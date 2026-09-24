"""Synthetic time-domain braking detection and track-position matching."""
import numpy as np
import pytest

from lmu_mcp.analysis.braking import BrakingSettings, detect_intervals, match_positions
from lmu_mcp.database import InspectionError


def test_hysteresis_detects_one_zone_and_excludes_tiny_tap():
    times=np.arange(0,3.2,.2)
    brake=np.zeros(len(times))
    brake[2]=30  # one-sample tap, 0.2 s to release
    brake[6:11]=[12,40,80,30,6]
    brake[11]=4  # release below 5%, after a 1 s interval
    zones=detect_intervals(times,brake,.3,BrakingSettings())
    assert len(zones)==1
    zone=zones[0]
    assert zone['start_time_s']==pytest.approx(1.2)
    assert zone['end_time_s']==pytest.approx(2.2)
    assert zone['peak_brake_pct']==80
    assert zone['onset_observed'] and zone['release_observed']


def test_missing_sample_and_large_gap_do_not_join_braking():
    settings=BrakingSettings(min_duration_s=.1)
    times=np.array([0,.2,.4,.6,.8,1.0,1.2,2.0,2.2,2.4,2.6])
    brake=np.array([0,40,40,np.nan,0,40,40,40,40,0,0])
    zones=detect_intervals(times,brake,.3,settings)
    assert len(zones)==3
    assert not zones[0]['release_observed']
    assert zones[0]['end_time_s']==pytest.approx(.4)
    assert zones[1]['start_time_s']==pytest.approx(1.0)
    assert zones[1]['end_time_s']==pytest.approx(1.2)
    assert not zones[1]['release_observed']
    assert zones[2]['start_time_s']==pytest.approx(2.0)
    assert zones[2]['release_observed'] and not zones[2]['onset_observed']


def test_invalid_thresholds_and_samples_are_rejected():
    with pytest.raises(InspectionError,match='release_pct'):
        BrakingSettings(onset_pct=5,release_pct=10).validate()
    with pytest.raises(InspectionError,match='finite numbers'):
        BrakingSettings(onset_pct=float('nan')).validate()
    with pytest.raises(InspectionError,match='increasing'):
        detect_intervals([0,.2,.1],[0,30,0],.3,BrakingSettings())
    with pytest.raises(InspectionError,match='between 0 and 100'):
        detect_intervals([0,.2,.4],[0,130,0],.3,BrakingSettings())


def test_matching_skips_extra_zone_and_prefers_track_order():
    a=[{'start_distance_m':v} for v in (100,300,500)]
    b=[{'start_distance_m':v} for v in (105,200,310,495)]
    pairs,unmatched_a,unmatched_b=match_positions(a,b,50)
    assert pairs==[(0,0),(1,2),(2,3)]
    assert unmatched_a==[] and unmatched_b==[1]
    with pytest.raises(InspectionError,match='10 to 300'):
        match_positions(a,b,500)
