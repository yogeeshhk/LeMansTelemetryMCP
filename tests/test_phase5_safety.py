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
