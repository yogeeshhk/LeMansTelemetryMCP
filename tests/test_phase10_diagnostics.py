"""Phase 10 diagnostics from deterministic synthetic DuckDB recordings."""
import duckdb
import pytest

from lmu_mcp import cli, diagnostics
from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.diagnostics import diagnose, format_diagnostics


def test_diagnostics_report_bounded_schema_and_benchmark_laps(recording):
    result=diagnose(recording.name, Repository(recording.parent))
    assert result['database_readable'] is True
    assert result['tables_discovered'] == 16
    assert result['channels']['Lap channel'] == 'found'
    assert result['channels']['ABS'] == 'found'
    assert result['detected_laps'] == 3
    assert result['usable_laps'] == 2
    assert result['maximum_sample_frequency_hz'] == 10
    assert 'not officially valid' in result['validity_note']
    text=format_diagnostics(result)
    assert 'Database readable: yes' in text
    assert 'Usable laps: 2' in text
    assert 'Maximum sample frequency: 10 Hz' in text
    assert 'PRIVATE DRIVER' not in text


def test_missing_channels_and_laps_are_explicit(recording):
    with duckdb.connect(str(recording)) as connection:
        connection.execute('DROP TABLE "Brake Pos"')
        connection.execute("DELETE FROM channelsList WHERE channelName='Brake Pos'")
        connection.execute('DROP TABLE "Lap"')
        connection.execute("DELETE FROM eventsList WHERE eventName='Lap'")
    result=diagnose(recording.name, Repository(recording.parent))
    assert result['channels']['Brake'] == 'missing'
    assert result['channels']['Lap channel'] == 'missing'
    assert result['detected_laps'] is None and result['usable_laps'] is None
    assert any('missing_channel' in warning for warning in result['warnings'])
    assert 'Detected laps: unavailable' in format_diagnostics(result)


def test_diagnostics_reject_wal_and_unsafe_path(recording):
    repo=Repository(recording.parent)
    with pytest.raises(InspectionError,match='relative session ID'):
        diagnose(str(recording),repo)
    wal=recording.with_name(recording.name+'.wal')
    wal.write_bytes(b'unfinished')
    with pytest.raises(InspectionError,match='WAL file'):
        diagnose(recording.name,repo)


def test_cli_diagnose_uses_fixed_repository_and_reports_errors(recording,monkeypatch,capsys):
    repo=Repository(recording.parent)
    monkeypatch.setattr(cli,'diagnose',lambda session_id:diagnose(session_id,repo))
    assert cli.main(['diagnose',recording.name])==0
    output=capsys.readouterr().out
    assert 'Tables discovered:' in output and 'Usable laps: 2' in output
    assert cli.main(['diagnose',str(recording)])==2
    error=capsys.readouterr().err
    assert 'relative session ID' in error and str(recording.parent) not in error


def test_schema_failure_is_sanitized(recording,monkeypatch):
    def fail(*args): raise duckdb.Error('internal query detail')
    monkeypatch.setattr(diagnostics,'inspect_connection',fail)
    with pytest.raises(InspectionError,match='schema could not be inspected safely') as caught:
        diagnose(recording.name,Repository(recording.parent))
    assert caught.value.code=='inspection_failed'
    assert 'internal query detail' not in str(caught.value)


def test_lap_query_failure_is_reported_without_internal_details(recording,monkeypatch):
    def fail(*args): raise duckdb.Error('internal query detail')
    monkeypatch.setattr(diagnostics,'Session',fail)
    result=diagnose(recording.name,Repository(recording.parent))
    assert result['database_readable'] is True
    assert result['detected_laps'] is None
    assert any('query_failed' in warning for warning in result['warnings'])
    assert 'internal query detail' not in format_diagnostics(result)
