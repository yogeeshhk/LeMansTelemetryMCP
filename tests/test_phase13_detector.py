"""Synthetic corner-range detector cases."""
import numpy as np
import pytest
from lmu_mcp.analysis.corners import detect_corner_ranges
from lmu_mcp.database import InspectionError


def traces():
    distance=np.arange(0,301,5,dtype=float)
    steering=np.zeros(len(distance))
    lateral=np.zeros(len(distance))
    speed=np.full(len(distance),120.0)
    for start,end,minimum in [(50,90,60),(180,220,80)]:
        inside=(distance>=start)&(distance<=end)
        steering[inside]=12
        lateral[inside]=.4
        speed[inside]=minimum+((distance[inside]-(start+end)/2)/20)**2*(100-minimum)
    steering[distance==130]=20
    lateral[distance==130]=.5
    return distance,steering,lateral,speed


def test_detects_two_unnamed_ranges_and_rejects_tiny_spike():
    rows=detect_corner_ranges(*traces())
    assert len(rows)==2
    assert [r['corner_id'] for r in rows]==[1,2]
    assert all(r['name'] is None and r['source']=='automatic' for r in rows)
    assert rows[0]['start_distance_m']==40
    assert rows[0]['apex_distance_m']==70
    assert rows[0]['end_distance_m']==100
    assert rows[0]['minimum_speed_kph']==60


def test_missing_samples_are_not_bridged():
    distance,steering,lateral,speed=traces()
    lateral[(distance>=65)&(distance<=75)]=np.nan
    rows=detect_corner_ranges(distance,steering,lateral,speed)
    assert all(not (r['start_distance_m']<65 and r['end_distance_m']>75) for r in rows)


def test_short_observed_hole_is_joined_but_large_hole_is_not():
    distance,steering,lateral,speed=traces()
    steering[distance==70]=0
    rows=detect_corner_ranges(distance,steering,lateral,speed)
    assert len(rows)==2
    steering[(distance>=65)&(distance<=80)]=0
    rows=detect_corner_ranges(distance,steering,lateral,speed)
    assert all(not (r['start_distance_m']<65 and r['end_distance_m']>80) for r in rows)


def test_invalid_distance_and_missing_values_fail_conservatively():
    distance,steering,lateral,speed=traces()
    with pytest.raises(InspectionError,match='increasing finite distances'):
        detect_corner_ranges(distance[::-1],steering,lateral,speed)
    with pytest.raises(InspectionError,match='at most 20'):
        detect_corner_ranges(np.array([0,30]),np.array([0,10]),np.array([0,.4]),np.array([100,80]))
