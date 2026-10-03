from pathlib import Path
import re

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology"
SQL_DIRS = (ROOT / "silver", ROOT / "gold")

# These transforms are not present on this branch, but their checked schema is
# part of the ontology contract. Keep this small: SQL-backed tables are parsed.
EXTERNAL_SCHEMA_CONTRACTS = {
    "gold_regime_features": {"trade_date", "information_available_ts"},
    "gold_tradable_universe": {
        "symbol", "trade_date", "information_available_ts", "med_adv_60d", "adv_rank"
    },
}


def _documents():
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(ONTOLOGY.glob("*.yaml"))
    }


def _table_references(value, parent_key=None):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"table", "source_table", "left_table", "right_table", "evidence_table"}:
                yield child
            elif key == "tables":
                yield from child
            else:
                yield from _table_references(child, key)
    elif isinstance(value, list):
        for child in value:
            yield from _table_references(child, parent_key)


def _split_sql_list(value):
    """Split a SQL select/DDL list on top-level commas (best effort)."""
    parts, start, depth = [], 0, 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _output_columns(select_list):
    columns = set()
    for expression in _split_sql_list(select_list):
        expression = re.sub(r"--.*", "", expression).strip()
        alias = re.search(r"\bAS\s+`?([A-Za-z_]\w*)`?\s*$", expression, re.I)
        if alias:
            columns.add(alias.group(1).lower())
            continue
        bare = re.fullmatch(r"(?:[A-Za-z_]\w*\.)?`?([A-Za-z_]\w*)`?", expression)
        if bare:
            columns.add(bare.group(1).lower())
    return columns


def _sql_table_schemas():
    """Infer target columns from CREATE TABLE and SELECT lists in transforms."""
    schemas = {}
    for directory in SQL_DIRS:
        for path in directory.glob("*.sql"):
            sql = path.read_text(encoding="utf-8")
            targets = re.findall(
                r"\bMERGE\s+INTO\s+(?:[A-Za-z_]\w*\.){0,2}([A-Za-z_]\w*)",
                sql,
                re.I,
            )
            creates = re.finditer(
                r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                r"(?:[A-Za-z_]\w*\.){0,2}([A-Za-z_]\w*)\s*\((.*?)\)\s*USING",
                sql,
                re.I | re.S,
            )
            for match in creates:
                table = match.group(1).lower()
                schemas.setdefault(table, set()).update(
                    column.lower()
                    for column in re.findall(r"^\s*`?([A-Za-z_]\w*)`?\s+[A-Z]", match.group(2), re.M)
                )
            if targets:
                # A transform's SELECT aliases/bare projections form a safe
                # best-effort superset of its final MERGE output columns.
                projected = set()
                for match in re.finditer(r"\bSELECT\b(.*?)\bFROM\b", sql, re.I | re.S):
                    projected.update(_output_columns(match.group(1)))
                for table in targets:
                    schemas.setdefault(table.lower(), set()).update(projected)
    return schemas


def _filter_columns(sql):
    sql = re.sub(r":[A-Za-z_]\w*", "", sql)
    qualified = {
        column.lower()
        for qualifier, column in re.findall(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b", sql)
        if qualifier.lower() != "source"
    }
    comparisons = {
        column.lower()
        for column in re.findall(
            r"(?<!\.)\b([A-Za-z_]\w*)\b\s*(?:<=|>=|<>|=|<|>|\bIN\b|\bIS\b)", sql, re.I
        )
        if column.upper() not in {"WHERE", "AND", "OR", "NOT"}
    }
    return qualified | comparisons


def _assert_columns(table, columns, context, schemas):
    if table not in schemas:
        pytest.skip(f"{table}: no DDL or defining SQL transform in this repository")
    missing = set(columns) - schemas[table]
    assert not missing, f"{context}: {table} has no columns {sorted(missing)}"


def test_every_yaml_parses():
    documents = _documents()
    assert documents
    assert all(document is not None for document in documents.values())


def test_every_referenced_table_has_semantics():
    documents = _documents()
    known = set(documents["table_semantics.yaml"]["tables"])
    referenced = {
        table
        for name, document in documents.items()
        if name != "table_semantics.yaml"
        for table in _table_references(document)
    }
    assert referenced <= known, f"Missing table semantics: {sorted(referenced - known)}"


def test_no_duplicate_terms():
    terms = list(_documents()["business_terms.yaml"]["terms"])
    normalized = [term.casefold().replace("-", "_").replace(" ", "_") for term in terms]
    assert len(normalized) == len(set(normalized))


@pytest.mark.parametrize("table", sorted(_documents()["table_semantics.yaml"]["tables"]))
def test_table_keys_exist_in_sql_schema(table):
    semantics = _documents()["table_semantics.yaml"]["tables"][table]
    _assert_columns(table, semantics.get("keys", []), "ontology key", _sql_table_schemas())


@pytest.mark.parametrize("name", sorted(_documents()["filters.yaml"]["filters"]))
def test_filter_columns_exist_in_sql_schema(name):
    spec = _documents()["filters.yaml"]["filters"][name]
    if "sql" not in spec:
        pytest.skip(f"{name}: rule-only filter has no SQL columns")
    schemas = _sql_table_schemas()
    columns = _filter_columns(spec["sql"])
    checked = 0
    for table in spec["tables"]:
        if table in schemas:
            _assert_columns(table, columns, f"filter {name}", schemas)
            checked += 1
    if not checked:
        pytest.skip(f"{name}: none of its tables has DDL or defining SQL in this repository")


def test_join_columns_exist_in_sql_schema():
    schemas = _sql_table_schemas()
    joins = _documents()["join_hints.yaml"]
    for name, spec in joins["lineage"].items():
        left, right, keys = spec["left_table"], spec["right_table"], spec["keys"]
        if left in schemas and right in schemas and not set(keys) <= schemas[left] & schemas[right]:
            # A two-name list represents differently named left/right columns.
            if not (len(keys) == 2 and keys[0] in schemas[left] and keys[1] in schemas[right]):
                _assert_columns(left, keys, f"lineage {name}", schemas)
                _assert_columns(right, keys, f"lineage {name}", schemas)
        elif left in schemas:
            checked_keys = [keys[0]] if len(keys) == 2 and keys[0] in schemas[left] else keys
            _assert_columns(left, checked_keys, f"lineage {name}", schemas)
        elif right in schemas:
            checked_keys = [keys[1]] if len(keys) == 2 and keys[1] in schemas[right] else keys
            _assert_columns(right, checked_keys, f"lineage {name}", schemas)
    for name, spec in joins["joins"].items():
        tables = spec["tables"]
        if "left_keys" in spec and tables[0] in schemas:
            _assert_columns(tables[0], spec["left_keys"], f"join {name} left", schemas)
        if "right_keys" in spec and tables[1] in schemas:
            _assert_columns(tables[1], spec["right_keys"], f"join {name} right", schemas)
        for table in tables[:2]:
            if "additional_keys" in spec and table in schemas:
                _assert_columns(table, spec["additional_keys"], f"join {name}", schemas)


def test_external_schema_contracts_guard_missing_transforms():
    """Guard reviewed schemas until their defining SQL lands on this branch."""
    documents = _documents()
    semantics = documents["table_semantics.yaml"]["tables"]
    for table, columns in EXTERNAL_SCHEMA_CONTRACTS.items():
        assert set(semantics[table]["keys"]) <= columns
    for name, spec in documents["filters.yaml"]["filters"].items():
        for table in set(spec.get("tables", [])) & EXTERNAL_SCHEMA_CONTRACTS.keys():
            assert _filter_columns(spec.get("sql", "")) <= EXTERNAL_SCHEMA_CONTRACTS[table], name
