---
name: feature-delivery
description: Use when implementing a substantial feature from a design document or technical specification. Covers requirements decomposition, codebase discovery, planning, incremental implementation, traceability, review, and delivery reporting.
---

# Feature delivery workflow

1. Identify the design document and the feature boundary.
2. Inspect repository instructions and Git status.
3. Discover relevant skills by their descriptions; load only skills that match affected technologies or risks.
4. Create a durable task directory under `agent-work/tasks/<slug>/`.
5. Decompose the design into atomic requirements and invariants.
6. Map each requirement to components and verification.
7. Research analogous code and tests before proposing new abstractions.
8. Record assumptions, conflicts, and decisions.
9. Produce a dependency-aware plan.
10. Design tests from requirements before implementation.
11. Implement small, independently verifiable slices.
12. Run targeted checks after each slice.
13. Obtain independent read-only review.
14. Validate findings, fix genuine defects, and re-review material changes.
15. Run full quality checks and generate the delivery report.

## Durable state

Maintain:
- `requirements.json`
- `plan.md`
- `architecture-map.md`
- `decisions.md`
- `progress.md`
- `review-findings.json`
- `verification.json`

After context loss, reconstruct state from these files and Git rather than relying on chat history.

## Completion

Never report merge readiness without executed verification evidence. Distinguish passed, failed, blocked, and not-run checks. Human approval remains required.
