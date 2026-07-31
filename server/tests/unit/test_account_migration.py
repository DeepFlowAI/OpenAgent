"""Regression tests for the tenant account data migration."""

import importlib.util
from pathlib import Path


class _MigrationOperations:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, statement) -> None:
        self.executed_sql.append(str(statement))

    def create_table(self, *args, **kwargs) -> None:
        pass

    def create_index(self, *args, **kwargs) -> None:
        pass


def test_upgrade_backfills_missing_legacy_admin_email(monkeypatch) -> None:
    migration_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "f4a8c2d6e0b1_add_tenant_accounts.py"
    )
    spec = importlib.util.spec_from_file_location(
        "tenant_account_migration", migration_path
    )
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    operations = _MigrationOperations()
    monkeypatch.setattr(migration, "op", operations)

    migration.upgrade()

    sql = "\n".join(operations.executed_sql)
    assert "RAISE EXCEPTION" not in sql
    assert "NULLIF(btrim(admin_email), '')" in sql
    assert "legacy-admin+" in sql
    assert "@example.invalid" in sql
