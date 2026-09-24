"""Validated, offline track knowledge separate from user manual-corner overrides."""
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from .database import InspectionError
from .telemetry import require

KNOWLEDGE_DIR = Path(__file__).resolve().parent / 'tracks' / 'knowledge'
MAX_FILES = 32
MAX_BYTES = 65_536
MAX_FEATURES = 128
MAX_SOURCES = 32
KINDS = {'corner', 'complex', 'straight', 'sector', 'landmark'}
STATUSES = {'calibrated', 'approximate', 'unmatched'}


def _fail(message):
    raise InspectionError('invalid_track_pack', message)


def _label(value, field, limit=128):
    if type(value) is not str or not 0 < len(value) <= limit or any(ord(ch) < 32 for ch in value):
        _fail(f'{field} must be a printable string of at most {limit} characters.')
    return value


def _distance(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 200_000:
        _fail(f'{field} must be a finite distance in metres from 0 to 200000.')
    return float(value)


def validate_pack(raw):
    """Return a normalized JSON-shaped pack; never interpret source prose as commands."""
    if type(raw) is not dict or raw.get('version') != 1 or type(raw.get('version')) is not int:
        _fail('Track pack requires version 1.')
    track = _label(raw.get('track'), 'track')
    layout = _label(raw.get('layout'), 'layout')
    status = raw.get('status')
    if type(status) is not str or status not in {'calibrated', 'approximate'}:
        _fail('Pack status must be calibrated or approximate.')
    sources = raw.get('sources')
    if type(sources) is not list or not 1 <= len(sources) <= MAX_SOURCES:
        _fail('Pack requires 1 to 32 source references.')
    normalized_sources = []
    for source in sources:
        if type(source) is not dict:
            _fail('Each source must be an object.')
        source_id = _label(source.get('id'), 'source id', 64)
        title = _label(source.get('title'), 'source title', 160)
        url = _label(source.get('url'), 'source URL', 500)
        try:
            parsed = urlsplit(url)
        except ValueError:
            _fail('Source URL is malformed.')
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            _fail('Source URL must be an HTTPS page without embedded credentials.')
        retrieved = _label(source.get('retrieved'), 'retrieved date', 10)
        try:
            if date.fromisoformat(retrieved).isoformat() != retrieved:
                raise ValueError
        except ValueError:
            _fail('Source retrieved date must be YYYY-MM-DD.')
        normalized_sources.append({'id': source_id, 'title': title, 'url': url,
                                   'retrieved': retrieved})
    source_ids = [source['id'] for source in normalized_sources]
    if len(set(source_ids)) != len(source_ids):
        _fail('Source IDs must be unique.')
    features = raw.get('features')
    if type(features) is not list or not 1 <= len(features) <= MAX_FEATURES:
        _fail('Pack requires 1 to 128 features.')
    normalized_features = []
    for feature in features:
        if type(feature) is not dict:
            _fail('Each feature must be an object.')
        feature_id = _label(feature.get('feature_id'), 'feature_id', 64)
        name = _label(feature.get('name'), 'feature name', 80)
        kind = feature.get('kind')
        feature_status = feature.get('status')
        order = feature.get('order')
        if type(kind) is not str or type(feature_status) is not str or kind not in KINDS or feature_status not in STATUSES:
            _fail('Feature kind or status is unsupported.')
        if type(order) is not int or not 1 <= order <= MAX_FEATURES:
            _fail('Feature order must be an integer from 1 to 128.')
        references = feature.get('source_ids')
        if type(references) is not list or not 1 <= len(references) <= 5 or any(type(ref) is not str or ref not in source_ids for ref in references) or len(set(references)) != len(references):
            _fail('Feature source_ids must cite 1 to 5 distinct pack sources.')
        start = feature.get('start_distance_m')
        end = feature.get('end_distance_m')
        uncertainty = feature.get('uncertainty_m')
        method = feature.get('distance_method')
        if (start is None) != (end is None):
            _fail('Feature distances require both start and end.')
        if start is not None:
            start = _distance(start, 'start_distance_m')
            end = _distance(end, 'end_distance_m')
            if not start < end:
                _fail('Feature end distance must exceed start distance.')
            uncertainty = _distance(uncertainty, 'uncertainty_m')
            if uncertainty > 1000:
                _fail('Feature uncertainty must not exceed 1000 m.')
            method = _label(method, 'distance_method', 200)
        elif uncertainty is not None or method is not None:
            _fail('Distance uncertainty and method require a distance range.')
        if feature_status == 'calibrated' and start is None:
            _fail('Calibrated features require a distance range.')
        if feature_status == 'unmatched' and start is not None:
            _fail('Unmatched features cannot claim a distance range.')
        note = feature.get('character')
        if note is not None:
            note = _label(note, 'character', 240)
        normalized_features.append({'feature_id': feature_id, 'name': name,
                                    'kind': kind, 'order': order, 'status': feature_status,
                                    'start_distance_m': start, 'end_distance_m': end,
                                    'uncertainty_m': uncertainty, 'distance_method': method,
                                    'source_ids': references, 'character': note})
    ids = [item['feature_id'] for item in normalized_features]
    orders = [item['order'] for item in normalized_features]
    if len(set(ids)) != len(ids) or len(set(orders)) != len(orders) or orders != sorted(orders):
        _fail('Feature IDs and orders must be unique and features must be in order.')
    corners = [f for f in normalized_features if f['kind'] == 'corner' and f['start_distance_m'] is not None]
    corners.sort(key=lambda item: item['start_distance_m'])
    if any(a['end_distance_m'] > b['start_distance_m'] for a, b in zip(corners, corners[1:])):
        _fail('Corner ranges must not overlap; other feature kinds may overlap.')
    return {'version': 1, 'track': track, 'layout': layout, 'status': status,
            'sources': normalized_sources, 'features': normalized_features}


def load_track_knowledge(track, layout, directory=KNOWLEDGE_DIR):
    """Load one exact-match local pack; validate every package file before use."""
    if not track or not layout:
        return None
    root = Path(directory)
    if not root.is_dir():
        return None
    root = root.resolve()
    files = list(root.glob('*.json'))
    require(len(files) <= MAX_FILES, 'track_pack_limit',
            'Keep at most 32 track-knowledge JSON files.')
    found = None
    for path in sorted(files):
        try:
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
                _fail('Track pack must be a regular file inside its fixed directory.')
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                _fail('Track pack must be a regular JSON file of at most 64 KiB.')
            pack = validate_pack(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InspectionError('invalid_track_pack', 'Track pack could not be read as UTF-8 JSON.') from exc
        if pack['track'] == track and pack['layout'] == layout:
            require(found is None, 'ambiguous_track_pack',
                    'Multiple track packs match this exact track and layout.')
            found = pack
    return found


def match_detected_corner(corner, pack):
    """Associate only a unique sourced corner range; complexes remain guide context."""
    if pack is None:
        return None
    start = float(corner['start_distance_m'])
    end = float(corner['end_distance_m'])
    width = end - start
    if width <= 0:
        return None
    candidates = []
    for feature in pack['features']:
        if feature['kind'] != 'corner' or feature['start_distance_m'] is None:
            continue
        left = feature['start_distance_m']
        right = feature['end_distance_m']
        overlap = max(0.0, min(end, right) - max(start, left))
        uncertainty = feature['uncertainty_m']
        if overlap / width >= 0.5 and left - uncertainty <= (start + end) / 2 <= right + uncertainty:
            candidates.append(feature)
    return candidates[0] if len(candidates) == 1 else None
