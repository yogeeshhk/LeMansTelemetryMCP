"""Stable local bearer path for the personal HTTP endpoint."""
import os
from pathlib import Path
import re
import secrets

_TOKEN = re.compile(r'[A-Za-z0-9_-]{32,128}\Z')
_FILENAME = 'private-path.txt'


def validate_token(token):
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise ValueError('Private MCP path is invalid; rotate it before starting the server.')
    return token


def state_directory():
    # The PowerShell launcher changes into the repository before invoking the CLI.
    return Path.cwd() / '.runtime'


def load_or_create(directory=None):
    directory = Path(directory) if directory is not None else state_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _FILENAME
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return validate_token(path.read_text(encoding='ascii').strip())
    token = secrets.token_urlsafe(32)
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as handle:
            handle.write(token)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return token


def rotate(directory=None):
    directory = Path(directory) if directory is not None else state_directory()
    directory.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path = directory / _FILENAME
    temporary = directory / (_FILENAME + '.' + secrets.token_hex(8) + '.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='ascii') as handle:
            handle.write(token)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return token
