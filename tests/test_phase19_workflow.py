"""Phase 19 guide-first workflow acceptance using synthetic telemetry."""
import json

import duckdb

from lmu_mcp.database import Repository
from lmu_mcp.server import INSTRUCTIONS
from lmu_mcp.service import TelemetryService
from lmu_mcp.track_knowledge import load_track_knowledge


def service(path):
    return TelemetryService(Repository(path.parent))


def set_identity(path, track, layout, car="Unsupported synthetic car"):
    with duckdb.connect(str(path)) as connection:
        for key, value in (("TrackName", track), ("TrackLayout", layout),
                           ("CarName", car)):
            connection.execute("UPDATE metadata SET value=? WHERE key=?", [value, key])


def test_la_sarthe_is_a_full_guide_without_personal_metrics(recording):
    set_identity(recording, "Circuit de la Sarthe", "Circuit de la Sarthe")
    result = service(recording).get_track_guide(recording.name)
    assert result["pack_status"] == "calibrated" and result["total"] == 15
    assert len(result["coaching"]) == 8
    assert {row["topic"] for row in result["coaching"]} == {
        "overview", "setup", "race", "practice"
    }
    assert all(feature["coaching"] and feature["coaching"][0]["topic"] == "driving"
               for feature in result["features"])
    wire = json.dumps(result)
    for private_or_personal in ("PRIVATE DRIVER", "lap_time_s", "recorded_lap_number",
                                "CarSetup", "raw_value", "proposed_direction"):
        assert private_or_personal not in wire
    assert "not a prescribed braking point" in wire.lower()
    assert "no click, pressure, ride-height, wing or differential value is prescribed" in wire.lower()


def test_guide_survives_bad_distance_and_personal_analysis_follows_on_request(corner_recording):
    set_identity(corner_recording, "Circuit de la Sarthe", "Circuit de la Sarthe")
    coach = service(corner_recording)
    guide = coach.get_track_guide(corner_recording.name)
    assert guide["total"] == 15 and len(guide["coaching"]) == 8

    # A general guide remains metadata-only even when lap distance cannot support analysis.
    with duckdb.connect(str(corner_recording)) as connection:
        connection.execute('UPDATE "Lap Dist" SET value=0 WHERE rowid=50')
    still_available = service(corner_recording).get_track_guide(corner_recording.name)
    assert still_available["features"] == guide["features"]

    # Restore this synthetic path, then model the later explicit personal-analysis request.
    with duckdb.connect(str(corner_recording)) as connection:
        connection.execute('UPDATE "Lap Dist" SET value=rowid WHERE rowid<100')
    personal = service(corner_recording).get_corner_history(
        corner_recording.name, 1, scope="recent"
    )
    assert personal["lap_samples"] and personal["selection"]["laps"]
    assert personal["identity"]["CarName"] == "Unsupported synthetic car"
    assert personal["experiments"] == []
    assert personal["sources"][0]["applicable"] is False


def test_missing_pack_and_explicit_track_precedence_are_unambiguous(recording):
    set_identity(recording, "Unreviewed Circuit", "Unknown Layout")
    result = service(recording).get_track_guide(recording.name)
    assert result["pack_status"] == "no_pack"
    assert result["features"] == [] and result["coaching"] == []
    assert load_track_knowledge("Circuit de Spa-Francorchamps",
                                "Circuit de Spa-Francorchamps") is not None
    assert load_track_knowledge("Circuit de Spa-Francorchamps", "Unknown Layout") is None
    assert "explicitly requested track takes priority over the latest recording" in INSTRUCTIONS
    assert "requires an exact matching layout" in INSTRUCTIONS