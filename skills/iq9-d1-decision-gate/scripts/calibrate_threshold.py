#!/usr/bin/env python3
"""Pick a d1 alert threshold from labeled states, instead of guessing 0.5.

Input: JSONL. Each line has a label and either a stored probability or a state to score:
    {"label": true,  "p_alert": 0.71}                                   # already scored
    {"label": false, "obs": {"soc_temp_c": 52.1, "soc_temp_c_1min_ago": 51.8}}   # scored here with d1
`label` is true when a human would want an alert. Logs from examples/always-on-agent work once you add
"label" to each line (their probability is at decision.p_alert).

    python calibrate_threshold.py labeled.jsonl                      # stored probabilities only, no torch
    ~/.venvs/d1/bin/python calibrate_threshold.py labeled.jsonl --score --model-dir ~/models/d1-2B
    python calibrate_threshold.py labeled.jsonl --objective recall --min-precision 0.8
    python calibrate_threshold.py --self-test

Output: a threshold sweep, the chosen threshold, and its confusion matrix. Also warns when d1 does not separate
the classes (AUC near 0.5). The previous d1-3B gate did not track the board's thermal readings; calibrate
d1-2B afresh, then use a rule instead or rewrite the state and questions if it still does not separate them.
"""

import argparse
import json
import os
import sys


def get_p(row):
    if "p_alert" in row:
        return float(row["p_alert"])
    d = row.get("decision") or {}
    if "p_alert" in d:
        return float(d["p_alert"])
    return None


def score_missing(rows, model_dir, questions_from):
    """Score rows that only have obs with d1 (fp32, CPU). About 4-5 s per state on the IQ-9075."""
    import torch
    from transformers import AutoModel
    sys.path.insert(0, questions_from)
    from system_one_example import SENSOR_QUESTIONS  # noqa: E402
    todo = [r for r in rows if get_p(r) is None]
    if not todo:
        return
    model = AutoModel.from_pretrained(os.path.expanduser(model_dir), trust_remote_code=True, dtype=torch.float32)
    model = model.to("cpu").eval()
    with torch.inference_mode():
        for i, r in enumerate(todo, 1):
            a = model.system_one(json.dumps(r["obs"]), SENSOR_QUESTIONS)["answers"]
            r["p_alert"] = a["alert"]["noul"]
            print(f"  scored {i}/{len(todo)} p_alert={r['p_alert']:.3f} label={r['label']}", file=sys.stderr)


def confusion(pairs, t):
    tp = sum(1 for p, y in pairs if p >= t and y)
    fp = sum(1 for p, y in pairs if p >= t and not y)
    fn = sum(1 for p, y in pairs if p < t and y)
    tn = sum(1 for p, y in pairs if p < t and not y)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"threshold": round(t, 4), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}


def auc(pairs):
    pos = [p for p, y in pairs if y]
    neg = [p for p, y in pairs if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def choose(pairs, objective, min_precision):
    cands = sorted({p for p, _ in pairs} | {0.5})
    rows = [confusion(pairs, t) for t in cands]
    if objective == "recall":
        ok = [r for r in rows if r["precision"] >= min_precision]
        best = max(ok, key=lambda r: (r["recall"], r["threshold"])) if ok else None
    else:
        # Among ties, take the middle threshold: the widest margin on both sides.
        top = max(r["f1"] for r in rows)
        tied = [r for r in rows if r["f1"] == top]
        best = tied[len(tied) // 2]
    return rows, best


def report(pairs, objective, min_precision):
    n_pos = sum(y for _, y in pairs)
    print(f"{len(pairs)} labeled states: {n_pos} alert, {len(pairs) - n_pos} no-alert")
    a = auc(pairs)
    if a is not None:
        print(f"AUC {a:.3f}" + ("  <- d1 barely separates these classes; a threshold will not fix that" if a < 0.65 else ""))
    rows, best = choose(pairs, objective, min_precision)
    print("\nthreshold  tp  fp  fn  tn  precision  recall  f1")
    step = max(1, len(rows) // 15)
    for r in rows[::step]:
        print(f"{r['threshold']:9.4f} {r['tp']:3} {r['fp']:3} {r['fn']:3} {r['tn']:3} {r['precision']:10.3f} {r['recall']:7.3f} {r['f1']:5.3f}")
    print(f"\nat 0.5: {json.dumps(confusion(pairs, 0.5))}")
    if best is None:
        print(f"no threshold reaches precision >= {min_precision}")
        return None
    print(f"chosen ({objective}): {json.dumps(best)}")
    if len(pairs) < 30 or min(n_pos, len(pairs) - n_pos) < 10:
        print("warning: fewer than 30 states or 10 per class; treat this threshold as provisional")
    return best


def self_test():
    sep = [(0.9, True), (0.8, True), (0.7, True), (0.3, False), (0.2, False), (0.1, False)]
    assert auc(sep) == 1.0
    _, best = choose(sep, "f1", 0.0)
    assert best["fp"] == 0 and best["fn"] == 0, best
    noise = [(0.6, True), (0.6, False), (0.4, True), (0.4, False)]
    assert auc(noise) == 0.5
    assert confusion(sep, 0.5) == {"threshold": 0.5, "tp": 3, "fp": 0, "fn": 0, "tn": 3,
                                   "precision": 1.0, "recall": 1.0, "f1": 1.0}
    _, b = choose([(0.9, True), (0.6, False), (0.55, True), (0.1, False)], "recall", 0.99)
    assert b["threshold"] == 0.9, b
    print("self-test passed")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labeled", nargs="?", help="JSONL with label plus p_alert (or obs, with --score)")
    ap.add_argument("--score", action="store_true", help="score rows without p_alert using d1 (needs the d1 venv)")
    ap.add_argument("--model-dir", default="~/models/d1-2B")
    ap.add_argument("--questions-from", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                             "..", "..", "..", "examples", "system-one-decision"),
                    help="directory with system_one_example.py (SENSOR_QUESTIONS)")
    ap.add_argument("--objective", choices=["f1", "recall"], default="f1",
                    help="f1: balance misses and false alarms. recall: catch the most alerts at --min-precision")
    ap.add_argument("--min-precision", type=float, default=0.8)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.labeled:
        ap.error("labeled JSONL required")
    rows = [json.loads(line) for line in open(args.labeled) if line.strip()]
    rows = [r for r in rows if "label" in r]
    if args.score:
        score_missing(rows, args.model_dir, args.questions_from)
    pairs = [(get_p(r), bool(r["label"])) for r in rows if get_p(r) is not None]
    skipped = len(rows) - len(pairs)
    if skipped:
        print(f"skipped {skipped} rows with no p_alert (use --score to compute them)")
    if not pairs:
        sys.exit("no scored, labeled rows")
    report(pairs, args.objective, args.min_precision)


if __name__ == "__main__":
    main()
