"""Phase 5 safety controls against synthetic recordings."""
import hashlib

import duckdb
import pytest

from lmu_mcp.database import InspectionError, Repository


def test_original_open_is_read_only_and_extensions_disabled(recording):
    before=hashlib.sha256(recording.read_bytes()).digest()
    with Repository(recording.parent).open(recording.name) as connection:
        for setting in ('enable_external_access','autoload_known_extensions',
                        'autoinstall_known_extensions','allow_unsigned_extensions'):
            assert connection.execute('SELECT current_setting(?)',[setting]).fetchone()[0] is False
        with pytest.raises(duckdb.Error):
            connection.execute('CREATE TABLE phase5_probe(value INTEGER)')
    assert hashlib.sha256(recording.read_bytes()).digest()==before


def test_discovery_is_bounded_and_does_not_return_partial_list(recording, monkeypatch):
    monkeypatch.setattr('lmu_mcp.config.MAX_DISCOVERY_ENTRIES', 1)
    (recording.parent/'other.txt').write_text('unrelated')
    with pytest.raises(InspectionError) as error:
        Repository(recording.parent).discover()
    assert error.value.code == 'discovery_limit'


def test_oversized_explicit_queries_fail_before_opening_database():
    from lmu_mcp.service import TelemetryService

    class NeverOpen:
        def open(self, session_id):
            raise AssertionError('A rejected request opened the recording')

    service = TelemetryService(NeverOpen())
    requests = [
        lambda: service.get_telemetry('race.duckdb',1,['speed']*21,0,100,1),
        lambda: service.get_telemetry('race.duckdb',1,['speed'],0,50000,1),
        lambda: service.get_telemetry('race.duckdb',1,['speed'],0,3000,.5),
        lambda: service.compare_laps('race.duckdb',[1,2],['speed'],0,50000,1),
    ]
    for request in requests:
        with pytest.raises(InspectionError) as error:
            request()
        assert error.value.code == 'query_limit'
        assert 'resolution' in str(error.value) or 'channel' in str(error.value) or 'section' in str(error.value)
