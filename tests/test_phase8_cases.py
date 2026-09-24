"""Additional milestone-one behavior checks with synthetic LMU recordings."""
import os
from pathlib import Path
from types import SimpleNamespace

import duckdb
import numpy as np
import pytest

from lmu_mcp.analysis.summary import control_transitions, match_onsets
from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService
from lmu_mcp.telemetry import Series


def test_mixed_rate_interpolation_discrete_hold_and_missing_sample(recording):
    with duckdb.connect(str(recording)) as connection:
        connection.execute('UPDATE "Ground Speed" SET value=40 WHERE rowid=50')
        connection.execute('UPDATE "Ground Speed" SET value=50 WHERE rowid=51')
        connection.execute('UPDATE "Brake Pos" SET value=20 WHERE rowid=25')
        connection.execute('UPDATE "Brake Pos" SET value=60 WHERE rowid=26')
    api=TelemetryService(Repository(recording.parent))
    result=api.get_telemetry(recording.name,1,['speed','brake','gear'],50,51,.5)
    assert result['distance_m']==[50,50.5,51]
    assert result['elapsed_s']==[5,5.05,5.1]
    assert result['channels']['speed']==[40,45,50]
    assert result['channels']['brake']==[20,30,40]
    assert result['channels']['gear']==[2,2,2]
    assert result['interpolation']['gear']=='previous state hold'
    with duckdb.connect(str(recording)) as connection:
        connection.execute('UPDATE "Ground Speed" SET value=CAST(? AS DOUBLE) WHERE rowid=51',['NaN'])
    stat=recording.stat()
    os.utime(recording,ns=(stat.st_atime_ns,stat.st_mtime_ns+1_000_000_000))
    missing=api.get_telemetry(recording.name,1,['speed'],50,51,.5)
    assert missing['channels']['speed']==[40,None,None]


def test_basic_brake_count_ignores_light_tap_and_merges_subpeaks(recording):
    # Ten-hertz controls resolve a 0.1 s tap below the documented 0.15 s minimum.
    with duckdb.connect(str(recording)) as connection:
        connection.execute('DELETE FROM "Brake Pos"')
        connection.execute("UPDATE channelsList SET frequency=10 WHERE channelName='Brake Pos'")
        rows=[]
        for n in range(231):
            time=n/10
            value=80 if 0<=time<.3 else 80 if 2<=time<2.5 else 30 if 2.5<=time<3 else 8 if time==4 else 0
            rows.append((value,))
        connection.executemany('INSERT INTO "Brake Pos" VALUES (?)',rows)
    summary=TelemetryService(Repository(recording.parent)).get_lap_summary(recording.name,1)
    assert summary['braking_events']==2  # Initial partial application and the two-peak event.
    assert summary['braking_time_pct']==14
    assert summary['braking_coverage_s']==10


def test_paginated_session_discovery(recording):
    copy=recording.parent/'other.duckdb'
    copy.write_bytes(recording.read_bytes())
    api=TelemetryService(Repository(recording.parent))
    first=api.list_sessions(limit=1)
    second=api.list_sessions(offset=first['next_offset'],limit=1)
    assert first['total']==second['total']==2
    assert first['next_offset']==1 and second['next_offset'] is None
    assert first['sessions'][0]['session_id']!=second['sessions'][0]['session_id']


def test_coarse_control_onset_truncation_is_explicit():
    times=np.arange(120,dtype=float)/10
    values=np.tile([0,10],60)
    signal=Series(times,values,'%',False,.2,'synthetic')
    session=SimpleNamespace(series=lambda name:signal)
    lap={'start_s':0,'end_s':12}
    path=(np.array([0,12],dtype=float),np.array([0,120],dtype=float),.2)
    result=control_transitions(session,lap,path,0,120)
    assert result['brake']['total']==60
    assert len(result['brake']['distances_m'])==50
    assert result['brake']['truncated'] is True
    assert match_onsets(result,result)['brake']['input_truncated'] is True


def test_file_symlink_escape_is_excluded_when_supported(tmp_path,recording):
    root=tmp_path/'root'
    root.mkdir()
    link=root/'escape.duckdb'
    try:
        link.symlink_to(recording)
    except (OSError,NotImplementedError):
        pytest.skip('file symlinks unavailable on this Windows account')
    repo=Repository(root)
    assert repo.discover()==[]
    with pytest.raises(InspectionError) as error:
        with repo.open(link.name):
            pass
    assert error.value.code=='invalid_session'
