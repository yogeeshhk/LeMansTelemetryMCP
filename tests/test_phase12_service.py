# Braking-zone service tests on known synthetic speed and control traces.
import duckdb
import pytest

from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService


@pytest.fixture
def braking_api(recording):
    with duckdb.connect(str(recording)) as connection:
        connection.execute("""UPDATE "Ground Speed" SET value = CASE
            WHEN rowid BETWEEN 20 AND 40 THEN 100 - (rowid - 20) * 2
            WHEN rowid BETWEEN 124 AND 148 THEN 95 - (rowid - 124) * 1.7
            ELSE 100 END""")
    return TelemetryService(Repository(recording.parent)), recording.name


def test_zones_have_position_speed_abs_and_pickup(braking_api):
    api,session_id=braking_api
    first=api.get_braking_zones(session_id,1)
    assert first['detected_brake_intervals']==1
    assert len(first['zones'])==1
    zone=first['zones'][0]
    assert zone['start_distance_m']==20
    assert zone['end_distance_m']==40
    assert zone['braking_distance_m']==20
    assert zone['initial_speed_kph']==100
    assert zone['minimum_speed_kph']==60
    assert zone['peak_brake_pct']==100
    assert zone['duration_s']==2
    assert zone['abs_active_time_s']==1
    assert zone['throttle_pickup_distance_m']==40
    assert zone['quality_flags']==[]
    assert first['excluded_intervals']=={'distance_or_clock_gap':0,'speed_coverage':0,'insufficient_speed_drop':0}


def test_zone_comparison_reports_metric_deltas_and_threshold_filter(braking_api):
    api,session_id=braking_api
    result=api.compare_braking_zones(session_id,1,2)
    assert len(result['matches'])==1
    differences=result['matches'][0]['a_minus_b']
    assert differences['brake_start_m']==0
    assert differences['braking_distance_m']==0
    assert differences['initial_speed_kph']==5
    assert differences['minimum_speed_kph']==pytest.approx(5.8)
    assert differences['brake_release_m']==0
    assert differences['throttle_pickup_m']==0
    assert differences['abs_active_time_s']==1
    assert result['unmatched_zone_ids_a']==[] and result['unmatched_zone_ids_b']==[]
    filtered=api.get_braking_zones(session_id,1,min_speed_drop_kph=80)
    assert filtered['zones']==[]
    assert filtered['excluded_intervals']['insufficient_speed_drop']==1


def test_invalid_settings_fail_before_database_open(braking_api,monkeypatch):
    api,session_id=braking_api
    def fail(*args): raise AssertionError('database opened')
    monkeypatch.setattr(api.repository,'open',fail)
    with pytest.raises(InspectionError,match='release_pct'):
        api.get_braking_zones(session_id,1,onset_pct=4,release_pct=5)
    with pytest.raises(InspectionError,match='10 to 300'):
        api.compare_braking_zones(session_id,1,2,max_match_distance_m=500)


def test_missing_optional_abs_is_null_not_zero(braking_api):
    api,session_id=braking_api
    path=api.repository.resolve(session_id)
    with duckdb.connect(str(path)) as connection:
        connection.execute('DROP TABLE "ABS"')
        connection.execute("DELETE FROM eventsList WHERE eventName='ABS'")
    result=api.get_braking_zones(session_id,1)
    assert result['zones'][0]['abs_active_time_s'] is None
    assert 'ABS signal unavailable' in result['warnings'][0]


def test_braking_cache_invalidates_when_recording_changes(braking_api):
    api,session_id=braking_api
    first=api.get_braking_zones(session_id,1)
    assert first['zones'][0]['minimum_speed_kph']==60
    path=api.repository.resolve(session_id)
    with duckdb.connect(str(path)) as connection:
        connection.execute('UPDATE "Ground Speed" SET value=30 WHERE rowid=30')
    second=api.get_braking_zones(session_id,1)
    assert second['zones'][0]['minimum_speed_kph']==30
