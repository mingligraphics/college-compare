"""Pure validation, selection and comparison. No retrieval, credentials or promotion."""
import json
import math
import re
from decimal import Decimal

from sources import keys, require, text, verify_excerpt

COLUMNS = (
    'school_id', 'field', 'candidate_value', 'academic_year', 'source_name',
    'source_url', 'source_type', 'evidence', 'current_value', 'current_year',
    'coverage_numerator', 'coverage_denominator', 'selection_rule', 'confidence',
    'flag_reason', 'status', 'review_notes', 'checked_date',
)
SCHOOLS = {'nyu', 'bu', 'ucb'}
FIELDS = {'tuition', 'coa', 'first_year_enrollment'}
REVIEWED_RULES = {'majority_undergraduate_schools', 'university_standard',
                  'resident_standard', 'cds_reported', 'university_reported',
                  'unresolved_source_conflict', 'living_arrangement_ambiguous'}


def year(value, nullable=False):
    if value is None and nullable:
        return
    require(isinstance(value, str) and bool(re.fullmatch(r'[0-9]{4}-[0-9]{2}', value)),
            'Academic year must be YYYY-YY')
    require(1900 <= int(value[:4]) <= 9998 and
            int(value[-2:]) == (int(value[:4]) + 1) % 100, 'Academic year must be consecutive')


def amount(value, field):
    if value is None:
        return
    require(type(value) in (int, float) and (type(value) is int or math.isfinite(value)), 'Value must be finite numeric or null')
    require(value >= 0, 'Value cannot be negative')
    if field == 'first_year_enrollment':
        require(type(value) is int, 'First-year enrollment must be an integer count')
    else:
        require(Decimal(str(value)) * 100 == (Decimal(str(value)) * 100).to_integral_value(),
                'USD amounts must have at most two decimal places')


def identity(record):
    require(isinstance(record['school_id'], str) and record['school_id'] in SCHOOLS, 'School outside pilot scope')
    require(isinstance(record['field'], str) and record['field'] in FIELDS, 'Field outside pilot scope')


def current_index(records):
    require(isinstance(records, list), 'Current School snapshot must be an array')
    current = {}
    for record in records:
        keys(record, {'school_id', 'field', 'current_value', 'current_year'}, 'current School record')
        identity(record)
        amount(record['current_value'], record['field'])
        year(record['current_year'], nullable=True)
        key = (record['school_id'], record['field'])
        require(key not in current, 'Duplicate current School field')
        current[key] = record
    return current


def units(value, context):
    require(isinstance(value, list) and len(value) > 0, f'{context}: expected nonempty array')
    for item in value:
        text(item, context)
    require(len(set(value)) == len(value), f'{context}: duplicate unit')
    return set(value)


def select_majority(record, source):
    """Count distinct units, aggregate equal amounts; never average or mix sources/years."""
    require(record['coverage_basis'] in ('schools', 'programs'), 'Coverage basis must be schools or programs')
    population = record['coverage_units']
    population = None if population is None else units(population, 'coverage_units')
    observations = record['observations']
    require(isinstance(observations, list) and observations, 'Majority requires observations')
    seen, totals, detail = set(), {}, []
    unknown_coverage = population is None
    for observation in observations:
        keys(observation, {'candidate_value', 'covered_units', 'evidence'}, 'observation')
        value = observation['candidate_value']
        amount(value, record['field'])
        verify_excerpt(source, observation['evidence'])
        covered = observation['covered_units']
        if covered is None:
            unknown_coverage = True
        else:
            covered = units(covered, 'covered_units')
            require(population is not None, 'Named coverage requires a known population')
            require(covered <= population, 'Observation contains units outside population')
            require(not seen.intersection(covered), 'Coverage overlaps or repeats a unit')
            seen.update(covered)
            if value is not None:
                totals[value] = totals.get(value, 0) + len(covered)
        detail.append(observation)
    denominator = len(population) if population is not None else None
    audit = '\nCoverage evidence: ' + json.dumps({
        'coverage_basis': record['coverage_basis'],
        'coverage_units': record['coverage_units'], 'observations': detail,
    }, ensure_ascii=False, allow_nan=False, sort_keys=True)
    if unknown_coverage:
        return None, None, denominator, 'Coverage is unknown; manual selection required.', audit
    winners = [(value, count) for value, count in totals.items() if count * 2 > denominator]
    if len(winners) == 1:
        value, numerator = winners[0]
        return value, numerator, denominator, '', audit
    return None, None, denominator, 'No value demonstrably covers >50% of units; manual selection required.', audit


def build_rows(candidates, current_records, sources):
    require(isinstance(candidates, list), 'Candidates must be an array')
    current = current_index(current_records)
    rows, seen = [], set()
    base = {'school_id', 'field', 'academic_year', 'source_id', 'evidence',
            'confidence', 'population', 'selection_rule'}
    for record in candidates:
        require(isinstance(record, dict), 'Candidate must be an object')
        rule = record.get('selection_rule')
        require(isinstance(rule, str) and rule in ({'direct', 'majority_gt_50'} | REVIEWED_RULES), 'Invalid selection_rule')
        if rule in REVIEWED_RULES:
            extra = {'review', 'source_concept'}
            extra |= ({'coverage_denominator', 'observations'} if rule == 'majority_undergraduate_schools'
                      else {'candidate_value', 'alternatives', 'components'})
        else:
            extra = {'candidate_value'} if rule == 'direct' else {'coverage_basis', 'coverage_units', 'observations'}
        keys(record, base | extra, 'candidate')
        identity(record)
        year(record['academic_year'])
        text(record['source_id'], 'source_id')
        require(record['source_id'] in sources, 'Unknown/unapproved source_id')
        require(isinstance(record['confidence'], str) and record['confidence'] in {'high', 'medium', 'low'}, 'Invalid confidence')
        expected_population = 'first_year' if record['field'] == 'first_year_enrollment' else 'undergraduate'
        require(record['population'] == expected_population, 'Wrong enrollment/cost population')
        key = (record['school_id'], record['field'], record['academic_year'], record['source_id'])
        require(key not in seen, 'Duplicate candidate group')
        seen.add(key)
        source = sources[record['source_id']]
        verify_excerpt(source, record['evidence'])
        numerator = denominator = None
        audit = ''
        if rule in REVIEWED_RULES:
            from reviewed import select_reviewed
            value, numerator, denominator, flag, audit = select_reviewed(record, source)
        elif rule == 'direct':
            value = record['candidate_value']
            amount(value, record['field'])
            flag = 'Value unknown; manual research required.' if value is None else ''
        else:
            require(record['field'] in {'tuition', 'coa'}, 'Majority rule applies only to costs')
            value, numerator, denominator, flag, audit = select_majority(record, source)
        previous = current.get((record['school_id'], record['field']))
        old_value = previous['current_value'] if previous else None
        old_year = previous['current_year'] if previous else None
        notes = []
        if source.get('evidence_kind') == 'reviewed_findings':
            notes.append('User-supplied reviewed findings; cited source was not fetched or checked in this run.')
            if source['checked_date'] is None:
                flag = ' '.join(filter(None, [flag, 'Source checked_date not supplied.']))
            if source['source_url'] is None:
                require(rule == 'unresolved_source_conflict', 'Missing source URL is allowed only for unresolved source conflicts')
                flag = ' '.join(filter(None, [flag, 'Source identity/URL and eligibility require verification.']))
        if rule in REVIEWED_RULES and record['review']['review_notes']:
            notes.append(record['review']['review_notes'])
        if previous is not None and old_year is None:
            notes.append('Current academic year unknown; do not infer a year or a like-for-like change.')
        if previous is None:
            notes.append('Current School field not supplied.')
        if value is None:
            notes.append('No candidate value selected; do not promote.')
        elif previous is not None:
            if old_year is None:
                pass
            elif old_year != record['academic_year']:
                notes.append('Different academic year; not a like-for-like value comparison.')
            elif old_value is None:
                notes.append('Current value is unknown; candidate available for review.')
            elif value == old_value:
                notes.append('Same value and academic year as current School.')
            else:
                notes.append('Different value for the same academic year; review required.')
        # Keep provenance reproducible even when Staging is detached from the input files.
        evidence = record['evidence'] + audit + '\nEvidence snapshot: ' + json.dumps({
            'source_id': source['source_id'], 'evidence_file': source['evidence_file'],
            'sha256': source['sha256'], 'approved_by': source['approved_by'],
            'evidence_kind': source.get('evidence_kind', 'source_snapshot'),
        }, ensure_ascii=False, sort_keys=True)
        row = dict(zip(COLUMNS, (
            record['school_id'], record['field'], value, record['academic_year'],
            source['source_name'], source['source_url'], source['source_type'], evidence,
            old_value, old_year, numerator, denominator, rule,
            'low' if value is None and rule not in REVIEWED_RULES else record['confidence'], flag, 'pending',
            ' '.join(notes), source['checked_date'],
        )))
        rows.append(row)
    originals = {(r['school_id'], r['field'], r['academic_year']) for r in rows
                 if r['source_type'] in {'university', 'CDS'} and r['candidate_value'] is not None}
    for row in rows:
        if row['source_type'] == 'nonprofit_research' and (
                row['school_id'], row['field'], row['academic_year']) in originals:
            note = 'University/CDS alternative available; prefer original evidence during human review.'
            row['flag_reason'] = ' '.join(filter(None, [row['flag_reason'], note]))
    return rows
