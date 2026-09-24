"""Opt-in read-only smoke test for the supplied private LMU recording."""
import hashlib
import os
from pathlib import Path

import pytest

from lmu_mcp.config import TELEMETRY_ROOT
from lmu_mcp.service import TelemetryService


@pytest.mark.skipif(os.environ.get('LMU_RUN_REAL_SMOKE') != '1',
                    reason='Set LMU_RUN_REAL_SMOKE=1 to check the supplied private recording')
def test_supplied_recording_stays_unchanged():
    session_id='Circuit de la Sarthe_R_2026-09-22T17_46_50Z.duckdb'
    path=TELEMETRY_ROOT/session_id
    assert path.is_file(), 'Supplied LMU recording is unavailable at the fixed telemetry path.'
    wal=Path(str(path)+'.wal')
    assert not wal.exists(), 'Close LMU cleanly before running this read-only smoke test.'
    def snapshot():
        stat=path.stat()
        return hashlib.sha256(path.read_bytes()).digest(),stat.st_size,stat.st_mtime_ns,wal.exists()
    before=snapshot()
    api=TelemetryService()
    info=api.get_session_info(session_id)
    laps=api.list_laps(session_id)['laps']
    candidates=[lap for lap in laps if lap['benchmark_candidate']]
    assert info['number_of_laps']>=1 and candidates
    lap=candidates[0]['lap']
    assert api.get_lap_summary(session_id,lap)['lap_time_s']>0
    first=api.get_telemetry(session_id,lap,['speed'],0,100,2)
    second=api.get_telemetry(session_id,lap,['speed'],0,100,2)
    assert first==second and len(first['distance_m'])==51
    assert first['units']['speed'] in ('km/h','m/s')
    assert snapshot()==before
