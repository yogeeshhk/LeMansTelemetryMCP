import json

import duckdb
import pytest

from lmu_mcp.database import Repository, InspectionError
from lmu_mcp.manual_corners import load_manual_corners
from lmu_mcp.service import TelemetryService


def service(recording):
    return TelemetryService(Repository(recording.parent))


def test_automatic_corner_metrics_and_comparison(corner_recording):
    recording=corner_recording
    api=service(recording)
    first=api.get_corners(recording.name,1)
    assert first['definition_source']=='automatic'
    assert first['total']==1
    corner=first['corners'][0]
    assert corner['corner_id']==1
    assert corner['start_distance_m'] <= 30 < corner['end_distance_m']
    assert 40 <= corner['minimum_speed_position_m'] <= 50
    assert 30 <= corner['minimum_speed_kph'] <= 32
    assert corner['entry_speed_kph'] > corner['minimum_speed_kph']
    assert corner['exit_speed_kph'] > corner['minimum_speed_kph']
    assert corner['brake_point_m'] is not None
    assert corner['turn_in_position_m'] is not None
    assert corner['throttle_pickup_position_m'] is not None
    assert corner['full_throttle_position_m'] is not None
    assert corner['section_time_s'] > 0
    assert corner['maximum_absolute_steering_pct']==20
    assert corner['quality_flags']==[]
    assert api.get_corners(recording.name,1,offset=1)['corners']==[]
    comparison=api.compare_corner(recording.name,1,[1,2])
    assert comparison['unmatched_laps']==[]
    assert comparison['comparisons'][0]['match_method']=='nearest_start_within_100_m'
    assert 1 <= comparison['comparisons'][0]['lap_minus_reference']['minimum_speed_kph'] <= 3
    assert comparison['comparisons'][0]['lap_minus_reference']['section_time_s'] > 0


def test_manual_override_and_outside_coverage(recording,tmp_path,monkeypatch):
    directory=tmp_path/'definitions'
    directory.mkdir()
    definition={'track':'Synthetic','layout':'Test','corners':[
        {'corner_id':7,'name':'Hairpin','start_distance_m':20,'apex_distance_m':45,'end_distance_m':70},
        {'corner_id':9,'name':'Beyond lap','start_distance_m':110,'end_distance_m':130}]}
    (directory/'synthetic.json').write_text(json.dumps(definition),encoding='utf-8')
    monkeypatch.setattr('lmu_mcp.service.load_manual_corners',lambda track,layout:load_manual_corners(track,layout,directory))
    api=service(recording)
    result=api.get_corners(recording.name,1)
    assert result['definition_source']=='manual'
    assert result['total']==2
    assert result['corners'][0]['name']=='Hairpin'
    assert result['corners'][0]['apex_distance_m']==45
    assert result['corners'][1]['quality_flags']==['outside_lap_distance_coverage']
    assert result['corners'][1]['minimum_speed_kph'] is None
    assert api.compare_corner(recording.name,7,[1,2])['comparisons'][0]['match_method']=='manual_id'
    definition['corners'][0]['name']='Renamed'
    (directory/'synthetic.json').write_text(json.dumps(definition),encoding='utf-8')
    assert api.get_corners(recording.name,1)['corners'][0]['name']=='Renamed'


def test_corner_request_errors(recording):
    api=service(recording)
    with pytest.raises(InspectionError,match='lateral_acceleration'):
        api.get_corners(recording.name,1)
    with pytest.raises(InspectionError,match='offset'):
        api.get_corners(recording.name,1,offset=-1)
    with pytest.raises(InspectionError,match='distinct'):
        api.compare_corner(recording.name,1,[1,1])


def test_automatic_corners_allow_small_negative_recorded_lap_start(corner_recording):
    recording=corner_recording
    with duckdb.connect(str(recording)) as connection:
        connection.execute('UPDATE "Lap Dist" SET value=-2.3 WHERE rowid=100')
    api=service(recording)
    corners=api.get_corners(recording.name,2)
    assert corners['total']==1
    assert corners['corners'][0]['start_distance_m']>=0
    comparison=api.compare_corner(recording.name,1,[1,2])
    assert len(comparison['comparisons'])==1
