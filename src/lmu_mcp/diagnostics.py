"""Bounded, read-only recording diagnostics independent of MCP transport."""
import duckdb

from .analysis.laps import identify_laps
from .database import InspectionError, Repository, inspect_connection
from .telemetry import Session


DISPLAY_CHANNELS = (
    ('Lap channel', 'lap_number'),
    ('Lap distance', 'lap_distance'),
    ('Speed', 'speed'),
    ('Brake', 'brake'),
    ('Throttle', 'throttle'),
    ('Steering', 'steering'),
    ('Gear', 'gear'),
    ('ABS', 'abs'),
    ('TC', 'tc'),
)


def diagnose(session_id: str, repository: Repository | None = None) -> dict:
    """Report support and benchmark eligibility without claiming official validity."""
    repo = repository or Repository()
    with repo.open(session_id) as connection:
        try:
            inspection = inspect_connection(connection, session_id)
        except duckdb.Error as exc:
            raise InspectionError('inspection_failed', 'Database opened but its schema could not be inspected safely.') from exc
        sources = inspection.channels.channels
        channels = {}
        for label, canonical in DISPLAY_CHANNELS:
            channels[label] = ('ambiguous' if canonical in inspection.channels.ambiguous
                               else 'found' if sources.get(canonical) is not None else 'missing')
        frequencies = [details['frequency_hz'] for details in inspection.catalog.values()
                       if details['frequency_hz'] is not None]
        warnings = list(inspection.warnings)
        for label, status in channels.items():
            if status != 'found':
                warnings.append(f'{label}: {status}; related analysis may be unavailable.')
        detected_laps = usable_laps = None
        try:
            session = Session(connection, inspection)
            laps = identify_laps(session)
            detected_laps = len(laps)
            usable_laps = sum(lap['benchmark_candidate'] for lap in laps)
        except InspectionError as exc:
            warnings.append(f'Lap diagnostics unavailable ({exc.code}): {exc}')
        except duckdb.Error:
            warnings.append('Lap diagnostics unavailable (query_failed): recording data could not be read safely.')
        return {
            'session_id': session_id,
            'database_readable': True,
            'tables_discovered': len(inspection.tables),
            'channels': channels,
            'detected_laps': detected_laps,
            'usable_laps': usable_laps,
            'maximum_sample_frequency_hz': max(frequencies, default=None),
            'warnings': list(dict.fromkeys(warnings)),
            'validity_note': 'Usable laps are benchmark candidates, not officially valid laps.',
        }


def format_diagnostics(result: dict) -> str:
    lines = [f"Database readable: {'yes' if result['database_readable'] else 'no'}",
             f"Tables discovered: {result['tables_discovered']}"]
    lines.extend(f'{label}: {status}' for label, status in result['channels'].items())
    lines.extend((
        f"Detected laps: {result['detected_laps'] if result['detected_laps'] is not None else 'unavailable'}",
        f"Usable laps: {result['usable_laps'] if result['usable_laps'] is not None else 'unavailable'}",
        f"Maximum sample frequency: {result['maximum_sample_frequency_hz']:g} Hz"
        if result['maximum_sample_frequency_hz'] is not None else 'Maximum sample frequency: unavailable',
        result['validity_note'],
    ))
    lines.extend(f'Warning: {warning}' for warning in result['warnings'])
    return '\n'.join(lines)
