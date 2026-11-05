---
name: architecture-discovery
description: Use before substantial changes that cross modules, services, data models, APIs, background workers, tenant boundaries, or frontend/backend layers.
---

# Architecture discovery

1. Read root and nested repository instructions.
2. Identify the relevant applications/packages and their responsibilities.
3. Find analogous code paths, including tests.
4. Trace dependencies and data ownership.
5. Identify public interfaces and extension points.
6. Inspect persistence, transactions, concurrency, caching, and async boundaries.
7. Inspect authorization and tenant boundaries.
8. Identify operational concerns: migrations, queues, retries, monitoring, deployment, rollback.
9. Record observed facts separately from inferred assumptions.
10. Prefer existing patterns unless the design explicitly changes them.

Do not produce a generic architecture essay. Return a concise map tied to actual files and symbols.
