"""tests/rag/test_sec_submissions_parser.py — pure parser tests for KG-0.

Covers ``sec_kg/submissions.py`` against recorded, real-shaped SEC submissions
payloads:

* ``with_former_names.json`` — current name + two former-name intervals in the
  live API's ISO-8601 format (``2001-04-02T00:00:00.000Z``)
* ``multi_ticker_share_class.json`` — multiple tickers including a share class
* ``no_tickers.json`` — no tickers and no former names
* ``same_former_name_two_periods.json`` — one former name published in two
  periods (the name was reused after an intervening name)

No network, Databricks or Spark is required.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config.data_sources import validate_data_source
from sec_kg.submissions import (
    MISS_PAYLOAD_SHA256,
    SEC_EDGAR_DATA_SOURCE,
    FormerName,
    RegistrantRecord,
    normalize_cik,
    parse_registrant,
    parse_registrant_json,
    payload_sha256,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sec_submissions"
OBSERVED_AT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_three_recorded_fixtures_exist():
    names = {
        "with_former_names.json",
        "multi_ticker_share_class.json",
        "no_tickers.json",
    }
    present = {p.name for p in FIXTURES.glob("*.json")}
    assert names <= present


def test_parses_current_identity_fields():
    record = parse_registrant(_load("with_former_names.json"), OBSERVED_AT)

    assert record.cik10 == "0001234567"
    assert record.name == "Northwind Semiconductor Holdings, Inc."
    assert record.sic == "3674"
    assert record.sic_description == "Semiconductors & Related Devices"
    assert record.tickers == ["NWSC"]
    assert record.exchanges == ["Nasdaq"]
    assert record.state_of_incorporation == "DE"
    assert record.fiscal_year_end == "0927"
    assert record.entity_type == "operating"
    assert record.observed_at is OBSERVED_AT


def test_former_names_are_parsed_in_order_with_inclusive_dates():
    record = parse_registrant(_load("with_former_names.json"), OBSERVED_AT)

    # Exact list proves the parser does not drop formerNames (mutation: drop
    # the formerNames branch -> [] -> this assertion fails).
    assert record.former_names == [
        FormerName(
            name="Northwind Semiconductor Corp.",
            from_date="2001-04-02",
            to_date="2014-06-30",
        ),
        FormerName(
            name="Northwind Devices, Inc.",
            from_date="1995-01-03",
            to_date="2001-04-01",
        ),
    ]
    # Inclusive as given: the SEC end date must never be shifted (a +1 day
    # "exclusive" conversion would yield 2014-07-01).
    assert record.former_names[0].to_date == "2014-06-30"
    assert record.to_dict()["former_names"] == [
        {
            "name": "Northwind Semiconductor Corp.",
            "from_date": "2001-04-02",
            "to_date": "2014-06-30",
        },
        {
            "name": "Northwind Devices, Inc.",
            "from_date": "1995-01-03",
            "to_date": "2001-04-01",
        },
    ]


def test_former_names_accept_the_real_iso_timestamp_api_format():
    """The live API publishes formerNames[].from/.to as ISO-8601 midnight UTC.

    The recorded fixture stores the real format
    (``2001-04-02T00:00:00.000Z``); the parser keeps the published calendar date
    and never shifts it by a day or into an exclusive bound.
    """
    payload = _load("with_former_names.json")
    assert payload["formerNames"][0]["from"] == "2001-04-02T00:00:00.000Z"
    assert payload["formerNames"][1]["to"] == "2001-04-01T00:00:00.000Z"

    record = parse_registrant(payload, OBSERVED_AT)

    assert [fn.from_date for fn in record.former_names] == [
        "2001-04-02",
        "1995-01-03",
    ]
    assert [fn.to_date for fn in record.former_names] == [
        "2014-06-30",
        "2001-04-01",
    ]
    # Inclusive as published: no +1 day exclusive conversion.
    assert record.former_names[0].to_date == "2014-06-30"
    assert record.to_dict()["former_names"][0]["from_date"] == "2001-04-02"


def test_former_name_dates_accept_iso_and_plain_month_day_formats():
    payload = {
        "cik": "42",
        "name": "Dual Format Corp.",
        "formerNames": [
            {
                "name": "Iso Corp.",
                "from": "2001-04-02T00:00:00.000Z",
                "to": "2014-06-30T00:00:00.000Z",
            },
            {"name": "Plain Corp.", "from": "1995-01-03", "to": "2001-04-01"},
            {
                "name": "Open Corp.",
                "from": "2020-02-29T00:00:00.000Z",
                "to": None,
            },
        ],
    }

    record = parse_registrant(payload, OBSERVED_AT)

    assert [(fn.from_date, fn.to_date) for fn in record.former_names] == [
        ("2001-04-02", "2014-06-30"),
        ("1995-01-03", "2001-04-01"),
        ("2020-02-29", None),
    ]


def test_same_former_name_in_two_periods_stays_two_entries():
    """A reused name is two intervals, not one: from_date distinguishes them."""
    record = parse_registrant(
        _load("same_former_name_two_periods.json"), OBSERVED_AT
    )

    assert record.cik10 == "0000654321"
    atlas = [fn for fn in record.former_names if fn.name == "Atlas Re Corp."]
    assert [fn.from_date for fn in atlas] == ["1987-01-02", "2010-01-04"]
    assert [fn.to_date for fn in atlas] == ["1999-12-31", "2018-06-29"]
    assert len(record.former_names) == 3
    # Distinct (name, from_date) keys: the two periods would collapse otherwise.
    assert len({(fn.name, fn.from_date) for fn in atlas}) == 2


def test_unrecognised_former_name_date_is_kept_verbatim():
    """An unknown future format must stay visible, not become None."""
    record = parse_registrant(
        {
            "cik": "42",
            "formerNames": [
                {"name": "Odd Corp.", "from": "FY2001", "to": "unknown"}
            ],
        },
        OBSERVED_AT,
    )
    assert record.former_names[0].from_date == "FY2001"
    assert record.former_names[0].to_date == "unknown"


def test_multiple_tickers_including_share_class_preserved_in_order():
    record = parse_registrant(
        _load("multi_ticker_share_class.json"), OBSERVED_AT
    )

    assert record.cik10 == "0007654321"
    assert record.tickers == ["ORCA", "ORCA.A"]
    assert record.exchanges == ["Nasdaq", "Nasdaq"]
    assert record.former_names == []


def test_no_tickers_is_empty_not_fabricated():
    record = parse_registrant(_load("no_tickers.json"), OBSERVED_AT)

    assert record.cik10 == "0009999999"
    assert record.name == "Cascade Income Trust"
    assert record.tickers == []
    assert record.exchanges == []
    assert record.entity_type == "investment"


def test_missing_list_fields_become_empty_lists():
    payload = {"cik": "42", "name": "No Lists Corp."}
    record = parse_registrant(payload, OBSERVED_AT)

    assert record.cik10 == "0000000042"
    assert record.tickers == []
    assert record.exchanges == []
    assert record.former_names == []
    assert record.sic is None


def test_ein_is_not_part_of_the_record():
    """KG-0 drops EIN: it must not leak into the registrant record."""
    payload = _load("with_former_names.json")
    assert payload["ein"] == "123456789"

    record = parse_registrant(payload, OBSERVED_AT)

    assert "ein" not in record.to_dict()
    assert not hasattr(record, "ein")


def test_entity_name_is_used_only_when_name_is_absent():
    record = parse_registrant(
        {"cik": "7", "entityName": "Fallback Holdings"}, OBSERVED_AT
    )
    assert record.name == "Fallback Holdings"


def test_to_dict_has_the_documented_keys():
    record = parse_registrant(_load("no_tickers.json"), OBSERVED_AT)

    assert set(record.to_dict()) == {
        "cik10",
        "name",
        "data_source",
        "former_names",
        "sic",
        "sic_description",
        "tickers",
        "exchanges",
        "state_of_incorporation",
        "fiscal_year_end",
        "entity_type",
        "observed_at",
    }


def test_record_carries_the_sec_edgar_data_source():
    """Every parsed record names its provider code from the shared vocabulary."""
    record = parse_registrant(_load("with_former_names.json"), OBSERVED_AT)

    assert SEC_EDGAR_DATA_SOURCE == "sec_edgar"
    assert record.data_source == "sec_edgar"
    assert validate_data_source(record.data_source) == "sec_edgar"
    assert record.to_dict()["data_source"] == "sec_edgar"


def test_record_data_source_is_a_required_field():
    """Mutation guard: giving the field a default would stop this failing."""
    with pytest.raises(TypeError):
        RegistrantRecord(cik10="0000000042", name="No Source Corp.")


def test_parse_registrant_json_matches_mapping_input():
    text = (FIXTURES / "with_former_names.json").read_text(encoding="utf-8")

    from_json = parse_registrant_json(text, OBSERVED_AT)
    from_mapping = parse_registrant(json.loads(text), OBSERVED_AT)

    assert from_json == from_mapping


@pytest.mark.parametrize("bad_cik", [None, "", "  ", "12AB34"])
def test_missing_or_non_numeric_cik_fails_loudly(bad_cik):
    with pytest.raises(ValueError):
        parse_registrant({"cik": bad_cik, "name": "Bad CIK"}, OBSERVED_AT)


def test_normalize_cik_zero_pads_and_accepts_ints():
    assert normalize_cik(320193) == "0000320193"
    assert normalize_cik("320193") == "0000320193"
    assert normalize_cik("0000320193") == "0000320193"


def test_payload_sha256_is_stable_and_miss_sentinel_is_distinct():
    body = b'{"cik": "1234567"}'
    assert payload_sha256(body) == payload_sha256(body)
    assert len(payload_sha256(body)) == 64
    assert payload_sha256(body) != MISS_PAYLOAD_SHA256
    # sha256(b"sec-submissions-missing")
    assert MISS_PAYLOAD_SHA256 == (
        "2379b339bb93257712805c3b35766a593575ed64cdbf0424caa0e880e90b3925"
    )
