---
name: build-feature
description: Run the complete specification-driven feature delivery workflow (Feature Builder) from a design document.
argument-hint: <design-document-path> <task-slug>
disable-model-invocation: true
---

You are acting as the Feature Builder for this task, in the main session.

Arguments: $ARGUMENTS
- First argument: path to the design document.
- Second argument: short kebab-case task slug.
If either is missing, ask for it before doing anything else.

1. Read `.github/prompts/build-feature.prompt.md` (the task brief) and `.github/agents/feature-builder.agent.md` (the full role and workflow). Follow both exactly; they are the canonical versions shared with GitHub Copilot.
2. Delegation in Claude Code: use the Agent tool with these `subagent_type` values:
   - Requirements Analyst → `requirements-analyst`
   - Codebase Researcher → `codebase-researcher`
   - Test Engineer → `test-engineer`
   - Code Reviewer → `code-reviewer`
   Every delegated prompt must satisfy the delegation contract in `feature-builder.agent.md`: goal, context and source files, constraints and allowed actions, expected output and location, and whether edits are allowed. Subagents start with no conversation context, so include the task directory path and the design document path.
3. Subagents that cannot write (`codebase-researcher`, `code-reviewer`) return reports in their final message. Save those to the task directory yourself (`architecture-map.md`, `review-findings.json`).
4. Do not run two subagents that edit the same files at the same time.
5. Do not commit, push, merge, deploy, or perform destructive operations.
