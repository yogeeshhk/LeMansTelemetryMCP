"""Phase 6 wire-format behavior on synthetic telemetry."""
import duckdb
import pytest

from lmu_mcp.database import Repository, inspect_connection
from lmu_mcp.service import TelemetryService
from lmu_mcp.telemetry import Session


def test_display_precision_preserves_granular_distance_and_raw_values(recording):
    with duckdb.connect(str(recording)) as connection:
        connection.execute('UPDATE "Ground Speed" SET value=36.123456 WHERE rowid=50')
        connection.execute('UPDATE "Brake Pos" SET value=33.123456 WHERE rowid=25')
    with Repository(recording.parent).open(recording.name) as connection:
        session=Session(connection, inspect_connection(connection, recording.name))
        assert session.series('speed').values[50] == pytest.approx(36.123456)
        assert session.series('brake').values[25] == pytest.approx(33.123456)
    api=TelemetryService(Repository(recording.parent))
    data=api.get_telemetry(recording.name,1,['speed','brake'],50,50.5,.125)
    assert data['distance_m']==[50,50.125,50.25,50.375,50.5]
    assert data['channels']['speed'][0]==36.1
    assert data['channels']['brake'][0]==33.123
    assert data['elapsed_s'][1]==5.013
    assert len(set(data['distance_m']))==5
    comparison=api.compare_laps(recording.name,[1,2],['speed'],50,51,1)
    assert comparison['deltas'][0]['speed_delta_a_minus_b_kph'][0]==6.1
    assert comparison['deltas'][0]['elapsed_delta_a_minus_b_s'][0]==-1.0
    assert api.get_lap_summary(recording.name,1)['max_speed_kph']==36.1
