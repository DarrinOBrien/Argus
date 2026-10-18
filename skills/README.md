# Skills

Agent skills for building on the Dragonwing IQ-9075 with LiquidAI models. Each folder holds a `SKILL.md` (frontmatter in the [Agent Skills](https://agentskills.io/specification) format, plus instructions) and a `scripts/` folder whose scripts were tested on the board.

| Skill | Scripts |
|---|---|
| [`iq9-preflight`](iq9-preflight/SKILL.md) | `preflight.sh [--json]`: read-only readiness check |
| [`iq9-geniex-lfm`](iq9-geniex-lfm/SKILL.md) | `serve.sh start\|stop\|restart\|status`, `lfm_client.py` (copy it into apps) |
| [`iq9-d1-decision-gate`](iq9-d1-decision-gate/SKILL.md) | `calibrate_threshold.py`: threshold sweep, AUC, confusion matrix |
| [`iq9-always-on-agent`](iq9-always-on-agent/SKILL.md) | `scaffold.sh apps/<name>`: a new app from the reference loop |
| [`iq9-lfm-tool-calling`](iq9-lfm-tool-calling/SKILL.md) | none; uses `examples/tool-calling/` |
| [`iq9-offline-rehearsal`](iq9-offline-rehearsal/SKILL.md) | `offline_audit.py <dir>`: static network-dependency scan |
| [`iq9-demo-prep`](iq9-demo-prep/SKILL.md) | `collect_metrics.sh`: TTFT, decode, memory, app-log medians |

## Using them

- **Claude Code** finds them in `.claude/skills/`. **Codex, pi, and other agents** that follow the `.agents/skills/` convention find them there. Both folders are symlinks to this one.
- **Any other agent:** `AGENTS.md` at the repo root links every skill. You can also point the agent at a `SKILL.md` directly.
- To use them across projects, symlink a skill folder into your agent's user skills folder (for example `~/.claude/skills/` or `~/.agents/skills/`).

Paths inside a skill are relative to the repo root, so run the scripts from there.

## Adding or changing a skill

- The folder name matches `name:` (lowercase letters and hyphens, at most 64 characters). The `description` says what the skill does and when to use it, in at most 1024 characters.
- Every number in a skill must be measured on the board and recorded in `docs/` first. The skill points back to its source.
- Scripts: run `--help` or `--self-test` cleanly. Bash scripts must pass `shellcheck`.
- Test on an IQ-9075 before you merge, and note the GenieX version.
