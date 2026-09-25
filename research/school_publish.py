"""Approved School snapshots -> fixed-column plans -> explicit transactional updates.

No credentials, client construction, network calls at import, or automatic publishing.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json

from sources import keys, require, text
from staging import SCHOOLS, year

# Fixed Basic v1 contract; never accept SQL identifiers from a snapshot.
COLUMNS = ('school_id', 'school_name', 'school_name_cn', 'short_name', 'institution_control', 'school_type', 'city', 'city_cn', 'state', 'state_cn', 'tuition_fees', 'tuition_fees_year', 'coa', 'coa_year', 'undergrad_enrollment', 'undergrad_enrollment_year', 'applicants', 'admitted', 'first_year_enrollment', 'acceptance_rate', 'admissions_year', 'sat_25', 'sat_75', 'act_25', 'act_75', 'test_policy', 'test_policy_cycle', 'international_pct', 'international_pct_year', 'international_pct_scope', 'graduation_rate_4yr', 'graduation_rate_4yr_year', 'international_need_aid', 'international_merit_aid', 'english_proficiency_policy', 'english_tests_accepted', 'english_policy_cycle', 'ranking_usnews', 'ranking_category', 'ranking_year')
FIELDS = COLUMNS[1:]
ORDER = ('nyu', 'bu', 'ucb')
SELECT_SQL = 'SELECT ' + ', '.join(COLUMNS) + ' FROM private.schools WHERE school_id = ANY(%s) ORDER BY school_id'
UPDATE_SQL = 'UPDATE private.schools SET ' + ', '.join(f + ' = %s' for f in FIELDS) + ' WHERE school_id = %s'
INTEGER_FIELDS = frozenset(('undergrad_enrollment', 'applicants', 'admitted', 'first_year_enrollment', 'sat_25', 'sat_75', 'act_25', 'act_75', 'ranking_usnews', 'ranking_year'))
PERCENT_FIELDS = frozenset(('acceptance_rate', 'international_pct', 'graduation_rate_4yr'))
ENUMS = {
 'institution_control': {'public','private_nonprofit','private_forprofit'},
 'school_type': {'research_university','liberal_arts_college','specialized_institution','other'},
 'test_policy': {'required','test_optional','test_free','test_flexible','unclear'},
 'international_pct_scope': {'undergraduate','all_students'},
 'international_need_aid': {'yes','limited','no','unclear'},
 'international_merit_aid': {'yes','limited','no','unclear'},
 'english_proficiency_policy': {'required','conditional','not_required','unclear'},
 'ranking_category': {'national_university','national_liberal_arts_college','other'},
}


def freeze(value):
    return tuple(value) if isinstance(value, list) else value


def thaw(value):
    return list(value) if isinstance(value, tuple) else value


def validate_rows(rows, *, master):
    require(isinstance(rows, list) and rows, 'Expected nonempty school rows')
    result = {}
    for row in rows:
        keys(row, set(COLUMNS), 'publishable School record')
        sid = row['school_id']
        require(type(sid) is str and sid in SCHOOLS, 'Unknown pilot school')
        require(sid not in result, 'Duplicate school')
        text(row['school_name'], 'school_name')
        for field in FIELDS:
            value = row[field]
            if value is None:
                continue
            if field in INTEGER_FIELDS:
                require(type(value) is int and 0 <= value <= 2147483647, 'Invalid integer: ' + field)
                require(field not in ('ranking_usnews','ranking_year') or value > 0, 'Rank/year must be positive')
            elif field in PERCENT_FIELDS or field in ('tuition_fees','coa'):
                require(type(value) in (int,float) and Decimal(str(value)).is_finite(), 'Invalid number: ' + field)
                number = Decimal(str(value))
                maximum = 100 if field in PERCENT_FIELDS else Decimal('9999999999.99')
                require(0 <= number <= maximum and number == number.quantize(Decimal('.01')), 'Invalid range/scale: ' + field)
            elif field == 'english_tests_accepted':
                require(isinstance(value, list), 'English tests must be an array or null')
                for test in value:
                    text(test, field)
                require(len(set(value)) == len(value), 'Duplicate English test')
            else:
                text(value, field)
                require(value.lower() not in ('null','undefined'), 'Textual null is forbidden')
                if field in ENUMS:
                    require(value in ENUMS[field], 'Invalid classification: ' + field)
        for field in ('tuition_fees', 'coa'):
            year(row[field + '_year'], nullable=True)
            if master:
                require((row[field] is None) == (row[field + '_year'] is None),
                        'Master amount and academic year must both be known or both null')
        for low, high in [('sat_25','sat_75'),('act_25','act_75')]:
            require(row[low] is None or row[high] is None or row[low] <= row[high], 'Reversed test percentiles')
        result[sid] = tuple(freeze(row[column]) for column in COLUMNS)
    return tuple(result[sid] for sid in ORDER if sid in result)


def master_snapshot(document):
    keys(document, {'source_tab', 'spreadsheet_id', 'rows'}, 'School snapshot')
    require(document['source_tab'] == 'School', 'Only the School master may be published')
    text(document['spreadsheet_id'], 'spreadsheet_id')
    return validate_rows(document['rows'], master=True)


def database_snapshot(document):
    keys(document, {'target', 'database_id', 'rows'}, 'database snapshot')
    require(document['target'] == 'private.schools', 'Unexpected target table')
    text(document['database_id'], 'database_id')
    return validate_rows(document['rows'], master=False)


def records(rows):
    return [dict(zip(COLUMNS, (thaw(v) for v in row))) for row in rows]


@dataclass(frozen=True)
class Plan:
    spreadsheet_id: str
    database_id: str
    before: tuple
    after: tuple

    def report(self):
        changes = []
        unchanged = []
        for old, new in zip(self.before, self.after):
            fields = {field: {'before': thaw(old[i]), 'after': thaw(new[i])}
                      for i, field in enumerate(COLUMNS) if i and old[i] != new[i]}
            if fields:
                changes.append({'school_id': new[0], 'changes': fields})
            else:
                unchanged.append(new[0])
        payload = {'source_tab': 'School', 'spreadsheet_id': self.spreadsheet_id,
                   'target': 'private.schools', 'database_id': self.database_id,
                   'before': records(self.before), 'after': records(self.after),
                   'changes': changes, 'unchanged': unchanged}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                           allow_nan=False).encode()).hexdigest()
        return {'mode': 'dry-run', 'approval_digest': digest, **payload}


def plan_publish(master, database):
    after = master_snapshot(master)
    current = {row[0]: row for row in database_snapshot(database)}
    require(all(row[0] in current for row in after), 'Target school missing; inserts are forbidden')
    before = tuple(current[row[0]] for row in after)
    return Plan(master['spreadsheet_id'], database['database_id'], before, after)


def read_school(service, spreadsheet_id):
    """Injected Sheets v4 client; reads School only. No Sheets write capability here.

    Full School tabs may contain unrelated columns; only the fixed projection is
    returned. Within the projection, unknown is a blank cell, zero stays zero.
    """
    text(spreadsheet_id, 'spreadsheet_id')
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range="'School'!A1:BA4",
        valueRenderOption='UNFORMATTED_VALUE').execute()
    grid = response.get('values', [])
    require(isinstance(grid, list) and grid, 'School header missing')
    header = grid[0]
    require(isinstance(header, list) and all(type(v) is str and v.strip() == v and v for v in header),
            'Invalid School headers')
    require(len(set(header)) == len(header), 'Duplicate School header')
    require(set(COLUMNS) <= set(header), 'Required School columns missing')
    indexes = [header.index(column) for column in COLUMNS]
    rows = []
    for cells in grid[1:]:
        require(isinstance(cells, list) and len(cells) <= len(header), 'Malformed School row')
        if not cells or all(v in ('', None) for v in cells):
            continue
        projected = [cells[i] if i < len(cells) else None for i in indexes]
        # This publisher is deliberately restricted to the initial pilot.
        sid = projected[0]
        require(type(sid) is str and sid.strip() == sid and sid, 'Invalid School ID')
        require(sid in SCHOOLS, 'Unknown pilot school in School master')
        record = dict(zip(COLUMNS, [None if v == '' else v for v in projected]))
        if isinstance(record['english_tests_accepted'], str):
            try:
                record['english_tests_accepted'] = json.loads(record['english_tests_accepted'])
            except ValueError as exc:
                raise ValueError('Invalid English tests JSON') from exc
        rows.append(record)
    document = {'source_tab': 'School', 'spreadsheet_id': spreadsheet_id, 'rows': rows}
    master_snapshot(document)
    return document


def _db_rows(cursor):
    rows = []
    for values in cursor.fetchall():
        require(len(values) == len(COLUMNS), 'Unexpected database projection')
        values = list(values)
        # PostgreSQL numeric arrives as Decimal. This schema fits safely within
        # float cent precision; JSON validation below still rejects excess scale.
        for i in range(len(COLUMNS)):
            if isinstance(values[i], Decimal):
                values[i] = float(values[i])
        rows.append(dict(zip(COLUMNS, values)))
    return rows


class PostgresSchools:
    """Trusted server/operator connection, never the public browser/RPC credential.

    Factory must return a fresh psycopg 3 connection with autocommit=True.
    database_id is the operator-verified project reference for this connection.
    No writes occur until apply receives an explicitly approved digest.
    """
    def __init__(self, connect, database_id):
        text(database_id, 'database_id')
        self.connect, self.database_id = connect, database_id

    def read(self, school_ids):
        require(isinstance(school_ids, (list, tuple)) and school_ids and
                all(type(s) is str and s in SCHOOLS for s in school_ids) and
                len(set(school_ids)) == len(school_ids), 'Invalid school scope')
        with self.connect() as connection:
            require(connection.autocommit is True, 'Fresh autocommit connection required')
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
                    cursor.execute(SELECT_SQL, (list(school_ids),))
                    rows = _db_rows(cursor)
        document = {'target': 'private.schools', 'database_id': self.database_id, 'rows': rows}
        database_snapshot(document)
        require({row['school_id'] for row in rows} == set(school_ids), 'Target school missing')
        return document

    def apply(self, plan, *, approved_digest, current_master):
        # Rebuild to validate even a manually constructed Plan; fail before connecting.
        master = {'source_tab': 'School', 'spreadsheet_id': plan.spreadsheet_id,
                  'rows': records(plan.after)}
        database = {'target': 'private.schools', 'database_id': plan.database_id,
                    'rows': records(plan.before)}
        require(plan_publish(master, database) == plan, 'Invalid publication plan')
        require(approved_digest == plan.report()['approval_digest'], 'Explicit plan approval required')
        require(plan.database_id == self.database_id, 'Wrong database target')
        require(current_master['spreadsheet_id'] == plan.spreadsheet_id and
                master_snapshot(current_master) == plan.after, 'School master changed; re-plan')
        with self.connect() as connection:
            require(connection.autocommit is True, 'Fresh autocommit connection required')
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute('SET LOCAL lock_timeout = \'5s\'')
                    cursor.execute('SET LOCAL statement_timeout = \'30s\'')
                    cursor.execute(SELECT_SQL + ' FOR UPDATE', ([row[0] for row in plan.after],))
                    current = validate_rows(_db_rows(cursor), master=False)
                    require(current == plan.before, 'Database changed; transaction aborted; re-plan')
                    count = 0
                    for old, new in zip(plan.before, plan.after):
                        if old != new:
                            cursor.execute(UPDATE_SQL, (*[thaw(v) for v in new[1:]], new[0]))
                            require(cursor.rowcount == 1, 'Update did not affect exactly one school')
                            count += 1
                    cursor.execute(SELECT_SQL, ([row[0] for row in plan.after],))
                    require(validate_rows(_db_rows(cursor), master=False) == plan.after,
                            'Transactional readback failed')
        return count
