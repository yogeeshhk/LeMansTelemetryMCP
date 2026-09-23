import hashlib
import json
import numpy as np
import duckdb
import pytest
from lmu_mcp.database import Repository,InspectionError
from lmu_mcp.service import TelemetryService
from lmu_mcp.alignment import make_grid


@pytest.fixture
def api(recording): return TelemetryService(Repository(recording.parent))


def test_discovery_metadata_and_channel_catalog(api,recording):
    sessions=api.list_sessions()
    assert sessions['sessions'][0]['filename']=='race.duckdb'
    assert sessions['sessions'][0]['session_id']=='race.duckdb'
    assert str(recording.parent) not in json.dumps(sessions)
    info=api.get_session_info(recording.name)
    assert info['number_of_laps']==2 and info['session_duration_s']==23
    assert info['start_time'] is None
    assert 'PRIVATE' not in json.dumps(info)
    channels=api.list_channels(recording.name)['channels']
    speed=next(c for c in channels if c['name']=='speed')
    assert speed['extrema']=={'value':{'min':30,'max':36}}
    assert speed['sample_count']==231


def test_lap_pagination_and_summary_metrics(api,recording):
    rows=api.list_laps(recording.name,limit=1)
    assert rows['next_offset']==1 and rows['total']==3
    assert rows['laps'][0]['max_speed_kph']==36
    summary=api.get_lap_summary(recording.name,1)
    assert summary['abs']['active_time_s']==pytest.approx(1)
    assert summary['abs']['activation_count']==1
    assert summary['tc']['active_time_s']==pytest.approx(1)
    assert summary['gear_changes']==1
    assert summary['braking_events']==1
    assert summary['average_speed_kph']==36
    assert summary['coasting_time_pct']==0
    assert 'channels' not in summary


def test_distance_alignment_has_continuous_interpolation_and_discrete_hold(api,recording):
    data=api.get_telemetry(recording.name,1,['speed','gear'],45,55,1)
    assert data['distance_m']==list(range(45,56))
    assert data['elapsed_s']==pytest.approx(np.arange(45,56)/10)
    assert data['channels']['speed']==[36]*11
    assert data['channels']['gear']==[1]*5+[2]*6
    assert 'hold' in data['interpolation']['gear']
    assert data['units']['speed']=='km/h'


def test_analytic_lap_delta_and_control_differences(api,recording):
    data=api.compare_laps(recording.name,[1,2],['speed','brake'],20,80,10)
    assert data['deltas'][0]['elapsed_delta_a_minus_b_s']==pytest.approx(-np.arange(20,81,10)/50)
    assert data['deltas'][0]['reported_lap_delta_s']==-2
    assert data['deltas'][0]['speed_delta_a_minus_b_kph']==[6]*7
    assert data['control_point_differences'][0]['brake']['matches'][0]['a_minus_b_m']==pytest.approx(0)


def test_outside_coverage_is_null_not_extrapolated(api,recording):
    data=api.get_telemetry(recording.name,1,['speed'],98,102,1)
    assert data['channels']['speed'][:2]==[36,36]
    assert data['channels']['speed'][2:]==[None,None,None]
    assert data['missing_crossings']==3


@pytest.mark.parametrize('args',[
    (0,100,0.001,['speed']), (0,3000,.5,['speed']), (0,100000,1,['speed']),
    (0,100,1,['speed']*21), (float('nan'),100,1,['speed']),
    (100,0,1,['speed']), (0,100,float('inf'),['speed']),
    (0,100,1,[]), (0,100,1,[['speed']]),
])
def test_invalid_requests_are_rejected_before_grid_allocation(args):
    with pytest.raises(InspectionError): make_grid(*args)


def test_reversing_distance_rejected(api,recording):
    with duckdb.connect(str(recording)) as c: c.execute('UPDATE "Lap Dist" SET value=-100 WHERE rowid=50')
    with pytest.raises(InspectionError) as e: api.get_telemetry(recording.name,1,['speed'],20,80,1)
    assert e.value.code=='distance_reversal'


def test_missing_optional_signals_return_null_metrics(api,recording):
    with duckdb.connect(str(recording)) as c:
        c.execute("DELETE FROM eventsList WHERE eventName='ABS'")
        c.execute('DROP TABLE ABS')
    result=api.get_lap_summary(recording.name,1)
    assert result['abs']['active_time_s'] is None
    assert any('abs' in w for w in result['warnings'])


def test_invalid_comparison_and_partial_interval(api,recording):
    with pytest.raises(InspectionError): api.compare_laps(recording.name,[1,1])
    with pytest.raises(InspectionError): api.compare_laps(recording.name,[1,3])
    with pytest.raises(InspectionError): api.get_telemetry(recording.name,99)


def test_nonfinite_values_serialize_as_null(api,recording):
    with duckdb.connect(str(recording)) as c: c.execute("UPDATE \"Ground Speed\" SET value='NaN'::DOUBLE WHERE rowid=50")
    result=api.get_telemetry(recording.name,1,['speed'],50,52,1)
    assert result['channels']['speed'][0] is None
    json.dumps(result,allow_nan=False)


def test_response_size_limit_is_explicit(api,recording,monkeypatch):
    monkeypatch.setattr('lmu_mcp.config.MAX_OUTPUT_BYTES',100)
    with pytest.raises(InspectionError) as e: api.get_session_info(recording.name)
    assert e.value.code=='response_limit'


def test_all_api_reads_leave_database_unchanged(api,recording):
    digest=hashlib.sha256(recording.read_bytes()).digest()
    api.list_channels(recording.name)
    api.list_laps(recording.name)
    api.get_lap_summary(recording.name,1)
    api.compare_laps(recording.name,[1,2],['speed'],20,80,10)
    assert hashlib.sha256(recording.read_bytes()).digest()==digest


def test_wide_decimal_channel_statistics_are_json_compatible(tmp_path):
    p=tmp_path/'wide.duckdb'
    with duckdb.connect(str(p)) as c:
        c.execute('CREATE TABLE telemetry(time DOUBLE,speed DECIMAL(8,2))')
        c.execute('INSERT INTO telemetry VALUES (0,1.25),(1,3.75)')
    service=TelemetryService(Repository(tmp_path))
    rows=service.list_channels(p.name)['channels']
    speed=next(row for row in rows if row['name']=='speed')
    assert speed['extrema']=={'speed':{'min':1.25,'max':3.75}}
    assert speed['unit'] is None
    json.dumps(rows,allow_nan=False)


def test_malformed_raw_signal_is_not_advertised(api,recording):
    with duckdb.connect(str(recording)) as c:
        c.execute('ALTER TABLE "Brake Pos" ALTER COLUMN value TYPE VARCHAR')
    names=[r['name'] for r in api.list_channels(recording.name)['channels']]
    assert 'brake' not in names and 'Brake Pos' not in names
