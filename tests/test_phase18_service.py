"""Service-level excursion scope, filtering, coverage and cost-bound tests."""
import os
import shutil

import duckdb
import pytest

from lmu_mcp import config
from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService


def add_excursion_signals(path):
    with duckdb.connect(str(path)) as connection:
        connection.execute("INSERT INTO channelsList VALUES ('Path Lateral',10,'m'),('Track Edge',10,'m')")
        connection.execute('CREATE TABLE "Path Lateral"(value DOUBLE)')
        connection.execute('CREATE TABLE "Track Edge"(value DOUBLE)')
        connection.execute('''INSERT INTO "Path Lateral"
            SELECT CASE
              WHEN rowid BETWEEN 30 AND 34 THEN 5.5
              WHEN rowid BETWEEN 70 AND 74 THEN -5.5
              WHEN rowid BETWEEN 136 AND 140 THEN 5.4
              WHEN rowid=20 THEN 5.6 ELSE 0 END
            FROM "GPS Time"''')
        connection.execute('''INSERT INTO "Track Edge"
            SELECT CASE WHEN rowid BETWEEN 70 AND 74 THEN -5 ELSE 5 END
            FROM "GPS Time"''')
        connection.execute("INSERT INTO \"In Pits\" VALUES (11,1),(12,0)")


@pytest.fixture
def excursion_recording(recording):
    add_excursion_signals(recording)
    return recording


def service(path):
    return TelemetryService(Repository(path.parent))


def clone(source, name, metadata=None):
    target = source.parent / name
    shutil.copy2(source, target)
    if metadata:
        with duckdb.connect(str(target)) as connection:
            for key, value in metadata.items():
                connection.execute("UPDATE metadata SET value=? WHERE key=?", [value, key])
    os.utime(target, None)
    return target


def test_recent_counts_repeated_and_flagged_complete_laps(excursion_recording):
    result = service(excursion_recording).get_excursion_hotspots(excursion_recording.name)
    assert result["status"] == "supported"
    assert result["event_count"] == 3 and result["total"] == 2
    repeated = next(row for row in result["hotspots"] if row["side"] == "right")
    assert repeated["event_count"] == 2
    assert repeated["distinct_affected_laps"] == 2
    assert repeated["confidence"] == "unconfirmed_repeated"
    assert result["sessions"][0]["flagged_complete_laps"] == 1
    assert result["sessions"][0]["partial_laps_excluded"] == 1
    assert result["coverage"]["fraction"] > .95
    assert "official track-limit" in result["method"]
    assert result["corroboration"]["surface_types"].startswith("not_used")


def test_hotspot_has_unique_sourced_feature_when_supported(excursion_recording):
    with duckdb.connect(str(excursion_recording)) as connection:
        connection.execute(
            "UPDATE metadata SET value='Circuit de Spa-Francorchamps' "
            "WHERE key IN ('TrackName','TrackLayout')"
        )
        connection.execute('UPDATE "Lap Dist" SET value=value+4750')
    result = service(excursion_recording).get_excursion_hotspots(excursion_recording.name)
    feature = next(row["track_feature"] for row in result["hotspots"]
                   if row["track_feature"] is not None)
    assert feature["feature_id"] == "campus"
    assert feature["status"] == "calibrated"

def test_missing_samples_and_reversed_lap_are_not_bridged(excursion_recording):
    with duckdb.connect(str(excursion_recording)) as connection:
        connection.execute('UPDATE "Path Lateral" SET value=NULL WHERE rowid=32')
        connection.execute('UPDATE "Lap Dist" SET value=-1 WHERE rowid=50')
    result = service(excursion_recording).get_excursion_hotspots(excursion_recording.name)
    assert result["status"] == "partial"
    assert result["event_count"] == 1
    assert result["sessions"][0]["unsupported_laps"] == [
        {"lap": 1, "code": "distance_reversal"}
    ]
    assert result["hotspots"][0]["distinct_affected_laps"] == 1


def test_missing_or_ambiguous_edge_signal_returns_unsupported(excursion_recording):
    with duckdb.connect(str(excursion_recording)) as connection:
        connection.execute("DELETE FROM channelsList WHERE channelName='Track Edge'")
        connection.execute('DROP TABLE "Track Edge"')
    result = service(excursion_recording).get_excursion_hotspots(excursion_recording.name)
    assert result["status"] == "unsupported"
    assert result["hotspots"] == []
    assert {item["code"] for item in result["sessions"][0]["unsupported_laps"]} == {"missing_channel"}


def test_general_uses_only_exact_layout_and_car(excursion_recording):
    same = clone(excursion_recording, "same.duckdb")
    clone(excursion_recording, "wrong-car.duckdb", {"CarName": "Other car"})
    clone(excursion_recording, "wrong-layout.duckdb", {"TrackLayout": "Other layout"})
    result = service(excursion_recording).get_excursion_hotspots(
        excursion_recording.name, scope="general"
    )
    assert {row["session_id"] for row in result["sessions"]} == {
        excursion_recording.name, same.name
    }
    assert result["event_count"] == 6
    assert result["distinct_affected_sessions"] == 2
    assert result["truncation"]["candidate_sessions_examined"] == 3


def test_general_session_lap_and_page_bounds_are_explicit(excursion_recording, monkeypatch):
    for index in range(6):
        clone(excursion_recording, f"same-{index}.duckdb")
    result = service(excursion_recording).get_excursion_hotspots(
        excursion_recording.name, scope="general", limit=1
    )
    assert len(result["sessions"]) == config.MAX_EXCURSION_HISTORY_SESSIONS
    assert result["truncation"]["sessions_truncated"]
    assert result["truncation"]["page_truncated"] and result["next_offset"] == 1
    monkeypatch.setattr(config, "MAX_EXCURSION_HISTORY_LAPS", 1)
    limited = service(excursion_recording).get_excursion_hotspots(
        excursion_recording.name, scope="general"
    )
    assert limited["coverage"]["analyzed_laps"] == 1
    assert limited["truncation"]["laps_truncated"]


def test_excursion_request_validation(excursion_recording):
    api = service(excursion_recording)
    for kwargs in ({"scope": "all"}, {"offset": -1}, {"limit": 51}):
        with pytest.raises(InspectionError):
            api.get_excursion_hotspots(excursion_recording.name, **kwargs)
