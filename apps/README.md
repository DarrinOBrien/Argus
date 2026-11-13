# apps

Your projects go here. Start a new one from the reference loop:

```bash
skills/iq9-always-on-agent/scripts/scaffold.sh apps/my-agent
```

Choose your app's name in place of `my-agent`. The scaffolded app runs with a rule gate and the LFM alone (`--gate rule`); d1 is an optional gate. Each app needs a README that covers how to run it, what you measured (with the actual runtime version, model revision, and precision), and its offline status. See [`AGENTS.md`](../AGENTS.md).

Evidence stays in your repo: `.gitignore` skips `*.jsonl` and `metrics.json` elsewhere but keeps them under `apps/`, so labeled calibration data, decision logs, and metrics can be committed. `*.log` files are still ignored.
