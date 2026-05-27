---
name: alembic-migrations
description: "Trigger: database schema change, alembic, migration, sqlalchemy models. Create and apply Alembic migrations securely."
license: Apache-2.0
metadata:
  author: gentleman-programming
  version: "1.0"
---

## Activation Contract

Run this skill when any change is made to SQLAlchemy models in the `jules` project.

## Hard Rules

- NEVER edit files in `alembic/versions/` manually.
- NEVER use `Base.metadata.create_all()` outside of test environments.
- Every schema change MUST have a migration created before commit.

## Execution Steps

1. Run `alembic revision --autogenerate -m "descripcion_del_cambio"`
2. Check the generated file in `alembic/versions/` to verify it's correct.
3. Run `alembic upgrade head`
4. Run `alembic downgrade -1` to verify reversibility.
5. Run `alembic upgrade head` again to return to the latest state.
