"""Offline Staging validation and planning. No credentials or Google imports."""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re
from urllib.parse import urlsplit

from sources import ValidationError, keys, require, text
from staging import COLUMNS, REVIEWED_RULES, amount, identity, year

HUMAN_FIELDS = {'status', 'review_notes'}
MACHINE_FIELDS = tuple(c for c in COLUMNS if c not in HUMAN_FIELDS)
STATUSES = {'pending', 'approved', 'rejected'}
RULES = REVIEWED_RULES | {'direct', 'majority_gt_50'}
MAJORITY_RULES = {'majority_gt_50', 'majority_undergraduate_schools'}


def candidate_key(row):
    return row['school_id'], row['field'], row['academic_year']


def validate_rows(rows, *, incoming):
    """Validate exact Staging output, reusing the research field/value/year rules."""
    require(isinstance(rows, list), 'Staging input must be an array')
    validated, seen = [], set()
    for row in rows:
        keys(row, COLUMNS, 'Staging row')
        identity(row)
        year(row['academic_year'])
        year(row['current_year'], nullable=True)
        for column in ('candidate_value', 'current_value'):
            amount(row[column], row['field'])
        for column in ('source_name', 'evidence'):
            text(row[column], column)
        for column, choices in [('source_type', {'university', 'CDS', 'nonprofit_research'}),
                                ('confidence', {'high', 'medium', 'low'}),
                                ('selection_rule', RULES), ('status', STATUSES)]:
            require(isinstance(row[column], str) and row[column] in choices,
                    f'Invalid {column}')
        require(not incoming or row['status'] == 'pending', 'Incoming status must be pending')
        require(isinstance(row['flag_reason'], str), 'flag_reason must be text')
        require(row['review_notes'] is None or isinstance(row['review_notes'], str),
                'review_notes must be text or null')
        url = row['source_url']
        if url is None:
            require(row['selection_rule'] == 'unresolved_source_conflict' and
                    row['candidate_value'] is None and bool(row['flag_reason'].strip()),
                    'Unknown source URL requires a flagged unresolved source conflict')
        else:
            text(url, 'source_url')
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
            except ValueError:
                valid = False
            require(valid and not any(c.isspace() for c in url), 'Invalid source URL')
        checked = row['checked_date']
        if checked is not None:
            require(isinstance(checked, str) and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', checked)),
                    'Invalid checked_date format')
            try:
                valid_date = date.fromisoformat(checked)
            except ValueError as exc:
                raise ValidationError('Invalid checked_date') from exc
            require(valid_date <= date.today(), 'checked_date cannot be in the future')
        numerator, denominator = row['coverage_numerator'], row['coverage_denominator']
        for value in (numerator, denominator):
            require(value is None or (type(value) is int and value > 0),
                    'Coverage counts must be positive integers or null')
        rule = row['selection_rule']
        if rule in MAJORITY_RULES:
            require(row['field'] in {'tuition', 'coa'}, 'Majority rule applies only to costs')
            if row['candidate_value'] is not None:
                require(numerator is not None and denominator is not None and
                        numerator <= denominator and numerator * 2 > denominator,
                        'Selected majority must cover strictly more than half')
            else:
                require(numerator is None and bool(row['flag_reason'].strip()),
                        'Unselected majority requires null numerator and a flag')
        else:
            require(numerator is None and denominator is None, 'Non-majority coverage must be null')
        if rule in {'unresolved_source_conflict', 'living_arrangement_ambiguous'}:
            require(row['candidate_value'] is None and bool(row['flag_reason'].strip()),
                    'Unresolved candidate requires null value and a flag')
        if rule in {'resident_standard', 'living_arrangement_ambiguous'}:
            require(row['field'] == 'coa', 'COA selection rule used on another field')
        if rule == 'university_standard':
            require(row['field'] in {'tuition', 'coa'}, 'Cost selection rule used on another field')
        if rule in {'cds_reported', 'university_reported'}:
            require(row['field'] == 'first_year_enrollment', 'Enrollment rule used on another field')
        if rule == 'cds_reported':
            require(row['source_type'] == 'CDS', 'CDS rule requires CDS source')
        if rule in {'university_standard', 'resident_standard', 'university_reported'}:
            require(row['source_type'] == 'university', 'University rule requires university source')
        if rule in {'university_standard', 'resident_standard', 'cds_reported', 'university_reported'}:
            require(row['candidate_value'] is not None, 'Reported/standard candidate requires a value')
        if row['candidate_value'] is None:
            require(bool(row['flag_reason'].strip()), 'Unknown candidate requires a flag')
        for value in row.values():
            require(not isinstance(value, str) or len(value.encode('utf-16-le')) // 2 <= 50000,
                    'Cell exceeds 50000 UTF-16 code units; preserve evidence externally, never truncate')
        key = candidate_key(row)
        require(key not in seen, 'Duplicate Staging key: ' + ' '.join(key))
        seen.add(key)
        validated.append({column: row[column] for column in COLUMNS})
    return validated


@dataclass(frozen=True)
class Snapshot:
    # Immutable row values in exact COLUMNS order, with physical worksheet positions.
    rows: tuple
    positions: tuple
    fingerprint: str

    def records(self):
        return [dict(zip(COLUMNS, row)) for row in self.rows]


def snapshot(rows, positions=None):
    records = validate_rows(rows, incoming=False)
    cells = tuple(tuple(row[c] for c in COLUMNS) for row in records)
    positions = tuple(range(2, 2 + len(cells))) if positions is None else tuple(positions)
    require(len(positions) == len(cells) and all(type(n) is int and n >= 2 for n in positions)
            and tuple(sorted(set(positions))) == positions, 'Invalid Staging row positions')
    payload = json.dumps([COLUMNS, cells, positions], ensure_ascii=False, allow_nan=False)
    return Snapshot(cells, positions, hashlib.sha256(payload.encode()).hexdigest())


@dataclass(frozen=True)
class Action:
    kind: str
    key: tuple
    values: tuple | None = None
    row_number: int | None = None


@dataclass(frozen=True)
class Plan:
    before: Snapshot
    actions: tuple


def plan_sync(incoming, existing):
    """Reject duplicates atomically; never pick a winner between duplicate input keys."""
    records = validate_rows(incoming, incoming=True)
    require(isinstance(existing, Snapshot), 'Expected a Staging snapshot')
    require(snapshot(existing.records(), existing.positions) == existing, 'Invalid snapshot fingerprint')
    lookup = {candidate_key(row): (row, n) for row, n in zip(existing.records(), existing.positions)}
    actions = []
    for row in records:
        key = candidate_key(row)
        match = lookup.get(key)
        if match is None:
            actions.append(Action('INSERT', key, tuple(row[c] for c in COLUMNS)))
            continue
        old, number = match
        if old['status'] in {'approved', 'rejected'}:
            actions.append(Action('SKIP_' + old['status'].upper(), key, row_number=number))
            continue
        merged = {**row, **{c: old[c] for c in HUMAN_FIELDS}}
        kind = 'NOOP' if all(merged[c] == old[c] for c in MACHINE_FIELDS) else 'UPDATE'
        actions.append(Action(kind, key, tuple(merged[c] for c in COLUMNS), number))
    return Plan(existing, tuple(actions))


class ConflictError(RuntimeError):
    pass


def check_unchanged(plan, current):
    if current != plan.before:
        raise ConflictError('Staging changed since planning; abort and re-read before replanning')


def report(plan, input_file, timestamp, errors=()):
    result = {'timestamp': timestamp, 'input_file': str(input_file), 'mode': 'dry_run',
              'inserts': [], 'updates': [], 'approved_skips': [], 'rejected_skips': [],
              'validation_errors': list(errors), 'no_op_rows': []}
    groups = {'INSERT': 'inserts', 'UPDATE': 'updates', 'SKIP_APPROVED': 'approved_skips',
              'SKIP_REJECTED': 'rejected_skips', 'NOOP': 'no_op_rows'}
    if plan is not None:
        for action in plan.actions:
            result[groups[action.kind]].append(dict(zip(('school_id', 'field', 'academic_year'), action.key)))
    return result
