---
name: build-feature
description: Run the complete specification-driven feature delivery workflow.
agent: Feature Builder
---

Implement the feature described in: ${input:design_document:Path to the design document}

Target task slug: ${input:task_slug:Short kebab-case identifier}

Use the full feature delivery workflow. Begin with specification analysis and codebase discovery. Do not start implementation until the requirements manifest and plan are ready.

If the design document has critical ambiguity or conflicts with repository architecture, stop and ask for a decision. Otherwise continue autonomously through tests, incremental implementation, independent review, fixes, final verification, and a delivery report.

Do not commit, push, merge, deploy, or perform destructive operations.
