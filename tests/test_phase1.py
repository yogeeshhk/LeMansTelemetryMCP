import hashlib
import json
from pathlib import Path
import subprocess
import sys

import duckdb
import pytest

from lmu_mcp.database import InspectionError, Repository, inspect_connection
from lmu_mcp.schema import ALIASES


def make_lmu(path):
    with duckdb.connect(str(path)) as c:
        c.execute("CREATE TABLE channelsList(channelName VARCHAR,frequency INTEGER,unit VARCHAR)")
        c.execute("CREATE TABLE eventsList(eventName VARCHAR,unit VARCHAR)")
        c.execute("CREATE TABLE metadata(key VARCHAR,value VARCHAR)")
        c.execute("INSERT INTO metadata VALUES ('DriverName','private identity')")
        for name, hz, unit in [('GPS Time',100,'s'),('Ground Speed',100,'km/h'),('Brake Pos',50,'%'),('Brake Pos Unfiltered',50,'%')]:
            c.execute('INSERT INTO channelsList VALUES (?,?,?)',[name,hz,unit])
            c.execute('CREATE TABLE "'+name+'"(value DOUBLE)')
            c.execute('INSERT INTO "'+name+'" VALUES (0),(1)')
        c.execute("INSERT INTO eventsList VALUES ('Lap',''),('ABS','')")
        c.execute('CREATE TABLE Lap(ts DOUBLE,value USMALLINT)')
        c.execute('INSERT INTO Lap VALUES (0,0),(10,1)')
        c.execute('CREATE TABLE ABS(ts DOUBLE,value BOOLEAN)')
        c.execute('INSERT INTO ABS VALUES (0,false),(1,true)')


def test_catalog_mapping_preserves_sources_units_and_missing(tmp_path):
    path=tmp_path/'race.duckdb'; make_lmu(path)
    result=Repository(tmp_path).inspect(path.name)
    speed=result.channels.channels['speed']
    assert (speed.table,speed.value_columns,speed.unit,speed.frequency_hz)==('Ground Speed',('value',),'km/h',100)
    assert result.channels.channels['brake'].table=='Brake Pos'
    assert result.channels.channels['abs'].timestamp_column=='ts'
    assert result.channels.channels['abs'].kind=='event'
    assert result.channels.channels['yaw_rate'] is None
    assert 'yaw_rate' in result.channels.missing
    assert 'private identity' not in json.dumps(result.to_dict())
    assert next(t for t in result.tables if t.name=='Ground Speed').samples==((0.0,),(1.0,))


def test_wide_alternate_names_do_not_invent_units():
    with duckdb.connect() as c:
        c.execute('CREATE TABLE telemetry(session_time DOUBLE,lap_index INTEGER,lap_distance_m DOUBLE,vehicle_speed DOUBLE,brake_position DOUBLE,extra_unknown DOUBLE)')
        c.execute('INSERT INTO telemetry VALUES (1,1,10,90,0,7)')
        result=inspect_connection(c)
    src=result.channels.channels['speed']
    assert src.value_columns==('vehicle_speed',)
    assert src.timestamp_column=='session_time'
    assert src.unit is None and src.frequency_hz is None
    assert 'extra_unknown' not in result.channels.channels


def test_ambiguous_names_are_not_silently_selected():
    with duckdb.connect() as c:
        c.execute('CREATE TABLE telemetry(time DOUBLE,speed DOUBLE,ground_speed DOUBLE)')
        result=inspect_connection(c)
    assert result.channels.channels['speed'] is None
    assert len(result.channels.ambiguous['speed'])==2
    assert 'speed' not in result.channels.missing


def test_multiple_clocks_are_ambiguous():
    with duckdb.connect() as c:
        c.execute('CREATE TABLE telemetry(time DOUBLE,ts DOUBLE,speed DOUBLE)')
        result=inspect_connection(c)
    assert result.channels.channels['speed'].timestamp_column is None
    assert 'timestamp' in result.channels.ambiguous
    assert any('Ambiguous time' in w for w in result.warnings)


def test_view_definitions_are_not_executed():
    with duckdb.connect() as c:
        c.execute("CREATE VIEW dangerous AS SELECT error('view was executed') AS speed")
        result=inspect_connection(c)
    assert result.tables[0].kind=='VIEW'
    assert result.tables[0].row_count is None and result.tables[0].samples==()
    assert result.channels.channels['speed'] is None


def test_discovery_is_recursive_fresh_and_isolates_wal(tmp_path):
    nested=tmp_path/'weekend'; nested.mkdir()
    make_lmu(nested/'one.DUCKDB')
    repo=Repository(tmp_path)
    assert [r['session_id'] for r in repo.discover()]==['weekend/one.DUCKDB']
    make_lmu(tmp_path/'two.duckdb')
    (tmp_path/'two.duckdb.wal').write_bytes(b'not a real WAL')
    assert len(repo.discover())==2
    with pytest.raises(InspectionError) as err: repo.inspect('two.duckdb')
    assert err.value.code=='wal_present'
    assert repo.inspect('weekend/one.DUCKDB').channels.channels['speed'] is not None
    assert (tmp_path/'two.duckdb.wal').read_bytes()==b'not a real WAL'


@pytest.mark.parametrize('sid',['../outside.duckdb','sub/../../outside.duckdb','missing.duckdb','file.txt'])
def test_path_confinement(tmp_path,sid):
    with pytest.raises(InspectionError) as err: Repository(tmp_path).inspect(sid)
    assert err.value.code=='invalid_session'


def test_absolute_paths_rejected_even_inside_root(tmp_path):
    p=tmp_path/'one.duckdb'; make_lmu(p)
    with pytest.raises(InspectionError): Repository(tmp_path).inspect(str(p))


def test_junction_escape_is_not_discovered_or_opened(tmp_path):
    root=tmp_path/'root'; outside=tmp_path/'outside'; root.mkdir(); outside.mkdir()
    make_lmu(outside/'outside.duckdb')
    link=root/'escape'
    if sys.platform=='win32':
        completed=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        assert completed.returncode==0,completed.stderr.decode(errors='replace')
    else:
        link.symlink_to(outside,target_is_directory=True)
    try:
        assert Repository(root).discover()==[]
        with pytest.raises(InspectionError): Repository(root).inspect('escape/outside.duckdb')
    finally:
        if sys.platform=='win32': link.rmdir()  # Remove only this junction, never its contents.
        else: link.unlink()
    assert (outside/'outside.duckdb').exists()


def test_missing_root(tmp_path):
    with pytest.raises(InspectionError) as err: Repository(tmp_path/'missing').discover()
    assert err.value.code=='directory_unavailable'


def test_corrupt_database_reported_without_raw_exception(tmp_path):
    (tmp_path/'bad.duckdb').write_bytes(b'broken')
    with pytest.raises(InspectionError) as err: Repository(tmp_path).inspect('bad.duckdb')
    assert err.value.code=='database_unavailable'
    assert str(tmp_path) not in str(err.value)


def test_original_database_unchanged_and_writes_rejected(tmp_path):
    p=tmp_path/'one.duckdb'; make_lmu(p)
    before=hashlib.sha256(p.read_bytes()).digest()
    repo=Repository(tmp_path)
    repo.inspect(p.name)
    with repo.open(p.name) as c:
        with pytest.raises(duckdb.Error): c.execute('CREATE TABLE forbidden(x INT)')
    assert hashlib.sha256(p.read_bytes()).digest()==before
    assert not Path(str(p)+'.wal').exists()


def test_invalid_frequency_and_missing_event_time(tmp_path):
    p=tmp_path/'one.duckdb'; make_lmu(p)
    with duckdb.connect(str(p)) as c:
        c.execute("UPDATE channelsList SET frequency=-1 WHERE channelName='Ground Speed'")
        c.execute('ALTER TABLE ABS DROP COLUMN ts')
    result=Repository(tmp_path).inspect(p.name)
    assert result.channels.channels['speed'].frequency_hz is None
    assert result.channels.channels['abs'] is None
    assert any('Invalid sample frequency' in w for w in result.warnings)
    assert any('Missing numeric event timestamp' in w for w in result.warnings)


def test_unknown_schema_still_has_inventory():
    with duckdb.connect() as c:
        c.execute('CREATE TABLE unknown(foo VARCHAR)')
        result=inspect_connection(c)
    assert len(result.tables)==1
    assert set(result.channels.missing)==set(ALIASES)
    assert any('Unsupported' in w for w in result.warnings)


def test_identifier_quoting_and_separator_alias():
    with duckdb.connect() as c:
        c.execute('CREATE SCHEMA "a""b"')
        c.execute('CREATE TABLE "a""b"."odd""name"("GROUND_SPEED" DOUBLE)')
        result=inspect_connection(c)
    assert result.channels.channels['speed'].table=='odd"name'
    assert result.channels.channels['speed'].schema=='a"b'


def test_duplicate_catalog_is_explicit(tmp_path):
    p=tmp_path/'one.duckdb'; make_lmu(p)
    with duckdb.connect(str(p)) as c: c.execute("INSERT INTO channelsList VALUES ('Ground Speed',100,'km/h')")
    with pytest.raises(InspectionError) as err: Repository(tmp_path).inspect(p.name)
    assert err.value.code=='ambiguous_catalog'


def test_locked_database_does_not_block_other_recordings(tmp_path):
    p=tmp_path/'locked.duckdb'; make_lmu(p)
    make_lmu(tmp_path/'readable.duckdb')
    script='import duckdb,sys; c=duckdb.connect(sys.argv[1]); print("ready",flush=True); sys.stdin.readline()'
    process=subprocess.Popen([sys.executable,'-c',script,str(p)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        assert process.stdout.readline().strip()=='ready'
        assert len(Repository(tmp_path).discover())==2
        with pytest.raises(InspectionError) as err: Repository(tmp_path).inspect(p.name)
        assert err.value.code in {'database_unavailable','wal_present'}
        assert Repository(tmp_path).inspect('readable.duckdb').channels.channels['speed'] is not None
    finally:
        process.communicate('\n',timeout=10)


def test_four_component_signal_preserves_unverified_order(tmp_path):
    p=tmp_path/'one.duckdb'; make_lmu(p)
    with duckdb.connect(str(p)) as c:
        c.execute("INSERT INTO channelsList VALUES ('Wheel Speed',100,'m/s')")
        c.execute('CREATE TABLE "Wheel Speed"(value1 FLOAT,value2 FLOAT,value3 FLOAT,value4 FLOAT)')
    source=Repository(tmp_path).inspect(p.name).channels.channels['wheel_speeds']
    assert source.value_columns==('value1','value2','value3','value4')
    assert source.unit=='m/s'


def test_catalog_view_cannot_supply_mappings():
    with duckdb.connect() as c:
        c.execute("CREATE VIEW channelsList AS SELECT error('executed') AS channelName,100 AS frequency,'km/h' AS unit")
        result=inspect_connection(c)
    assert result.catalog=={}
    assert result.channels.channels['speed'] is None
