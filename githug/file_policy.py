"""Conservative filename exclusions; users still review selected content."""
from pathlib import PurePosixPath


def sensitive_path(path):
    name = PurePosixPath(path).name.casefold()
    return (name.startswith('.env') or name in {'madobe.json', 'settings.json', 'credentials.json'}
            or any(word in name for word in ('secret', 'credential', 'api_key', 'apikey'))
            or PurePosixPath(name).suffix in {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'})
