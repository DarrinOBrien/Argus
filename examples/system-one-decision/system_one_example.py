"""System One (d1-3B): named decisions over a state, in one forward pass, no output tokens.

Runs three steps and prints what it gets back:
  1. sensor states, each answered by three questions (noul, choice, score)
  2. one image answered by a noul question
  3. the same sensor states as one packed batch

Each decision is appended as one JSON line to --log, which is the offline proof a demo
can show. The alert threshold is an example value. Tune it on states you have labeled.
"""

import argparse
import json
import pathlib
import time
from datetime import datetime, timezone

import torch
from PIL import Image, ImageDraw
from transformers import AutoModel

ALERT_THRESHOLD = 0.5  # example value: tune on your own labeled states

SENSOR_QUESTIONS = {
    "alert": {
        "type": "noul",
        "instructions": "Does this state need a human alert right now?",
    },
    "category": {
        "type": "choice",
        "instructions": "Which category fits this state best?",
        "criteria": {
            "thermal": "Temperature or heat problem",
            "motion": "Unexpected movement",
            "normal": "Nothing notable",
        },
    },
    "severity": {
        "type": "score",
        "instructions": "How severe is it?",
        "criteria": ["Low", "Moderate", "Critical"],
    },
}

SENSOR_STATES = [
    {"temp_c": 71.5, "temp_c_1min_ago": 58.0, "motion": "none"},
    {"temp_c": 36.8, "temp_c_1min_ago": 36.6, "motion": "none"},
    {"temp_c": 37.0, "temp_c_1min_ago": 36.9, "motion": "sudden 2.1 g spike"},
]


def red_square_image() -> Image.Image:
    img = Image.new("RGB", (256, 256), "white")
    ImageDraw.Draw(img).rectangle([64, 64, 192, 192], fill=(220, 30, 30))
    return img


def timed(fn, *args, **kwargs):
    start = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, (time.perf_counter() - start) * 1000


def assert_answer_shape(answers: dict) -> None:
    # Shapes come from api.py: noul -> {"noul": p}; choice -> {"choice", "confidence", "probabilities"};
    # score -> {"score", "confidence", "probabilities", "legend"}
    assert set(answers) == {"alert", "category", "severity"}, answers.keys()
    assert 0.0 <= answers["alert"]["noul"] <= 1.0
    assert answers["category"]["choice"] in SENSOR_QUESTIONS["category"]["criteria"]
    assert 0.0 <= answers["severity"]["score"] <= 2.0  # expected level index on 3 levels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-dir", default="~/models/d1-3B")
    ap.add_argument("--log", default="decisions.jsonl")
    ap.add_argument("--dtype", default="float32", choices=["float32", "bfloat16"],
                    help="weight dtype on CPU. float32 matches the model card's CPU path.")
    args = ap.parse_args()
    dtype = {"float32": torch.float32, "bfloat16": torch.bfloat16}[args.dtype]

    model_dir = pathlib.Path(args.model_dir).expanduser()
    load_start = time.perf_counter()
    model = AutoModel.from_pretrained(str(model_dir), trust_remote_code=True, dtype=dtype)
    model = model.to("cpu").eval()
    print(f"loaded {model_dir} as {args.dtype} in {time.perf_counter() - load_start:.1f} s, "
          f"threads={torch.get_num_threads()}")

    # Step 1: sensor states, one call each. The first call pays setup costs, so it is a warm-up.
    model.system_one(json.dumps(SENSOR_STATES[0]), SENSOR_QUESTIONS)

    print("\n== 1. sensor states")
    with open(args.log, "a") as log, torch.inference_mode():
        for obs in SENSOR_STATES:
            res, ms = timed(model.system_one, json.dumps(obs), SENSOR_QUESTIONS)
            answers = res["answers"]
            assert_answer_shape(answers)
            p_alert = answers["alert"]["noul"]
            record = {
                "t": datetime.now(timezone.utc).isoformat(),
                "obs": obs,
                "p_alert": round(p_alert, 4),
                "alert_fired": p_alert >= ALERT_THRESHOLD,
                "category": answers["category"]["choice"],
                "category_confidence": round(answers["category"]["confidence"], 4),
                "severity_expected_level": round(answers["severity"]["score"], 3),
                "output_tokens": res["usage"]["output_tokens"],
                "input_tokens": res["usage"]["input_tokens"],
                "ms": round(ms, 1),
            }
            print(json.dumps(record))
            log.write(json.dumps(record) + "\n")

    # Step 2: one image, one noul question, state=None.
    print("\n== 2. image (state=None)")
    with torch.inference_mode():
        res, ms = timed(
            model.system_one,
            None,
            {"red": {"type": "noul", "instructions": "Is there a red object in this picture?"}},
            images=[red_square_image()],
        )
    print(json.dumps({"p_red_object": round(res["answers"]["red"]["noul"], 4), "ms": round(ms, 1),
                      "input_tokens": res["usage"]["input_tokens"]}))

    # Step 3: the same sensor states as one batch, packed with no padding.
    print("\n== 3. batch of", len(SENSOR_STATES))
    with torch.inference_mode():
        batch, ms = timed(
            model.system_one_batch,
            [(json.dumps(obs), SENSOR_QUESTIONS) for obs in SENSOR_STATES],
        )
    for obs, item in zip(SENSOR_STATES, batch):
        assert_answer_shape(item["answers"])
        print(json.dumps({"obs": obs, "p_alert": round(item["answers"]["alert"]["noul"], 4)}))
    print(f"batch of {len(batch)} in {ms:.1f} ms total")


if __name__ == "__main__":
    main()
