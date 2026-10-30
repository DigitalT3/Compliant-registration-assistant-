"""The committed Supabase migration files must match backend/migrations.py (they are generated)."""
from scripts import export_supabase_migrations as export


def test_committed_files_match_the_code():
    expected = export.build()
    on_disk = {p.name: p.read_text(encoding="utf-8") for p in export.OUT.glob("*.sql")}
    assert on_disk == expected, "Run `python -m scripts.export_supabase_migrations` and commit the result"


def test_every_table_is_hardened_and_ordered():
    files = export.build()
    names = sorted(files)
    assert names == [f"20261029{i:06d}_{n}.sql" for i, n in
                     zip(range(1, 14), ["base_schema", "poc_entities", "form_fields", "root_cause_category",
                                        "user_test_support", "employee_accounts", "forced_password_change",
                                        "customer_data_additions", "customer_source", "ai_event_detail", "dispute_review", "creator_role", "security_and_version"])]
    sql = "\n".join(files.values())
    import re
    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql))
    assert len(tables) == 23
    for t in tables | {"schema_meta"}:
        assert f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY;' in files[names[-1]], t
    assert "AUTOINCREMENT" not in sql and "PRAGMA" not in sql
