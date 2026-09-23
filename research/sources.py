"""Local evidence boundary. Research adapters save evidence; this module never fetches URLs."""
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def keys(value, expected, context):
    require(isinstance(value, dict), f'{context}: expected an object')
    require(set(value) == set(expected), f'{context}: expected exactly {sorted(expected)}')


def text(value, context):
    require(isinstance(value, str) and bool(value) and value == value.strip(),
            f'{context}: expected nonblank text without surrounding whitespace')
    return value


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValidationError(f'Invalid JSON numeric constant: {value}')

    try:
        return json.loads(Path(path).read_text(encoding='utf-8'),
                          object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, OSError) as exc:
        raise ValidationError(f'Cannot load JSON {path}: {exc}') from exc


def load_sources(manifest_path):
    """Require reviewer-approved sources and hash-verified UTF-8 evidence snapshots."""
    manifest_path = Path(manifest_path)
    records = load_json(manifest_path)
    require(isinstance(records, list), 'Sources must be an array')
    sources = {}
    root = manifest_path.parent.resolve()
    expected = {'source_id', 'source_name', 'source_url', 'source_type',
                'approved_by', 'checked_date', 'evidence_file', 'sha256'}
    for record in records:
        supplied = isinstance(record, dict) and 'evidence_kind' in record
        keys(record, expected | ({'evidence_kind'} if supplied else set()), 'source')
        kind = record.get('evidence_kind', 'source_snapshot')
        require(kind in ('source_snapshot', 'reviewed_findings'), 'Invalid evidence_kind')
        for key in expected - {'checked_date', 'source_url'}:
            text(record[key], key)
        if kind == 'source_snapshot' or record['source_url'] is not None:
            text(record['source_url'], 'source_url')
        require(record['source_type'] in {'university', 'CDS', 'nonprofit_research'},
                'Unapproved source_type')
        require(record['source_id'] not in sources, 'Duplicate source_id')
        if record['source_url'] is not None:
            url = urlsplit(record['source_url'])
            require(url.scheme == 'https' and bool(url.hostname) and not url.username
                    and not url.password and not any(c.isspace() for c in record['source_url']),
                    'Source URL must be an HTTPS public-source URL without credentials')
        checked = record['checked_date']
        if checked is None:
            require(kind == 'reviewed_findings', 'Source snapshot requires checked_date')
        else:
            text(checked, 'checked_date')
            require(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', checked)), 'Invalid checked_date format')
            try:
                checked_date = date.fromisoformat(checked)
            except ValueError as exc:
                raise ValidationError('Invalid checked_date') from exc
            require(checked_date <= date.today(), 'checked_date cannot be in the future')
        require(bool(re.fullmatch(r'[0-9a-f]{64}', record['sha256'])), 'Invalid SHA-256')
        relative = Path(record['evidence_file'])
        require(not relative.is_absolute(), 'evidence_file must be relative to its manifest')
        path = (root / relative).resolve()
        require(path.is_relative_to(root), 'Evidence path escapes its manifest directory')
        try:
            raw = path.read_bytes()
            snapshot = raw.decode('utf-8')
        except (OSError, UnicodeError) as exc:
            raise ValidationError('Cannot read UTF-8 evidence snapshot') from exc
        require(hashlib.sha256(raw).hexdigest() == record['sha256'], 'Evidence SHA-256 mismatch')
        sources[record['source_id']] = {**record, '_snapshot': snapshot}
    return sources


def verify_excerpt(source, excerpt):
    text(excerpt, 'evidence')
    require(excerpt in source['_snapshot'], 'Evidence excerpt is absent from saved source snapshot')
