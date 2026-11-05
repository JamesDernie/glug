# Glug - An Autonomous Engineer for Copilot and Claude Code

A verification-oriented feature delivery framework for GitHub Copilot in VS Code and for Claude Code.

It is deliberately a starter rather than a turnkey autonomous system: agent delegation and tool availability depend on the selected Copilot harness, VS Code version, enabled features, and your organization's policies. The deterministic Python scripts are the enforcement layer; the agents are responsible for reasoning and making changes.

## What is included

- `.github/copilot-instructions.md` — project-wide engineering contract.
- `.github/agents/*.agent.md` — coordinator and specialist roles.
- `.github/skills/*/SKILL.md` — portable, on-demand workflows.
- `.github/prompts/build-feature.prompt.md` — reusable entry point.
- `agent-work/` — task-state templates and a requirements manifest example.
- `.github/agent-scripts/` — standard-library Python validation, quality runner, and report generator.
- `.github/agent-quality.toml` — commands you must adapt to your repository.
- `CLAUDE.md` and `.claude/` — Claude Code wrappers around the same files (see [Using with Claude Code](#using-with-claude-code)).

## Install

1. Copy/merge `.github/` and `agent-work/` into your repository.
2. Do not overwrite existing `copilot-instructions.md`; merge the engineering contract into it.
3. Open the repository in VS Code and select the **Copilot** harness in Chat.
4. Confirm Agent Skills and custom agents are enabled in your VS Code configuration.
5. Review every command in `.github/agent-quality.toml`. Replace the examples with commands that actually work in your project.
6. Run the scripts locally before asking an agent to use them:

   ```bash
   python .github/agent-scripts/validate_requirements.py agent-work/requirements.example.json
   python .github/agent-scripts/run_quality.py --dry-run
   ```

7. Open Chat → Agent Customizations and verify the agents and skills are discovered.
8. Start with `/build-feature` (or select Feature Builder and provide the design document).

## Suggested first run

Use a non-critical feature or a completed historical feature as a benchmark. Ask Feature Builder to:
- read the design document,
- inspect the codebase and applicable skills,
- produce a plan and requirements manifest,
- stop before implementation if it finds unresolved contradictions or missing critical decisions.

Review the generated manifest and plan. Then let it proceed.

## Important Copilot compatibility note

VS Code's custom-agent file format is shared across harnesses, but not every frontmatter field works in every harness. In particular, the current VS Code reference says the Copilot harness does **not** support the `agents` frontmatter field. This starter therefore does not use it. The coordinator is instructed to use the Copilot task/delegation capability when it is available; otherwise it must explicitly perform the specialist workflow itself or ask you to enable delegation. Do not assume that writing several `.agent.md` files automatically guarantees that the coordinator can invoke them.

The reviewer and researcher are read-only by instruction and tool restriction. This is a guardrail, not a security boundary: retain normal workspace trust, permission prompts, backups, and Git review.

## How task state works

For each feature, create a separate directory under `agent-work/tasks/<slug>/` containing:

- `requirements.json`
- `plan.md`
- `decisions.md`
- `progress.md`
- `review-findings.json`
- `verification.json`

The agent must update these files as durable state. Do not rely on chat history as the source of truth.

## Using with Claude Code

The `.github/` files remain the single source of truth. Claude Code uses thin wrappers that point back to them:

| Copilot | Claude Code |
|---|---|
| `.github/copilot-instructions.md` | `CLAUDE.md` imports it with `@.github/copilot-instructions.md` |
| `.github/skills/<name>/` | `.claude/skills/<name>` (relative symlink) |
| `.github/agents/<role>.agent.md` | `.claude/agents/<role>.md` (tells the subagent to read the original first) |
| `/build-feature` prompt + Feature Builder agent | `/build-feature` skill: `/build-feature <design-doc> <task-slug>` |

Differences from Copilot:

- **Feature Builder runs in the main session**, not as a subagent, because Claude Code subagents cannot start other subagents. It hands work to `requirements-analyst`, `codebase-researcher`, `test-engineer` and `code-reviewer` with the Agent tool, so delegation is always available.
- **Tool access is slightly different.** `requirements-analyst` can write its two output files in the task directory and run the manifest validator. `code-reviewer` has Bash, limited by instruction to read-only git commands, so it can inspect the diff itself. As with Copilot, these are guardrails, not a security boundary.

To install into another repository, also copy `CLAUDE.md` and `.claude/` (merge with any existing `CLAUDE.md`). Copy with symlinks preserved (for example `cp -R`, or `rsync -a`). On Windows, where Git may check symlinks out as plain text files, replace each `.claude/skills/<name>` symlink with a copy of the matching `.github/skills/<name>` folder.

## Python requirements

Python 3.11+ (uses only the standard library). No package installation is required.

## Quality runner

`.github/agent-quality.toml` contains arrays of argument arrays. Each command runs without a shell, from the repository root. The runner captures stdout/stderr and writes `agent-work/quality-results.json`.

Adapt commands to your stack. The sample includes pytest and Ruff; remove or replace them if your project uses different tools.

## Safety / merge policy

- The scripts never commit, push, merge, deploy, or modify production data.
- The quality runner executes commands you configure. Review them before running.
- Passing tests does not prove correctness or complete requirement coverage.
- A generated report is evidence, not approval. A human still owns merge approval.
