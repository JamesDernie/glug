# Glug - A Copilot Autonomous Engineer

A Copilot-native, verification-oriented feature delivery framework for VS Code.

It is deliberately a starter rather than a turnkey autonomous system: agent delegation and tool availability depend on the selected Copilot harness, VS Code version, enabled features, and your organization's policies. The deterministic Python scripts are the enforcement layer; the agents are responsible for reasoning and making changes.

## What is included

- `.github/copilot-instructions.md` — project-wide engineering contract.
- `.github/agents/*.agent.md` — coordinator and specialist roles.
- `.github/skills/*/SKILL.md` — portable, on-demand workflows.
- `.github/prompts/build-feature.prompt.md` — reusable entry point.
- `agent-work/` — task-state templates and a requirements manifest example.
- `scripts/` — standard-library Python validation, quality runner, and report generator.
- `agent-quality.toml` — commands you must adapt to your repository.

## Install

1. Copy/merge `.github/`, `scripts/`, `agent-work/`, and `agent-quality.toml` into your repository.
2. Do not overwrite existing `copilot-instructions.md`; merge the engineering contract into it.
3. Open the repository in VS Code and select the **Copilot** harness in Chat.
4. Confirm Agent Skills and custom agents are enabled in your VS Code configuration.
5. Review every command in `agent-quality.toml`. Replace the examples with commands that actually work in your project.
6. Run the scripts locally before asking an agent to use them:

   ```bash
   python scripts/validate_requirements.py agent-work/requirements.example.json
   python scripts/run_quality.py --dry-run
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

## Python requirements

Python 3.11+ (uses only the standard library). No package installation is required.

## Quality runner

`agent-quality.toml` contains arrays of argument arrays. Each command runs without a shell, from the repository root. The runner captures stdout/stderr and writes `agent-work/quality-results.json`.

Adapt commands to your stack. The sample includes pytest and Ruff; remove or replace them if your project uses different tools.

## Safety / merge policy

- The scripts never commit, push, merge, deploy, or modify production data.
- The quality runner executes commands you configure. Review them before running.
- Passing tests does not prove correctness or complete requirement coverage.
- A generated report is evidence, not approval. A human still owns merge approval.
