"""Regression tests for app/migrate.py -- the schema-drift self-heal that
fixes the "no such column: dishes.reference_price" class of bug.

Uses its own throwaway SQLite files rather than the shared session DB from
conftest.py, since these tests need to deliberately desync a schema.
"""
import shutil
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.migrate import SchemaDriftError, audit_schema, migrate_schema


@pytest.fixture()
def stale_db(tmp_path):
    """A copy of the live (fully migrated, already seeded by conftest's
    session-start hook) dev schema with the two columns this project has
    actually added after initial release dropped back out, reproducing
    exactly the database state the bug report described.
    """
    from app.config import DATABASE_URL
    src = DATABASE_URL.replace("sqlite:///", "")
    dst = tmp_path / "stale.db"
    shutil.copy2(src, dst)

    con = sqlite3.connect(dst)
    con.execute("ALTER TABLE dishes DROP COLUMN reference_price")
    con.execute("ALTER TABLE ngo_allocations DROP COLUMN expiry_risk")
    con.commit()
    con.close()
    return dst


def test_audit_detects_missing_columns(stale_db):
    engine = create_engine(f"sqlite:///{stale_db}")
    report = audit_schema(engine)
    missing = {(d.table, d.column) for d in report.missing}
    assert ("dishes", "reference_price") in missing
    assert ("ngo_allocations", "expiry_risk") in missing


def test_fully_migrated_db_reports_no_drift():
    from app.database import engine
    report = audit_schema(engine)
    assert report.drift == []


def test_migrate_adds_columns_and_backfills_correctly(stale_db):
    engine = create_engine(f"sqlite:///{stale_db}")
    report = migrate_schema(engine)

    assert "dishes.reference_price" in report.added_columns
    assert "ngo_allocations.expiry_risk" in report.added_columns
    assert "dishes.reference_price" in report.backfilled

    con = sqlite3.connect(stale_db)
    rows = con.execute("SELECT base_price, reference_price FROM dishes").fetchall()
    con.close()
    assert rows  # sanity: the table actually has data
    assert all(base == ref for base, ref in rows), (
        "reference_price must be backfilled from base_price, not left at the "
        "bare column default")


def test_migrate_is_idempotent(stale_db):
    """Running the migration twice must not error or double-apply anything."""
    engine = create_engine(f"sqlite:///{stale_db}")
    migrate_schema(engine)
    second = migrate_schema(engine)
    assert second.added_columns == []
    assert second.drift == []


def test_migrate_backs_up_before_changing_anything(stale_db):
    engine = create_engine(f"sqlite:///{stale_db}")
    report = migrate_schema(engine)
    assert report.backup_path is not None
    assert Path(report.backup_path).exists()

    # The backup must reflect the PRE-migration (stale) schema.
    con = sqlite3.connect(report.backup_path)
    cols = [r[1] for r in con.execute("PRAGMA table_info(dishes)")]
    con.close()
    assert "reference_price" not in cols


def test_unsafe_drift_is_refused_without_partial_changes(tmp_path):
    """A NOT NULL column with no default and no registered backfill rule
    must never be guessed at -- the engine should refuse outright, and must
    not leave any other column half-migrated in the process.
    """
    from app.config import DATABASE_URL
    src = DATABASE_URL.replace("sqlite:///", "")
    dst = tmp_path / "unsafe.db"
    shutil.copy2(src, dst)

    con = sqlite3.connect(dst)
    con.execute("ALTER TABLE dishes DROP COLUMN unit_cost")      # unsafe: no default
    con.execute("ALTER TABLE dishes DROP COLUMN reference_price")  # safe: has a backfill rule
    con.commit()
    con.close()

    engine = create_engine(f"sqlite:///{dst}")
    with pytest.raises(SchemaDriftError, match="unit_cost"):
        migrate_schema(engine)

    con = sqlite3.connect(dst)
    cols = [r[1] for r in con.execute("PRAGMA table_info(dishes)")]
    con.close()
    assert "unit_cost" not in cols
    assert "reference_price" not in cols, (
        "a refused migration must not partially apply the columns it "
        "considered safe before hitting the unsafe one")
