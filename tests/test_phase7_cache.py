"""Process-cache behavior against temporary read-only recordings."""
from collections import Counter
import os
from pathlib import Path

import duckdb
import pytest

from lmu_mcp.cache import AnalysisCache
from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService
import lmu_mcp.service as service_module


def test_schema_and_lap_cache_reuse_and_revision_invalidation(recording,monkeypatch):
    counts=Counter()
    original_inspect=service_module.inspect_connection
    original_laps=service_module.identify_laps
    def inspect(*args):
        counts['inspection']+=1
        return original_inspect(*args)
    def laps(*args):
        counts['laps']+=1
        return original_laps(*args)
    monkeypatch.setattr(service_module,'inspect_connection',inspect)
    monkeypatch.setattr(service_module,'identify_laps',laps)
    api=TelemetryService(Repository(recording.parent))
    assert api.get_session_info(recording.name)['number_of_laps']==2
    assert api.list_laps(recording.name)['laps'][0]['lap_time_s']==10
    assert api.get_lap_summary(recording.name,1)['lap_time_s']==10
    assert counts=={'inspection':1,'laps':1}
    with duckdb.connect(str(recording)) as connection:
        connection.execute('UPDATE "Lap Time" SET value=9.9 WHERE ts=10')
    stat=recording.stat()
    os.utime(recording,ns=(stat.st_atime_ns,stat.st_mtime_ns+1_000_000_000))
    assert api.list_laps(recording.name)['laps'][0]['lap_time_s']==9.9
    assert counts=={'inspection':2,'laps':2}


def test_wal_failure_is_not_cached(recording):
    api=TelemetryService(Repository(recording.parent))
    assert api.get_session_info(recording.name)['number_of_laps']==2
    wal=Path(str(recording)+'.wal')
    wal.write_bytes(b'active recording')
    with pytest.raises(InspectionError) as error:
        api.get_session_info(recording.name)
    assert error.value.code=='wal_present'
    wal.unlink()
    assert api.get_session_info(recording.name)['number_of_laps']==2


def test_cache_is_lru_bounded_and_clears_changed_revision(monkeypatch):
    monkeypatch.setattr('lmu_mcp.config.MAX_CACHE_ENTRIES',2)
    monkeypatch.setattr('lmu_mcp.config.MAX_CACHE_BYTES',1024)
    cache=AnalysisCache()
    cache.activate('race',(1,))
    cache.put('race',(1,),'schema',{'a':1})
    cache.put('race',(1,),'laps',{'b':2})
    assert cache.get('race',(1,),'schema')=={'a':1}
    cache.put('race',(1,),'path',{'c':3})
    assert cache.entry_count==2 and cache.size_bytes<=1024
    assert cache.get('race',(1,),'laps') is None
    cache.activate('race',(2,))
    assert cache.entry_count==0 and cache.get('race',(1,),'schema') is None
    cache.put('race',(1,),'schema',{'stale':True})
    assert cache.entry_count==0
