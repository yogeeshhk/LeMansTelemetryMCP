"""Optional, bounded track/layout-specific manual corner definitions."""
import json
import math
from pathlib import Path
from .database import InspectionError
from .telemetry import require

TRACK_DEFINITIONS_DIR = Path(__file__).resolve().parent / 'tracks'
MAX_DEFINITION_FILES = 32
MAX_DEFINITION_BYTES = 65_536
MAX_MANUAL_CORNERS = 128


def _number(value, name):
    require(type(value) in (int,float) and math.isfinite(value),
            'invalid_track_definition',f'{name} must be a finite number.')
    return float(value)


def _validate_definition(data):
    require(type(data) is dict and type(data.get('track')) is str and type(data.get('layout')) is str
            and 0<len(data['track'])<=128 and 0<len(data['layout'])<=128,
            'invalid_track_definition','Track definitions need nonempty track and layout names (at most 128 characters).')
    raw=data.get('corners')
    require(type(raw) is list and 1<=len(raw)<=MAX_MANUAL_CORNERS,
            'invalid_track_definition','Define 1 to 128 manual corners.')
    rows=[]
    for item in raw:
        require(type(item) is dict and type(item.get('corner_id')) is int
                and 1<=item['corner_id']<=1000,
                'invalid_track_definition','Each manual corner needs a positive integer corner_id (1-1000).')
        name=item.get('name')
        require(name is None or (type(name) is str and 0<len(name)<=80
                                and all(ord(char)>=32 for char in name)),
                'invalid_track_definition','Corner names must be printable strings of at most 80 characters.')
        start=_number(item.get('start_distance_m'),'start_distance_m')
        end=_number(item.get('end_distance_m'),'end_distance_m')
        require(0<=start<end<=200000 and end-start<=2000,
                'invalid_track_definition','Manual corner ranges need 0 <= start < end <= 200000 m and length <= 2000 m.')
        apex=item.get('apex_distance_m')
        if apex is not None:
            apex=_number(apex,'apex_distance_m')
            require(start<=apex<=end,'invalid_track_definition',
                    'Manual apex distance must lie within its corner range.')
        rows.append({'corner_id':item['corner_id'],'name':name,'source':'manual',
                     'start_distance_m':start,'end_distance_m':end,
                     'apex_distance_m':apex})
    require(len({row['corner_id'] for row in rows})==len(rows),
            'invalid_track_definition','Manual corner IDs must be unique.')
    ordered=sorted(rows,key=lambda row:row['start_distance_m'])
    require(all(left['end_distance_m']<=right['start_distance_m'] for left,right in zip(ordered,ordered[1:])),
            'invalid_track_definition','Manual corner ranges must not overlap.')
    return data['track'],data['layout'],ordered


def load_manual_corners(track, layout, directory: Path = TRACK_DEFINITIONS_DIR):
    """Return a matching validated list, or None; never follow definitions outside root."""
    if not track or not layout:
        return None
    root=Path(directory)
    if not root.is_dir():
        return None
    root=root.resolve()
    files=list(root.glob('*.json'))
    require(len(files)<=MAX_DEFINITION_FILES,'track_definition_limit',
            'Too many track definition files; keep at most 32 JSON files.')
    found=None
    for path in sorted(files):
        try:
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
                raise InspectionError('invalid_track_definition','Track definition must be a regular file inside its fixed directory.')
            if not path.is_file() or path.stat().st_size>MAX_DEFINITION_BYTES:
                raise InspectionError('track_definition_limit','Track definition must be a regular JSON file of at most 64 KiB.')
            data=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:
            raise InspectionError('invalid_track_definition','Track definition could not be read as valid UTF-8 JSON.') from exc
        defined_track,defined_layout,rows=_validate_definition(data)
        if defined_track==track and defined_layout==layout:
            require(found is None,'ambiguous_track_definition',
                    'Multiple manual files match this exact track and layout.')
            found=rows
    return found
