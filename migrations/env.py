"""Alembic environment — connects to the OCP Bionic database.

Supports both online (direct migration) and offline (SQL script generation) modes.
DATABASE_URL is read from the environment (via src.config) so the same migrations
work against SQLite (dev) and PostgreSQL (production) without code changes.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# src.config calls load_dotenv() and exposes DATABASE_URL
from src.config import DATABASE_URL

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Override sqlalchemy.url with the value from .env (takes precedence over alembic.ini)
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Set up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We use raw DDL in migrations (no SQLAlchemy ORM MetaData) — set target_metadata = None
target_metadata = None


def run_migrations_offline() -> None:
    """Generate a SQL script without connecting to the database.

    Run with: alembic upgrade --sql head > schema.sql
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


def run_migrations_online() -> None:
    """Apply migrations directly to the connected database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
