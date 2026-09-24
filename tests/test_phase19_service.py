"""Phase 19 service integration tests using synthetic telemetry and setup values."""
import json
import os
import shutil

import duckdb
import pytest

from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService
from tests.test_phase18_service import add_excursion_signals


def api(path):
    return TelemetryService(Repository(path.parent))


def setup_value(setting_id, value=3, available=True):
    return {"available": available, "key": setting_id, "value": value,
            "minValue": 0, "maxValue": 8, "stringValue": f"synthetic-{value}"}


def put_metadata(path, **values):
    with duckdb.connect(str(path)) as connection:
        for key, value in values.items():
            connection.execute("DELETE FROM metadata WHERE key=?", [key])
            connection.execute("INSERT INTO metadata VALUES (?,?)", [key, value])


def clone(source, name, **metadata):
    target = source.parent / name
    shutil.copy2(source, target)
    if metadata:
        put_metadata(target, **metadata)
    os.utime(target, None)
    return target


@pytest.fixture
def history_recording(corner_recording):
    setup = json.dumps({
        "VM_DIFF_PRELOAD": setup_value("VM_DIFF_PRELOAD", 2),
        "VM_FRONT_ANTISWAY": setup_value("VM_FRONT_ANTISWAY", 4),
        "WM_PRESSURE-W_FL": setup_value("WM_PRESSURE-W_FL", 99),
    })
    put_metadata(corner_recording, CarName="Ligier JS P325",
                 WeatherConditions="Dry", SessionType="Practice", CarSetup=setup)
    return corner_recording


def test_recent_discloses_selection_setup_and_weak_evidence_fallback(history_recording):
    result = api(history_recording).get_corner_history(history_recording.name, 1)
    assert result["status"] == "supported"
    assert result["scope"] == "recent" and len(result["selection"]["laps"]) == 2
    assert all(row["selection"] == "fastest" for row in result["selection"]["laps"])
    assert all(row["timing_source"] == "recorded Lap Time event"
               for row in result["selection"]["laps"])
    assert {row["setting_id"] for row in result["setup_context"]["settings"]} == {
        "VM_DIFF_PRELOAD", "VM_FRONT_ANTISWAY"
    }
    assert result["experiments"] == []
    assert "Keep the setup fixed" in result["next_step"]
    assert "PRIVATE DRIVER" not in json.dumps(result)


def test_general_builds_disjoint_good_bad_groups_and_marks_mixed_conditions(history_recording):
    same_a = clone(history_recording, "same-a.duckdb", WeatherConditions="Wet")
    same_b = clone(history_recording, "same-b.duckdb", WeatherConditions="Dry")
    clone(history_recording, "wrong-car.duckdb", CarName="Other car")
    clone(history_recording, "wrong-layout.duckdb", TrackLayout="Other layout")
    result = api(history_recording).get_corner_history(
        history_recording.name, 1, scope="general"
    )
    assert {row["session_id"] for row in result["conditions"]["sessions"]} == {
        history_recording.name, same_a.name, same_b.name
    }
    selected = result["selection"]["laps"]
    assert [row["selection"] for row in selected] == ["fastest"] * 3 + ["slowest"] * 3
    assert len({(row["session_id"], row["lap"]) for row in selected}) == 6
    assert result["conditions"]["mixed_weather"] is True
    assert all(row["fastest_samples"] == 3 and row["slowest_samples"] == 3
               and row["repeated"] for row in result["evidence"])
    assert result["truncation"]["candidate_sessions_examined"] == 4


def test_excursion_overlap_is_context_not_claimed_track_limit(history_recording):
    add_excursion_signals(history_recording)
    result = api(history_recording).get_corner_history(history_recording.name, 1)
    assert result["excursion_overlap"]["event_count"] > 0
    assert result["excursion_overlap"]["confidence"] == "unconfirmed_path_deviation"
    assert "track limit" not in json.dumps(result["excursion_overlap"]).lower()


def test_wrong_car_and_unavailable_setting_cannot_produce_setup_experiment(history_recording):
    put_metadata(history_recording, CarName="Some GT3")
    wrong_car = api(history_recording).get_corner_history(history_recording.name, 1)
    assert wrong_car["experiments"] == []
    assert wrong_car["sources"][0]["applicable"] is False

    unavailable = json.dumps({
        "VM_DIFF_PRELOAD": setup_value("VM_DIFF_PRELOAD", available=False)
    })
    put_metadata(history_recording, CarName="Ligier JS P325", CarSetup=unavailable)
    missing = api(history_recording).get_corner_history(history_recording.name, 1)
    assert missing["setup_context"]["status"] == "unsupported"
    assert missing["setup_context"]["settings"] == [] and missing["experiments"] == []


def test_missing_recorded_timing_reports_unsupported_without_guessing(history_recording):
    with duckdb.connect(str(history_recording)) as connection:
        connection.execute('UPDATE "Lap Time" SET value=0')
    result = api(history_recording).get_corner_history(history_recording.name, 1)
    assert result["status"] == "unsupported_timing"
    assert result["selection"]["laps"] == [] and result["lap_samples"] == []
    assert result["experiments"] == []
    assert "boundary" in result["selection"]["method"]


def test_corner_history_validates_scope_and_corner(history_recording):
    service = api(history_recording)
    for corner_id, scope in ((0, "recent"), (1, "all")):
        with pytest.raises(InspectionError):
            service.get_corner_history(history_recording.name, corner_id, scope)