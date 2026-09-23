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
DIGEST = 'ede7d72f0158b2a0d894cc39bfb025a7b6e06f2dd803488c4e212b15943464a0'
IDS = ('nyu', 'bu', 'ucb')
PAIRS = (('nyu', 'bu'), ('nyu', 'ucb'), ('bu', 'ucb'))
SNAPSHOTS = Path.home() / ('Documents/Codex/2026-09-08/'
    'open-my-local-college-compare-repository/outputs/school-publish-20260923')


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
        'https://' + PROJECT + '.supabase.co/functions/v1/compare-schools',
        data=json.dumps({'schoolA': a, 'schoolB': b}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verify_rows(rows, expected, ids):
    require(isinstance(rows, list) and len(rows) == len(ids), 'Wrong row count')
    require([r['school_id'] for r in rows] == list(ids), 'Wrong row identities/order')
    differences = []
    for row in rows:
        for field in FIELDS:
            # Report identities only: never echo unexpected server content.
            if field not in row or type(row[field]) is bool or row[field] != expected[row['school_id']][field]:
                differences.append(row['school_id'] + '.' + field)
    return differences


def run(folder, transport_factory=production_transport, api=compare_api, emit=print,
        approved_digest=DIGEST):
    stage = 'approved snapshots'
    try:
        master = load_json(folder / 'approved-school.json')
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
        # Existing implementation does the second read/check under row locks
        # and all five-column updates in one transaction. No SQL duplicated here.
        updated = db.apply(plan, approved_digest=approved_digest, current_master=master)
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
        emit('Database readback: PASS (15/15 fields)')
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
                        help='Execute the previously approved transaction')
    parser.add_argument('--snapshots', type=Path, default=SNAPSHOTS)
    args = parser.parse_args()
    return run(args.snapshots)


if __name__ == '__main__':
    sys.exit(main())
