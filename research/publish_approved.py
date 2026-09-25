"""Explicit production entry point for the approved three-school publication."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request

from sources import load_json, require, ValidationError
from school_publish import PostgresSchools, plan_publish, database_snapshot, FIELDS

PROJECT = 'hmnoqybdcfwqbjhorwzd'
IDS = ('nyu', 'bu', 'ucb')
PAIRS = (('nyu', 'bu'), ('nyu', 'ucb'), ('bu', 'ucb'))
SPREADSHEET = '1gMcmRGVxWgw4olbax2Vwxf4ZDJroBaHShH8A1qAjkrw'


def validate_connection(params):
    """Check the destination without displaying any connection information."""
    host = params.get('host', '')
    direct = host == 'db.' + PROJECT + '.supabase.co'
    pooler = (host.endswith('.pooler.supabase.com') and
              params.get('user', '').endswith('.' + PROJECT))
    require(direct or pooler, 'Unexpected connection destination')
    require(params.get('dbname') == 'postgres', 'Unexpected database')
    require(not params.get('hostaddr') and not params.get('service'),
            'Connection routing override forbidden')


def production_transport():
    # Lazy import: --help and unit tests do not need psycopg or credentials.
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    url = os.environ.get('DATABASE_URL')
    require(bool(url), 'Missing database configuration')
    params = conninfo_to_dict(url)
    validate_connection(params)
    def connect():
        return psycopg.connect(url, autocommit=True, connect_timeout=15,
                              sslmode='require')
    return PostgresSchools(connect, PROJECT)


def compare_api(a, b):
    request = urllib.request.Request(
        'https://' + PROJECT + '.supabase.co/functions/v1/compare-schools-basic-v1',
        data=json.dumps({'schoolA': a, 'schoolB': b}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verify_rows(rows, expected, ids):
    require(isinstance(rows, list) and len(rows) == len(ids), 'Wrong row count')
    require([r['school_id'] for r in rows] == list(ids), 'Wrong row identities/order')
    differences = []
    for row in rows:
        for field in ('school_id',) + FIELDS:
            # Report identities only: never echo unexpected server content.
            if field not in row or type(row[field]) is bool or row[field] != expected[row['school_id']][field]:
                differences.append(row['school_id'] + '.' + field)
    return differences


def run(folder, transport_factory=production_transport, api=compare_api, emit=print,
        approved_digest=None):
    stage = 'approved snapshots'
    try:
        require(isinstance(approved_digest,str) and len(approved_digest)==64, 'Explicit reviewed digest required')
        master = load_json(folder / 'approved-school.json')
        current_master = load_json(folder / 'current-school.json')
        require(master['spreadsheet_id'] == SPREADSHEET, 'Wrong master spreadsheet')
        baseline = load_json(folder / 'current-private-schools.json')
        plan = plan_publish(master, baseline)
        require(plan.report()['approval_digest'] == approved_digest, 'Approval mismatch')
        require(plan.database_id == PROJECT and tuple(r[0] for r in plan.after) == IDS,
                'Scope mismatch')
        emit('Approved snapshot: PASS')
        stage = 'database configuration/connection'
        db = transport_factory()
        stage = 'pre-write baseline'
        require(database_snapshot(db.read(list(IDS))) == plan.before, 'Baseline mismatch')
        emit('Pre-write baseline: PASS')
    except (Exception, KeyboardInterrupt):
        emit('STOP BEFORE COMMIT: ' + stage + ' failed. No updates attempted.')
        return 1

    try:
        # The transport rechecks the baseline under row locks, updates only Basic
        # fields, and verifies them in the same transaction.
        updated = db.apply(plan, approved_digest=approved_digest, current_master=current_master)
    except ValidationError:
        emit('STOP BEFORE COMMIT: locked baseline/validation failed; batch aborted.')
        return 1
    except (Exception, KeyboardInterrupt):
        # Lost COMMIT acknowledgements cannot honestly be called a rollback.
        emit('STOP: transaction failed; COMMIT OUTCOME UNKNOWN. Do not retry automatically.')
        return 2

    changed = sum(len(r['changes']) for r in plan.report()['changes'])
    emit(f'Transaction committed: {updated} school rows, {changed} changed values')
    expected = {r['school_id']: r for r in master['rows']}
    failed = False
    try:
        actual = db.read(list(IDS))
        database_snapshot(actual)
        rows = sorted(actual['rows'], key=lambda r: IDS.index(r['school_id']))
        differences = verify_rows(rows, expected, IDS)
        require(not differences, 'Readback mismatch')
        emit('Database readback: PASS (120/120 fields)')
    except (Exception, KeyboardInterrupt):
        failed = True
        emit('Database readback: FAILED (read, structure, or value mismatch)')
    for a, b in PAIRS:
        try:
            differences = verify_rows(api(a, b), expected, (a, b))
            if differences:
                emit(f'API {a}/{b}: MISMATCH ' + ', '.join(differences))
                failed = True
            else:
                emit(f'API {a}/{b}: PASS')
        except (Exception, KeyboardInterrupt):
            failed = True
            emit(f'API {a}/{b}: FAILED (request or response structure)')
    if failed:
        emit('STOP AFTER COMMIT: verification failed. No repair attempted.')
        return 3
    emit('SUCCESS: all verification passed; no automatic repair performed.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True,
                        help='Execute an explicitly reviewed Basic v1 plan')
    parser.add_argument('--snapshots', type=Path, required=True)
    parser.add_argument('--approved-digest', required=True)
    parser.add_argument('--transport', choices=('postgres','supabase-cli'), default='postgres')
    args = parser.parse_args()
    factory = production_transport
    if args.transport == 'supabase-cli':
        from school_cli_transport import SupabaseSchools
        factory = SupabaseSchools
    return run(args.snapshots, transport_factory=factory, approved_digest=args.approved_digest)


if __name__ == '__main__':
    sys.exit(main())
