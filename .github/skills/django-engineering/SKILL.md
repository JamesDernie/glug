---
name: django-engineering
description: Use when a feature touches Django models, ORM queries, migrations, views, DRF APIs, management commands, signals, transactions, background jobs, or multi-tenant database routing.
---

# Django engineering checklist

Adapt all recommendations to the repository's actual conventions.

## Models and ORM
- Inspect existing model ownership, managers, constraints, indexes, and related_name conventions.
- Prefer database constraints for invariants that must hold under concurrency.
- Watch for N+1 queries; use select_related/prefetch_related deliberately.
- Avoid hidden database work in properties or serializers.
- Consider query count and pagination for collection endpoints.

## Transactions and concurrency
- Define the atomic unit of work.
- Use transaction.atomic where required.
- Consider select_for_update, uniqueness constraints, idempotency, and retry behaviour where concurrent requests can race.
- Ensure side effects are coordinated with transaction commit where appropriate.
- Test rollback and partial-failure behaviour.

## Tenancy and authorization
- Identify how the current project selects tenant databases/schemas.
- Never assume a request's tenant context is sufficient for background jobs.
- Test cross-tenant isolation and unauthorized access.
- Avoid unscoped queries that can cross tenant boundaries.
- Check default database and central/shared database behaviour explicitly.

## Migrations
- Inspect generated migrations before accepting them.
- Consider table size, locks, backfills, defaults, nullability, indexes, and deployment ordering.
- Check reversibility and data preservation.
- Do not run destructive production migrations.

## APIs and background work
- Follow existing serializer, permission, filtering, error, and versioning conventions.
- Validate external input at boundaries.
- Make jobs idempotent where retries are possible.
- Define retry, timeout, dead-letter, and observability behaviour.

## Tests
- Reuse project factories and fixtures.
- Test database routing and tenant isolation where applicable.
- Test transaction rollback and constraints.
- Assert query behaviour for performance-sensitive paths where the project supports it.
