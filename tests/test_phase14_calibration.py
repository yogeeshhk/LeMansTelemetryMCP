import json
import duckdb
import pytest
from lmu_mcp.database import Repository, InspectionError
from lmu_mcp.service import TelemetryService
from lmu_mcp.track_knowledge import validate_pack, match_detected_corner
from lmu_mcp.cli import main


def service(recording):
    return TelemetryService(Repository(recording.parent))


def pack():
    return validate_pack({'version': 1, 'track': 'Synthetic', 'layout': 'Test',
        'status': 'calibrated', 'sources': [{'id': 'map', 'title': 'Map',
        'url': 'https://example.org/map', 'retrieved': '2026-09-24'}],
        'features': [{'feature_id': 'turn-one', 'name': 'Turn One',
        'kind': 'corner', 'order': 1, 'status': 'calibrated',
        'start_distance_m': 25, 'end_distance_m': 70,
        'uncertainty_m': 5, 'distance_method': 'Reviewed synthetic laps',
        'source_ids': ['map']}]})


def test_report_known_turn_without_pack_and_no_private_metadata(corner_recording):
    report = service(corner_recording).calibration_report(corner_recording.name)
    assert report['pack_status'] == 'no_pack'
    assert report['considered_laps'] == 2
    assert len(report['lap_reports']) == 2
    assert all(len(lap['detected_corners']) == 1 for lap in report['lap_reports'])
    assert report['lap_reports'][0]['detected_corners'][0]['apex_gps'] is None
    assert 'PRIVATE DRIVER' not in json.dumps(report)
    assert report['unsupported_laps'] == []


def test_unique_candidate_mapping_and_ambiguity(corner_recording, monkeypatch):
    knowledge = pack()
    monkeypatch.setattr('lmu_mcp.calibration.load_track_knowledge',
                        lambda track, layout: knowledge)
    report = service(corner_recording).calibration_report(corner_recording.name, max_laps=1)
    assert report['pack_status'] == 'calibrated'
    assert report['lap_reports'][0]['detected_corners'][0]['candidate_feature_id'] == 'turn-one'
    ambiguous = {'features': knowledge['features'] + [{**knowledge['features'][0],
                                                        'feature_id': 'turn-two'}]}
    assert match_detected_corner({'start_distance_m': 25, 'end_distance_m': 65}, ambiguous) is None


def test_report_records_invalid_lap_path_without_repair(corner_recording):
    with duckdb.connect(str(corner_recording)) as connection:
        connection.execute('UPDATE "Lap Dist" SET value=80 WHERE rowid=110')
    report = service(corner_recording).calibration_report(corner_recording.name)
    assert len(report['lap_reports']) == 1
    assert report['unsupported_laps'][0]['code'] == 'distance_reversal'
    with pytest.raises(InspectionError, match='max_laps'):
        service(corner_recording).calibration_report(corner_recording.name, 6)


def test_cli_report_command_uses_service_result(monkeypatch, capsys):
    class FakeService:
        def calibration_report(self, session_id, max_laps):
            assert (session_id, max_laps) == ('race.duckdb', 2)
            return {'pack_status': 'no_pack'}
    monkeypatch.setattr('lmu_mcp.cli.TelemetryService', FakeService)
    assert main(['calibration-report', 'race.duckdb', '--max-laps', '2']) == 0
    assert json.loads(capsys.readouterr().out) == {'pack_status': 'no_pack'}
