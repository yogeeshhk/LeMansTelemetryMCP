"""Core sustained path-deviation and candidate-signal mapping tests."""
import numpy as np
import pytest

from lmu_mcp.analysis.excursions import ExcursionSettings, detect_path_deviations
from lmu_mcp.database import InspectionError, inspect_connection


def detect(lateral, edge, times=None, distance=None, max_gap=0.15):
    lateral = np.asarray(lateral, dtype=float)
    count = len(lateral)
    times = np.arange(count) * 0.1 if times is None else np.asarray(times, dtype=float)
    distance = np.arange(count) * 5.0 if distance is None else np.asarray(distance, dtype=float)
    return detect_path_deviations(times, distance, lateral, edge, max_gap)


def test_sustained_events_on_both_signed_edges_and_short_noise():
    lateral = [0, 5.2, 5.3, 5.4, 5.5, 0, -5.2, -5.3, -5.4, -5.5, 0, 5.4, 0]
    edge = [5, 5, 5, 5, 5, 5, -5, -5, -5, -5, -5, 5, 5]
    result = detect(lateral, edge)
    assert [event["side"] for event in result["events"]] == ["right", "left"]
    assert all(event["duration_s"] == pytest.approx(0.3) for event in result["events"])
    assert result["events"][0]["peak_excess_m"] == pytest.approx(0.5)
    assert result["short_runs_excluded"] == 1
    assert all(event["confidence"] == "unconfirmed" for event in result["events"])


def test_missing_sample_and_clock_gap_split_runs():
    lateral = [0, 5.3, 5.3, np.nan, 5.3, 5.3, 5.3, 5.3]
    edge = [5] * len(lateral)
    after_missing = detect(lateral, edge)["events"]
    assert len(after_missing) == 1 and after_missing[0]["start_time_s"] == pytest.approx(.4)
    times = [0, .1, .2, .3, 1.0, 1.1, 1.2, 1.3]
    lateral = [5.3] * len(times)
    result = detect(lateral, edge, times=times)
    assert len(result["events"]) == 2
    assert result["coverage_s"] == pytest.approx(.6)


def test_ambiguous_sign_reversal_and_missing_signals_are_unsupported():
    with pytest.raises(InspectionError) as error:
        detect([0, 5.2, 5.3, 5.4], [-5, -5, -5, -5])
    assert error.value.code == "ambiguous_edge_sign"
    with pytest.raises(InspectionError) as error:
        detect([np.nan] * 4, [5] * 4)
    assert error.value.code == "unsupported_excursion_signals"
    with pytest.raises(InspectionError) as error:
        detect([0, 5.2, 5.3, 5.4], [5] * 4, distance=[0, 5, 4, 10])
    assert error.value.code == "invalid_excursion_samples"


def test_thresholds_and_event_bound_are_validated():
    with pytest.raises(InspectionError):
        ExcursionSettings(min_duration_s=.1).validate()
    with pytest.raises(InspectionError) as error:
        detect_path_deviations(
            np.arange(1.0, step=.1), np.arange(10),
            [5.5, 5.5, 5.5, 0, 0, 5.5, 5.5, 5.5, 0, 0], [5] * 10, .15,
            ExcursionSettings(max_events=1, min_duration_s=.2),
        )
    assert error.value.code == "excursion_limit"


def test_canonical_candidate_signal_mapping_preserves_units_and_components():
    import duckdb
    with duckdb.connect() as connection:
        connection.execute("CREATE TABLE channelsList(channelName VARCHAR,frequency INTEGER,unit VARCHAR)")
        connection.execute("CREATE TABLE eventsList(eventName VARCHAR,unit VARCHAR)")
        for name, unit, columns in [
            ("GPS Time", "s", "value DOUBLE"),
            ("Path Lateral", "m", "value FLOAT"),
            ("Track Edge", "m", "value FLOAT"),
            ("SurfaceTypes", "", "value1 UTINYINT,value2 UTINYINT,value3 UTINYINT,value4 UTINYINT"),
            ("GPS Latitude", "deg", "value FLOAT"),
            ("GPS Longitude", "deg", "value FLOAT"),
        ]:
            connection.execute("INSERT INTO channelsList VALUES (?,?,?)", [name, 10, unit])
            connection.execute(f'CREATE TABLE "{name}"({columns})')
        result = inspect_connection(connection)
    assert result.channels.channels["path_lateral"].unit == "m"
    assert result.channels.channels["track_edge"].unit == "m"
    assert result.channels.channels["surface_types"].value_columns == ("value1", "value2", "value3", "value4")
    assert result.channels.channels["gps_latitude"].unit == "deg"
    assert result.channels.channels["gps_longitude"].unit == "deg"
