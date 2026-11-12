"""Local regression checks for the example and its real shared output guards."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("npu_example", Path(__file__).with_name("serve_lfm_npu.py"))
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.ready = patch.object(example.LFM, "ready", return_value=True)
        self.ready.start(); self.addCleanup(self.ready.stop)
        self.models = patch.object(example.LFM, "models", return_value=[example.DEFAULT_MODEL])
        self.models.start(); self.addCleanup(self.models.stop)
        self.post = patch.object(example.LFM, "_post")
        self.mock_post = self.post.start(); self.addCleanup(self.post.stop)

    @staticmethod
    def reply(text="Hello.", tokens=4, finish="stop"):
        return {"choices": [{"message": {"content": text, "reasoning_content": "Some reasoning"},
                             "finish_reason": finish}], "usage": {"completion_tokens": tokens}}, 12.0

    def call(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["serve_lfm_npu.py", *args]), contextlib.redirect_stdout(output):
            code = example.main()
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def test_success_request_fields(self):
        self.mock_post.return_value = self.reply()
        code, result = self.call("--max-tokens", "64")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        path, body = self.mock_post.call_args.args
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(body["max_completion_tokens"], 64)
        self.assertEqual(body["compute"], "npu")
        self.assertIs(body["enable_think"], False)

    def test_empty_or_zero_usage_fails_after_one_retry(self):
        for text, tokens in (("", 4), ("Hello.", 0)):
            with self.subTest(text=text, tokens=tokens):
                self.mock_post.reset_mock()
                self.mock_post.return_value = self.reply(text, tokens)
                code, result = self.call()
                self.assertEqual(code, 2)
                self.assertFalse(result["ok"])
                self.assertTrue(result["retried"])
                self.assertEqual(self.mock_post.call_count, 2)

    def test_cap_hit_and_http_failure_are_errors(self):
        self.mock_post.return_value = self.reply(finish="length")
        self.assertEqual(self.call()[0], 2)
        self.mock_post.side_effect = OSError("connection lost")
        code, result = self.call()
        self.assertEqual(code, 2)
        self.assertIn("connection lost", result["error"])

    def test_absent_server_or_model_never_sends_inference(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with patch.object(example.LFM, "ready", return_value=False):
                self.assertEqual(self.call()[0], 2)
            with patch.object(example.LFM, "models", return_value=[]):
                self.assertEqual(self.call()[0], 2)
        self.mock_post.assert_not_called()

    def test_invalid_inputs_never_send_requests(self):
        for args in (("--max-tokens", "0"), ("--timeout", "nan"), ("--prompt", " ")):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    self.call(*args)
                self.assertEqual(error.exception.code, 2)
        self.mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
