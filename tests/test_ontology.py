from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology"


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
