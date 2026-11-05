---
name: test-design
description: Use when deriving tests for new features, refactors, bug fixes, domain rules, data integrity constraints, APIs, or workflows. Focuses on requirement traceability, negative cases, properties, and meaningful assertions.
---

# Test design workflow

1. Read the requirement and its rationale.
2. Identify externally observable behaviour and invariants.
3. Identify valid, invalid, boundary, failure, retry, concurrency, and authorization cases.
4. Choose the lowest test level that provides meaningful confidence; add integration/contract/e2e tests where unit tests cannot prove the behaviour.
5. Reuse established fixtures and factories.
6. Avoid mirroring private implementation details.
7. Ensure assertions would fail for plausible defects.
8. Run new tests against the current baseline where possible.
9. Record requirement IDs in test names, markers, comments, or the traceability manifest.
10. Report tests that are missing, flaky, environment-dependent, or not run.

Coverage is a diagnostic, not a proof of correctness. Consider mutation testing for critical business logic.
