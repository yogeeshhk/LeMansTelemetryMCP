"""Bounded CarSetup allowlist and validation tests with synthetic values only."""
import json

import duckdb

from lmu_mcp.database import inspect_connection, SignalReader
from lmu_mcp.setup import MAX_SETUP_JSON_CHARS, SETTING_ALLOWLIST, parse_car_setup


def setting(setting_id, value=3, minimum=0, maximum=8, **extra):
    return {"available": True, "key": setting_id, "value": value,
            "minValue": minimum, "maxValue": maximum,
            "stringValue": f"synthetic-{value}", **extra}


def test_allowlist_preserves_raw_range_and_producer_labels():
    raw = json.dumps({
        "VM_BRAKE_PRESSURE": setting("VM_BRAKE_PRESSURE", caption="Max Pedal Force"),
        "VM_DIFF_PRELOAD": setting("VM_DIFF_PRELOAD", value=2, minimum=1, maximum=5),
        "PRIVATE_UNKNOWN": setting("PRIVATE_UNKNOWN", value=99),
    })
    result = parse_car_setup(raw)
    assert result["status"] == "available" and len(result["settings"]) == 2
    pressure = next(row for row in result["settings"]
                    if row["setting_id"] == "VM_BRAKE_PRESSURE")
    assert pressure == {
        "setting_id": "VM_BRAKE_PRESSURE", "category": "brakes",
        "label": "Max Pedal Force", "producer_key": "VM_BRAKE_PRESSURE",
        "raw_value": 3, "declared_range": {"minimum": 0, "maximum": 8},
        "display_value": "synthetic-3", "direction_semantics": "unverified",
    }
    assert all(row["setting_id"] in SETTING_ALLOWLIST for row in result["settings"])


def test_unavailable_malformed_and_per_wheel_settings_are_omitted():
    raw = json.dumps({
        "VM_REAR_WING": setting("VM_REAR_WING", available=False),
        "VM_DIFF_POWER": setting("VM_DIFF_POWER", value=9, minimum=0, maximum=5),
        "VM_FRONT_WING": setting("WRONG_KEY"),
        "WM_PRESSURE-W_FL": setting("WM_PRESSURE-W_FL"),
    })
    result = parse_car_setup(raw)
    assert result["status"] == "unsupported" and result["settings"] == []
    assert result["omitted"] == 3
    assert all(not key.startswith("WM_") for key in SETTING_ALLOWLIST)


def test_missing_malformed_and_oversized_setup_are_unsupported():
    for raw in (None, "", "[]", "{bad", "x" * (MAX_SETUP_JSON_CHARS + 1)):
        result = parse_car_setup(raw)
        assert result["status"] == "unsupported" and result["settings"] == []


def test_reader_fetches_setup_without_adding_it_to_public_metadata():
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE metadata(key VARCHAR,value VARCHAR)")
        raw = json.dumps({"VM_DIFF_COAST": setting("VM_DIFF_COAST")})
        connection.execute("INSERT INTO metadata VALUES ('CarSetup',?),('DriverName','PRIVATE')", [raw])
        inspection = inspect_connection(connection)
        reader = SignalReader(connection, inspection)
        assert reader.car_setup_json() == raw
        assert reader.metadata() == {}
