import numpy as np
import duckdb
import pytest
from lmu_mcp.database import InspectionError
from lmu_mcp.analysis.laps import identify_laps, select_lap


def test_clock_stride_and_discrete_events(recording,open_session):
    with open_session(recording) as session:
        assert session.series('brake').times[:3]==pytest.approx([0,.2,.4])
        assert session.sample('gear',[4.9,5,5.1])==pytest.approx([1,2,2])
        assert session.sample('abs',[2.9,3,4])==pytest.approx([0,1,0])
        assert session.series('speed').unit=='km/h'
        assert 'inferred' in session.series('speed').timing
        assert 'DriverName' not in session.metadata


def test_laps_reported_and_incomplete_tail(recording,open_session):
    with open_session(recording) as session:
        laps=identify_laps(session)
    assert [r['lap_time_s'] for r in laps]==[10,12,None]
    assert [r['benchmark_candidate'] for r in laps]==[True,True,False]
    assert all(r['valid'] is None for r in laps)
    assert laps[-1]['flags']==['incomplete_final_interval']


def test_zero_time_not_valid_benchmark(recording,open_session):
    with duckdb.connect(str(recording)) as c: c.execute('UPDATE "Lap Time" SET value=0 WHERE ts=22')
    with open_session(recording) as s:
        row=select_lap(s,2)
    assert row['lap_time_s'] is None and row['boundary_duration_s']==12
    assert not row['benchmark_candidate']


def test_lap_reset_keeps_unique_ids_and_partial_interval(recording,open_session):
    with duckdb.connect(str(recording)) as c: c.execute('UPDATE Lap SET value=0 WHERE ts=22')
    with open_session(recording) as s: rows=identify_laps(s)
    assert [r['lap'] for r in rows]==[1,2,3]
    assert 'counter_reset_or_jump' in rows[1]['flags']
    assert not rows[1]['complete']


def test_first_partial_lap_is_not_completed_by_guessing(recording,open_session):
    with duckdb.connect(str(recording)) as c: c.execute('UPDATE "Lap Time" SET value=15 WHERE ts=10')
    with open_session(recording) as s: row=select_lap(s,1)
    assert 'first_interval_start_unverified' in row['flags']
    assert 'lap_clock_disagreement' in row['flags']


def test_mismatched_counts_rejected(recording,open_session):
    with duckdb.connect(str(recording)) as c: c.execute('DELETE FROM "Brake Pos" WHERE rowid=0')
    with open_session(recording) as s:
        with pytest.raises(InspectionError,match='sample count'): s.series('brake')


def test_unsupported_frequency_rejected(recording,open_session):
    with duckdb.connect(str(recording)) as c: c.execute("UPDATE channelsList SET frequency=7 WHERE channelName='Brake Pos'")
    with open_session(recording) as s:
        with pytest.raises(InspectionError,match='integer clock stride'): s.series('brake')


def test_clock_gap_is_not_bridged(recording,open_session):
    with duckdb.connect(str(recording)) as c: c.execute('UPDATE "GPS Time" SET value=value+1 WHERE value>=8')
    with open_session(recording) as s:
        assert np.isnan(s.sample('speed',[8.2])[0])
        assert np.isnan(s.sample('gear',[8.2])[0])
        assert 'clock_gap' in select_lap(s,1)['flags']


def test_missing_and_reversed_clock(recording,open_session):
    with duckdb.connect(str(recording)) as c: c.execute('UPDATE "GPS Time" SET value=-1 WHERE rowid=2')
    with open_session(recording) as s:
        with pytest.raises(InspectionError,match='strictly increasing'): s.clock


def test_budget_rejected_before_signal_materialization(recording,open_session,monkeypatch):
    monkeypatch.setattr('lmu_mcp.config.MAX_SOURCE_SAMPLES',10)
    with open_session(recording) as s:
        with pytest.raises(InspectionError) as err: s.clock
    assert err.value.code=='source_limit'
