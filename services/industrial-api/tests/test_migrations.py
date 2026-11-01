"""Alembic 迁移：可升级、可回滚、可在干净库重放。"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def make_config(url: str) -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def sqlite_url(tmp_path):
    return f"sqlite:///{tmp_path / 'migration.db'}"


def test_upgrade_creates_schema_meta(sqlite_url):
    command.upgrade(make_config(sqlite_url), "head")

    engine = create_engine(sqlite_url)
    table_names = set(inspect(engine).get_table_names())
    engine.dispose()

    assert "schema_meta" in table_names
    assert "alembic_version" in table_names


def test_downgrade_removes_schema_meta(sqlite_url):
    config = make_config(sqlite_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(sqlite_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    version_table_exists = "alembic_version" in table_names
    revision = None
    if version_table_exists:
        with engine.connect() as connection:
            row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
            revision = row[0] if row else None
    engine.dispose()

    assert "schema_meta" not in table_names
    assert revision is None


def test_replay_is_idempotent_on_clean_database(sqlite_url):
    config = make_config(sqlite_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(sqlite_url)
    assert "schema_meta" in inspect(engine).get_table_names()
    engine.dispose()