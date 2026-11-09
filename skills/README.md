# Skills

Agent skills for building on the Dragonwing IQ-9075 with LiquidAI models. Each folder holds a `SKILL.md` (frontmatter in the [Agent Skills](https://agentskills.io/specification) format, plus instructions) and supporting scripts (the tool-calling skill uses its example directly). Reference behavior has dated IQ9 evidence; revised helper behavior must pass local regression and bounded board integration checks before being called board-verified. Latest reference results are in [README Developer Notes](../README.md#developer-notes).

| Skill | Scripts |
|---|---|
| [`iq9-getting-started`](iq9-getting-started/SKILL.md) | none; guided UART/network/SSH setup, approved staging, and first NPU response using existing helpers |
| [`iq9-preflight`](iq9-preflight/SKILL.md) | `preflight.sh [--json] [--profile reference\|generator\|board] [--model M]`: selected-stack readiness |
| [`iq9-geniex-lfm`](iq9-geniex-lfm/SKILL.md) | `serve.sh run\|start\|stop\|restart\|status` (prefer foreground `run` in a separate terminal), `lfm_client.py` |
| [`iq9-d1-decision-gate`](iq9-d1-decision-gate/SKILL.md) | `calibrate_threshold.py`: threshold sweep, AUC/confusion matrices, separate held-out `--eval` |
| [`iq9-always-on-agent`](iq9-always-on-agent/SKILL.md) | `scaffold.sh apps/<name>`: a new app from the reference loop |
| [`iq9-lfm-tool-calling`](iq9-lfm-tool-calling/SKILL.md) | none; uses `examples/tool-calling/` |
| [`iq9-offline-rehearsal`](iq9-offline-rehearsal/SKILL.md) | `offline_audit.py <dir>`: static network-dependency scan |
| [`iq9-demo-prep`](iq9-demo-prep/SKILL.md) | `collect_metrics.sh` / `.py`: reasoning/answer TTFT, estimated decode, usage-based rates, memory/app-log medians |

## Using them

For first-time access, setup internet, or an unknown board state, start with [`iq9-getting-started`](iq9-getting-started/SKILL.md). It coordinates the guide, preflight, and generator skills; it is not an unattended installer. The guided onboarding flow is not yet board-rehearsed.

- **Claude Code** finds them in `.claude/skills/`. **Codex, pi, and other agents** that follow the `.agents/skills/` convention find them there. Both folders are symlinks to this one.
- **Any other agent:** `AGENTS.md` at the repo root links every skill. You can also point the agent at a `SKILL.md` directly.
- To use them across projects, symlink a skill folder into your agent's user skills folder (for example `~/.claude/skills/` or `~/.agents/skills/`).

Shell examples using `skills/...` or `examples/...` run from the repo root unless stated otherwise. Markdown links resolve from the skill file. When installing skills elsewhere, retain the referenced repo examples or use their explicit paths.

LFM3-1.7B and d1-2B are reference defaults, not competition requirements. d1 and external sensors are optional; sensors are not supplied. Verify each chosen model/configuration on the board.

## Adding or changing a skill

- The folder name matches `name:` (lowercase letters and hyphens, at most 64 characters). The `description` says what the skill does and when to use it, in at most 1024 characters.
- Performance numbers must be measured for the app: identify the board, runtime, model/build/precision, n, and medians, and mark estimates as estimates. Suggested caps, sample sizes, and planning floors are defaults/guidance, not measured guarantees. Never promote unverified behavior or local mock tests to board results.
- Scripts: run `--help` or `--self-test` cleanly. Bash scripts must pass `shellcheck`.
- Test on an IQ-9075 before you merge, and note the GenieX version.
