# Claude Code instructions

The engineering contract below is shared with GitHub Copilot. It applies to all Claude Code work in this repository exactly as it applies to Copilot work.

@.github/copilot-instructions.md

## Claude Code mapping

The canonical workflow definitions live under `.github/`. Claude Code files are thin wrappers around them; edit the `.github/` originals, not the wrappers.

| Copilot | Claude Code |
|---|---|
| `.github/copilot-instructions.md` | Imported above |
| `.github/skills/<name>/` | `.claude/skills/<name>` (symlink) |
| `.github/agents/<role>.agent.md` | `.claude/agents/<role>.md` (wrapper that loads the original) |
| `/build-feature` prompt + Feature Builder agent | `/build-feature` skill, run in the main session |

- Feature Builder runs in the main session, not as a subagent, because Claude Code subagents cannot start other subagents. It delegates with the Agent tool to `requirements-analyst`, `codebase-researcher`, `test-engineer` and `code-reviewer`.
- Where a `.github/` file refers to "the Copilot harness", "the task/delegation capability" or Copilot tool names (`read`, `search`, `edit`, `execute`, `agent`), read them as the Claude Code equivalents (Read, Grep/Glob, Edit/Write, Bash, Agent).
