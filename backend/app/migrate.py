"""Additive schema-drift migration for the SQLite dev/demo database.

The project has no migration framework (Alembic was deliberately left out
-- see the note at the bottom of this file for why). `Base.metadata.create_all()`
only creates tables that do not exist yet; it never alters an existing
table, so adding a column to a model (as happened with `Dish.reference_price`
and `NGOAllocation.expiry_risk`) silently desyncs every database that was
seeded before that change. The symptom is an opaque
`sqlite3.OperationalError: no such column: ...` the next time that column
is queried, which is exactly the bug this module exists to prevent.

This module audits every table's actual columns (via `PRAGMA table_info`)
against what the SQLAlchemy models declare, and safely adds whatever is
missing:

  * A column that is nullable, or has a usable scalar/callable default, can
    always be added without risking a NOT NULL violation on existing rows
    (SQLite requires a DEFAULT to add a NOT NULL column to a non-empty
    table, which is exactly what this provides).
  * A column with a *semantically* better backfill than its bare default
    (e.g. a new dish's reference_price should start equal to its existing
    base_price, not 0.0) can register that backfill in BACKFILL_RULES,
    applied as a follow-up UPDATE after the column is added.
  * A column that is NOT NULL with no default and no registered backfill
    cannot be safely auto-added -- there is no value that is obviously
    correct for pre-existing rows. migrate_schema() refuses and raises
    SchemaDriftError rather than guessing, and the caller (app.main) lets
    that fail the app's startup with a clear message instead of masking it.

Called once at FastAPI startup, after Base.metadata.create_all(), so a
plain `uvicorn app.main:app` restart self-heals an out-of-date database
for any purely additive model change -- the case this project will hit
every time a new column is added to an existing table -- without the
developer needing to remember to reseed.
"""
from __future__ import annotations

import datetime
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import Base
# SQLAlchemy only populates Base.metadata.tables as a side effect of
# importing the model classes. app.main always imports the models
# (transitively, via the routers) before this module's functions run, but
# nothing enforces that for a standalone script or test -- without this
# import, audit_schema()/migrate_schema() would silently iterate zero
# tables and report "no drift" even on a badly out-of-date database.
from app import models  # noqa: F401

# (table, column) -> a SQL statement to run once, immediately after that
# column is added, to backfill it more meaningfully than its bare default.
BACKFILL_RULES: dict[tuple[str, str], str] = {
    ("dishes", "reference_price"): "UPDATE dishes SET reference_price = base_price",
}


class SchemaDriftError(RuntimeError):
    """Raised when the database has drifted from the models in a way that
    cannot be safely auto-migrated (see module docstring)."""


@dataclass
class ColumnDrift:
    table: str
    column: str
    model_type: str
    issue: str  # "missing" | "type_mismatch"
    db_type: str | None = None


@dataclass
class MigrationReport:
    audited_tables: int = 0
    drift: list[ColumnDrift] = field(default_factory=list)
    added_columns: list[str] = field(default_factory=list)  # "table.column"
    backfilled: list[str] = field(default_factory=list)
    backup_path: str | None = None

    @property
    def missing(self) -> list[ColumnDrift]:
        return [d for d in self.drift if d.issue == "missing"]

    @property
    def type_mismatches(self) -> list[ColumnDrift]:
        return [d for d in self.drift if d.issue == "type_mismatch"]

    def summary(self) -> str:
        if not self.drift:
            return f"schema check: {self.audited_tables} tables, no drift"
        lines = [f"schema check: {self.audited_tables} tables, "
                 f"{len(self.missing)} missing column(s), "
                 f"{len(self.type_mismatches)} type mismatch(es)"]
        for col in self.added_columns:
            lines.append(f"  + added column {col}")
        for col in self.backfilled:
            lines.append(f"  + backfilled {col}")
        for d in self.type_mismatches:
            lines.append(f"  ! {d.table}.{d.column}: model says {d.model_type}, "
                         f"db says {d.db_type} (not auto-fixed -- review manually)")
        return "\n".join(lines)


def _literal_default(column) -> tuple[bool, object]:
    """Return (ok, value) -- a concrete Python value usable as a column's
    SQL DEFAULT, or (False, None) if this column has none."""
    if column.default is None:
        return False, None
    if not getattr(column.default, "is_scalar", False) and not getattr(
            column.default, "is_callable", False):
        return False, None
    arg = column.default.arg
    value = arg(None) if callable(arg) else arg
    return True, value


def _sql_literal(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return f"'{value.isoformat()}'"
    return "'" + str(value).replace("'", "''") + "'"


def audit_schema(engine: Engine) -> MigrationReport:
    """Compare every model's columns against the live database. Read-only."""
    if not Base.metadata.tables:
        # Defends against exactly the silent-no-op this module almost
        # shipped with: without the `app.models` import above having run,
        # there is nothing to compare against and every database would
        # wrongly report as drift-free.
        raise RuntimeError(
            "Base.metadata.tables is empty -- app.models was not imported "
            "before calling audit_schema(). This should be impossible; "
            "check that app/migrate.py still imports app.models.")
    report = MigrationReport()
    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names())

    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_tables:
            # A wholly missing table is Base.metadata.create_all()'s job,
            # not this module's -- it runs first and handles this case.
            continue
        report.audited_tables += 1
        db_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
        for column in table.columns:
            model_type = column.type.compile(dialect=engine.dialect)
            if column.name not in db_columns:
                report.drift.append(ColumnDrift(
                    table=table_name, column=column.name,
                    model_type=model_type, issue="missing"))
                continue
            db_type = str(db_columns[column.name]["type"])
            if db_type.split("(")[0].upper() != model_type.split("(")[0].upper():
                report.drift.append(ColumnDrift(
                    table=table_name, column=column.name, model_type=model_type,
                    issue="type_mismatch", db_type=db_type))
    return report


def _backup_sqlite_file(engine: Engine) -> str | None:
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    src = Path(url.database)
    if not src.exists():
        return None
    backup = src.with_name(f"{src.stem}.pre-migration-backup{src.suffix}")
    shutil.copy2(src, backup)
    return str(backup)


def migrate_schema(engine: Engine) -> MigrationReport:
    """Audit, then safely add any missing columns. Raises SchemaDriftError
    (without changing anything) if a missing column cannot be added safely.
    """
    report = audit_schema(engine)
    if not report.missing:
        return report

    # Pre-flight: make sure every missing column is actually safe to add
    # before touching the database at all, so a partially-applied,
    # half-broken migration is never left behind.
    unsafe: list[ColumnDrift] = []
    plans: list[tuple[ColumnDrift, str, str | None]] = []
    for drift in report.missing:
        column = Base.metadata.tables[drift.table].columns[drift.column]
        ok, default_value = _literal_default(column)
        backfill_sql = BACKFILL_RULES.get((drift.table, drift.column))
        if not column.nullable and not ok:
            unsafe.append(drift)
            continue
        ddl_type = column.type.compile(dialect=engine.dialect)
        clause = f'ALTER TABLE {drift.table} ADD COLUMN "{drift.column}" {ddl_type}'
        if not column.nullable:
            clause += f" NOT NULL DEFAULT {_sql_literal(default_value)}"
        elif ok:
            clause += f" DEFAULT {_sql_literal(default_value)}"
        plans.append((drift, clause, backfill_sql))

    if unsafe:
        names = ", ".join(f"{d.table}.{d.column}" for d in unsafe)
        raise SchemaDriftError(
            f"Cannot safely auto-migrate column(s): {names} -- NOT NULL with no "
            f"default and no registered backfill rule in app/migrate.py. This "
            f"usually means the database has drifted too far from the models "
            f"to patch column-by-column -- back up backend/data/*.db and "
            f"re-seed instead (`python -m app.seed`), or add an explicit entry "
            f"to BACKFILL_RULES if a safe backfill value does exist.")

    report.backup_path = _backup_sqlite_file(engine)

    with engine.begin() as conn:
        for drift, clause, backfill_sql in plans:
            conn.execute(text(clause))
            report.added_columns.append(f"{drift.table}.{drift.column}")
            if backfill_sql:
                conn.execute(text(backfill_sql))
                report.backfilled.append(f"{drift.table}.{drift.column}")

    return report


# Why not Alembic: this project creates its schema with
# Base.metadata.create_all() and treats the database as disposable,
# regenerable test/demo data (see seed.py and the README's "known
# limitations"). Alembic is the right tool once the schema needs versioned,
# reversible, team-coordinated migrations against data that must be
# preserved -- for a single SQLite file that a solo developer reseeds on
# demand, it would add real scaffolding (env.py, a versions/ directory, a
# migration per model change) without buying anything this module doesn't
# already provide for the one failure mode that actually occurs here:
# "I pulled new code with a new column and forgot to reseed."
