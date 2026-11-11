"""Local guard checks with a mocked vendor CLI; no board or model downloads."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("zetic_example", Path(__file__).with_name("run.py"))
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)

STDOUT = "model LiquidAI/LFM3-1.7B | sdk 0.1.0 runtime 61ba260\ncaps text 1 | load 3300 ms\nThe sky is blue due to Rayleigh scattering.\n"
STDERR = "[sdk] hexrt open 1300 ms; v73; HEXRT_NSP2=1 cpu_rows=32768x6\n[sdk] loaded lfm3-1.7b v73\n[Ok] finish stop | prompt 40 rows (cached 0) -> 12 tokens | ttft 54.2 ms (prefill dsp 40.0) | decode 12 steps 45.70 t/s\n"


class RunTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.scratch.cleanup)
        root = Path(self.scratch.name)
        self.sdk, self.model = root / "sdk", root / "model"
        (self.sdk / "bin").mkdir(parents=True)
        (self.sdk / "lib").mkdir()
        cli = self.sdk / "bin/zetic_lfm3_cli"
        cli.touch(); cli.chmod(0o755)
        (self.sdk / "lib/libhexrt_v73_skel.so").touch()
        (self.model / "v73").mkdir(parents=True)
        self.manifest = {"schema": "zetic.hexagon.package/1", "package": {"name": "lfm3-1.7b"},
                         "target": {"hexagon_arch": 73, "platform": "linux-arm64-qcom"},
                         "capabilities": {"text": True, "image": False, "audio": False},
                         "model": {"repo_id": "LiquidAI/LFM3-1.7B"}, "lm": {"quant": "w4lpbq"}}
        self.save_manifest()
        self.arch = patch.object(example.platform, "machine", return_value="aarch64")
        self.arch.start(); self.addCleanup(self.arch.stop)
        self.process = patch.object(example.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, STDOUT, STDERR))
        self.mock_run = self.process.start(); self.addCleanup(self.process.stop)

    def save_manifest(self):
        (self.model / "v73/manifest.json").write_text(json.dumps(self.manifest))

    def call(self, **kwargs):
        return example.run(self.sdk, self.model, "Explain the blue sky.", **kwargs)

    def test_success_caps_and_timing(self):
        result = self.call(max_tokens=64)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["completion_tokens"], 12)
        self.assertEqual(result["timings"]["runtime_ttft_ms"], 54.2)
        self.assertEqual(result["timings"]["model_load_ms"], 3300)
        command = self.mock_run.call_args.args[0]
        self.assertEqual(command[command.index("--max-tokens") + 1], "64")
        self.assertEqual(command[command.index("--target") + 1], "v73")
        self.assertEqual(self.mock_run.call_args.kwargs["env"]["HF_HUB_OFFLINE"], "1")
        self.assertEqual(result["actions"], [])

    def test_invalid_limits_do_not_launch(self):
        for kwargs in ({"max_tokens": 0}, {"max_tokens": True}, {"max_tokens": 1025},
                       {"timeout": 0}, {"timeout": float("nan")}, {"timeout": float("inf")}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(self.call(**kwargs)["ok"])
        self.mock_run.assert_not_called()

    def test_output_failures(self):
        cases = [
            (STDOUT, STDERR.replace("12 tokens", "0 tokens")),
            (STDOUT, STDERR.replace("12 tokens", "65 tokens")),
            (STDOUT, STDERR.replace("finish stop", "finish length")),
            (STDOUT.split("The sky")[0], STDERR),
            ("<think>Reasoning only</think>", STDERR),
            ("<think>Unfinished reasoning", STDERR),
            (STDOUT, "no usage"),
            (STDOUT, STDERR.replace("HEXRT_NSP2=1", "missing device")),
        ]
        for stdout, stderr in cases:
            with self.subTest(stderr=stderr):
                self.mock_run.return_value = subprocess.CompletedProcess([], 0, stdout, stderr)
                self.assertFalse(self.call(max_tokens=64)["ok"])

    def test_nonzero_exit_and_timeout(self):
        self.mock_run.return_value = subprocess.CompletedProcess([], 1, STDOUT, STDERR)
        self.assertFalse(self.call()["ok"])
        self.mock_run.side_effect = subprocess.TimeoutExpired("mock", 120, output=b"partial", stderr=b"timeout")
        result = self.call()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stdout"], "partial")

    def test_missing_model_and_wrong_target(self):
        result = example.run(self.sdk, self.model / "missing", "Hello")
        self.assertFalse(result["ok"])
        self.manifest["target"]["hexagon_arch"] = 79
        self.save_manifest()
        self.assertFalse(self.call()["ok"])
        self.mock_run.assert_not_called()

    def test_malformed_manifest_is_error_data(self):
        for manifest in ([], {"package": []}, {"package": {"name": "lfm3-1.7b"}, "target": []}):
            (self.model / "v73/manifest.json").write_text(json.dumps(manifest))
            self.assertFalse(self.call()["ok"])
        self.mock_run.assert_not_called()

    def test_text_package_rejects_media(self):
        image = self.model / "test.ppm"; image.touch()
        self.assertFalse(self.call(image=image)["ok"])
        self.mock_run.assert_not_called()

    def test_omni_audio(self):
        self.manifest["package"]["name"] = "lfm3-omni-2b"
        self.manifest["capabilities"]["audio"] = True
        self.save_manifest()
        audio = self.model / "test.wav"; audio.touch()
        self.mock_run.return_value = subprocess.CompletedProcess([], 0, STDOUT,
                                    STDERR.replace("loaded lfm3-1.7b", "loaded lfm3-omni-2b"))
        self.assertTrue(self.call(audio=audio)["ok"])
        command = self.mock_run.call_args.args[0]
        self.assertIn("Perform ASR in English.", command)

    def test_cli_jsonl_logging_and_log_error(self):
        log = self.model / "results.jsonl"
        args = ["run.py", "--sdk", str(self.sdk), "--model", str(self.model), "--log", str(log)]
        output = io.StringIO()
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            self.assertEqual(example.main(), 0)
        self.assertEqual(json.loads(output.getvalue()), json.loads(log.read_text()))
        args[-1] = str(self.model / "missing/results.jsonl")
        output = io.StringIO()
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            self.assertEqual(example.main(), 2)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_no_laptop_inference_or_option_injection(self):
        with patch.object(example.platform, "machine", return_value="arm64"):
            self.assertFalse(self.call()["ok"])
        self.mock_run.assert_not_called()
        result = example.run(self.sdk, self.model, "--tts")
        self.assertTrue(result["ok"])
        self.assertTrue(result["command"][-1].startswith("[request:"))


if __name__ == "__main__":
    unittest.main()
