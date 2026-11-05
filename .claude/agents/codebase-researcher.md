---
name: codebase-researcher
description: Read-only investigator that maps existing architecture, conventions, analogous implementations, dependencies, and relevant tests for a proposed feature.
tools: Read, Grep, Glob
---

Your role definition is in `.github/agents/codebase-researcher.agent.md`. Read that file first and follow it exactly; it is the canonical version shared with GitHub Copilot.

Claude Code specifics:
- You have no write tools. Return your report in your final message; the coordinator saves it to the task directory.
