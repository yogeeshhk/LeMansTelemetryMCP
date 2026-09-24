"""Bounded general coaching support, independent of personal lap analysis."""
from copy import deepcopy
import json
import pytest
from lmu_mcp.database import InspectionError, Repository
from lmu_mcp.service import TelemetryService
from lmu_mcp.track_knowledge import validate_pack
from tests.test_phase14_packs import pack


def note(**changes):
    return dict(topic='overview', evidence='sourced', text='Synthetic circuit context.',
                applicability='Synthetic layout only.', source_ids=['map'], **changes)


def test_optional_coaching_is_bounded_and_evidence_is_explicit():
    raw = pack()
    assert 'coaching' not in validate_pack(raw)
    raw['coaching'] = [note()]
    raw['features'][0]['coaching'] = [{**note(), 'topic': 'driving',
                                      'evidence': 'general_technique', 'source_ids': []}]
    result = validate_pack(raw)
    assert validate_pack(result) == result
    assert result['features'][0]['coaching'][0]['evidence'] == 'general_technique'
    for change in [{'text': 'x' * 1001}, {'evidence': 'measured'}, {'topic': 'unknown'},
                   {'source_ids': []}, {'source_ids': ['missing']}, {'source_ids': [{}]},
                   {'applicability': ''}, {'text': 'bad\ntext'}]:
        bad = deepcopy(raw)
        bad['coaching'][0].update(change)
        with pytest.raises(InspectionError):
            validate_pack(bad)
    for target, count in [(raw, 9), (raw['features'][0], 4)]:
        original = target['coaching']
        target['coaching'] = original * count
        with pytest.raises(InspectionError, match='Coaching requires'):
            validate_pack(raw)
        target['coaching'] = original


def test_guide_notes_do_not_load_laps_and_keep_pagination(recording, monkeypatch):
    raw = pack()
    raw['coaching'] = [note()]
    raw['features'] *= 2
    raw['features'][1] = {**raw['features'][0], 'feature_id': 'two', 'order': 2,
                          'start_distance_m': 60, 'end_distance_m': 80}
    validated = validate_pack(raw)
    monkeypatch.setattr('lmu_mcp.service.load_track_knowledge', lambda *args: validated)
    service = TelemetryService(Repository(recording.parent))
    def forbidden(*args):
        raise AssertionError('A general guide must not require personal lap analysis')
    monkeypatch.setattr(service, '_laps', forbidden)
    monkeypatch.setattr(service, '_path', forbidden)
    first = service.get_track_guide(recording.name, limit=1)
    assert first['coaching'] == validated['coaching']
    assert first['next_offset'] == 1
    second = service.get_track_guide(recording.name, offset=1, limit=1)
    assert second['features'][0]['feature_id'] == 'two'
    assert second['next_offset'] is None
    assert 'lap_time' not in json.dumps(first)
