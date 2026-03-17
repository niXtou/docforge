"""Alembic environment configuration for async SQLAlchemy.

WHAT IS ALEMBIC?
─────────────────
Alembic is a database migration tool. When you change a model in app/models/db.py
(add a column, rename a table, etc.), Alembic generates a versioned migration
script that transforms the existing database schema to match the new model.

HOW TO USE IT
──────────────
  # Generate a migration after changing a model:
  cd backend
  alembic revision --autogenerate -m "add updated_at to extraction_jobs"

  # Apply all pending migrations (run on deploy):
  alembic upgrade head

  # Roll back the last migration:
  alembic downgrade -1

OFFLINE VS ONLINE MODE
───────────────────────
  Offline: generates SQL statements to a file without connecting to the DB.
           Useful for reviewing what will change before running it.
           Run with: alembic upgrade head --sql

  Online:  connects to the DB and runs migrations directly.
           The normal mode for local dev and CI/CD pipelines.

WHY ASYNCIO?
─────────────
SQLAlchemy's async engine (asyncpg) can't be used from synchronous code.
Alembic is synchronous by default, so we bridge the gap by running
`asyncio.run(run_async_migrations())` inside the sync `run_migrations_online()`.
Inside `run_async_migrations`, we use `connection.run_sync(do_run_migrations)`
to hand back to Alembic's sync migration runner with a real connection.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# IMPORTANT: This import has a side effect — it registers all ORM models with
# Base.metadata so Alembic can detect table additions/changes automatically.
# The `# noqa: F401` suppresses the "imported but unused" linter warning.
import app.models.db  # noqa: F401  # type: ignore[reportUnusedImport]
from alembic import context
from app.core.config import settings
from app.core.database import Base

config = context.config

# Set up Python logging from the alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This tells Alembic which tables to compare against the DB when autogenerating
target_metadata = Base.metadata

# Override the DB URL from alembic.ini with our application settings
# so we don't have to keep two copies of the connection string in sync
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Run migrations in offline mode (no DB connection required).

    Generates SQL statements as text instead of executing them.
    Useful for reviewing changes or running in restricted environments.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations using the provided synchronous connection.

    Called from within `run_async_migrations` via connection.run_sync() —
    Alembic's migration runner is synchronous, so we pass it a sync connection
    even though the outer engine is async.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via a sync bridge."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # don't pool connections for one-off migration runs
    )
    async with connectable.connect() as connection:
        # run_sync lets us call a sync function (do_run_migrations) from async context
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in online mode (connects to the real DB)."""
    asyncio.run(run_async_migrations())


# Alembic calls this file as a script — detect the mode and run accordingly
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
