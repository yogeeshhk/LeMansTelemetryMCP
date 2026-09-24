import numpy as np
import duckdb
import pytest
from contextlib import contextmanager
from lmu_mcp.database import Repository, inspect_connection
from lmu_mcp.telemetry import Session


@pytest.fixture
def recording(tmp_path):
    path=tmp_path/'race.duckdb'
    with duckdb.connect(str(path)) as c:
        c.execute('BEGIN TRANSACTION')
        c.execute('CREATE TABLE channelsList(channelName VARCHAR,frequency INTEGER,unit VARCHAR)')
        c.execute('CREATE TABLE eventsList(eventName VARCHAR,unit VARCHAR)')
        c.execute('CREATE TABLE metadata(key VARCHAR,value VARCHAR)')
        c.executemany('INSERT INTO metadata VALUES (?,?)',[('Version','1'),('TrackName','Synthetic'),('TrackLayout','Test'),('CarName','Test car'),('CarClass','Test'),('DriverName','PRIVATE DRIVER')])
        def sampled(name,hz,unit,fn,typ='DOUBLE'):
            c.execute('INSERT INTO channelsList VALUES (?,?,?)',[name,hz,unit])
            c.execute('CREATE TABLE "'+name+'"(value '+typ+')')
            times=np.arange(0,230+1,10/hz)/10
            c.executemany('INSERT INTO "'+name+'" VALUES (?)',[(fn(float(t)),) for t in times])
        def local(t): return t if t<10 else (t-10)/1.2 if t<22 else t-22
        sampled('GPS Time',10,'s',lambda t:t)
        sampled('Lap Dist',10,'m',lambda t:local(t)*10)
        sampled('Ground Speed',10,'km/h',lambda t:36 if t<10 else 30)
        sampled('Brake Pos',5,'%',lambda t:100 if 2<=local(t)<4 else 0)
        sampled('Throttle Pos',5,'%',lambda t:0 if 2<=local(t)<4 else 100)
        sampled('Steering Pos',10,'%',lambda t:np.sin(t))
        sampled('TC',10,'',lambda t:6<=local(t)<7,'BOOLEAN')
        def event(name,rows,unit='',typ='DOUBLE'):
            c.execute('INSERT INTO eventsList VALUES (?,?)',[name,unit])
            c.execute('CREATE TABLE "'+name+'"(ts DOUBLE,value '+typ+')')
            c.executemany('INSERT INTO "'+name+'" VALUES (?,?)',rows)
        event('Lap',[(0,0),(10,1),(22,2)],typ='INTEGER')
        event('Lap Time',[(0,0),(10,10),(22,12)],unit='s')
        event('Gear',[(0,1),(5,2),(15,3)],typ='INTEGER')
        event('ABS',[(0,False),(3,True),(4,False)],typ='BOOLEAN')
        event('In Pits',[(0,0)],typ='INTEGER')
        event('Finish Status',[(0,0)],typ='INTEGER')
        c.execute('COMMIT')
    return path


@pytest.fixture
def open_session():
    @contextmanager
    def factory(path):
        with Repository(path.parent).open(path.name) as c:
            yield Session(c,inspect_connection(c,path.name))
    return factory


def add_corners(recording):
    with duckdb.connect(str(recording)) as connection:
        connection.execute("INSERT INTO channelsList VALUES ('G Force Lat',10,'G')")
        connection.execute('CREATE TABLE "G Force Lat"(value DOUBLE)')
        connection.execute('INSERT INTO "G Force Lat" SELECT CASE WHEN ((rowid / 10.0 < 10 AND rowid / 10.0 BETWEEN 3 AND 6) OR (rowid / 10.0 >= 10 AND (rowid / 10.0 - 10) / 1.2 BETWEEN 3 AND 6)) THEN 0.5 ELSE 0 END FROM "GPS Time"')
        connection.execute('UPDATE "Steering Pos" SET value=CASE WHEN ((rowid / 10.0 < 10 AND rowid / 10.0 BETWEEN 3 AND 6) OR (rowid / 10.0 >= 10 AND (rowid / 10.0 - 10) / 1.2 BETWEEN 3 AND 6)) THEN 20 ELSE 0 END')
        connection.execute('UPDATE "Ground Speed" SET value=CASE WHEN rowid / 10.0 < 10 THEN 50 - 20 * greatest(0, 1 - abs(rowid / 10.0 - 4.5) / 1.5) ELSE 48 - 16 * greatest(0, 1 - abs((rowid / 10.0 - 10) / 1.2 - 4.5) / 1.5) END')
        connection.execute('UPDATE "Throttle Pos" SET value=CASE WHEN rowid / 5.0 < 10 THEN CASE WHEN rowid / 5.0 < 5 THEN 0 ELSE 100 END ELSE CASE WHEN (rowid / 5.0 - 10) / 1.2 < 5 THEN 0 ELSE 100 END END')


@pytest.fixture
def corner_recording(recording):
    add_corners(recording)
    return recording
