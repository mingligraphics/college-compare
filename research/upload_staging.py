"""Offline-only dry-run CLI. Does not import/authenticate/connect to Google Sheets."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from sources import ValidationError, load_json, require
from staging_sync import plan_sync, report
from staging_transport import MemoryStaging


def read_input(path):
    try:
        return load_json(path)
    except (ValidationError, OSError) as exc:
        # Do not echo malformed file content, keys, secrets, or parser diagnostics.
        raise ValidationError('Input file is unreadable or is not strict JSON') from exc


def dry_run(input_file, existing_file=None):
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        incoming = read_input(input_file)
        existing = [] if existing_file is None else read_input(existing_file)
        transport = MemoryStaging(existing)
        plan = plan_sync(incoming, transport.read_staging())
        require(transport.write_count == 0, 'Dry-run must not write')
        return plan, report(plan, input_file, timestamp)
    except (ValidationError, TypeError, ValueError, OverflowError) as exc:
        # Validation messages are structural; no values, evidence or credentials are logged.
        message = str(exc) if isinstance(exc, ValidationError) else 'Malformed Staging record'
        return None, report(None, input_file, timestamp, errors=[message])


def print_report(plan, audit):
    if plan is not None:
        for action in plan.actions:
            print(action.kind, *action.key)
    for error in audit['validation_errors']:
        print('ERROR', error)
    print('Summary:')
    for key, label in [('inserts', 'inserts'), ('updates', 'updates'),
                       ('approved_skips', 'approved skips'), ('rejected_skips', 'rejected skips'),
                       ('no_op_rows', 'no-op rows'), ('validation_errors', 'errors')]:
        print(len(audit[key]), label)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--existing', type=Path, help='Mock existing Staging JSON; omitted means empty')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Always enabled; no live-write CLI exists')
    parser.add_argument('--report', required=True, type=Path, help='New JSON path inside research/output/')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / 'output'
    target = args.report.resolve()
    try:
        require(target.is_relative_to(root.resolve()) and target.suffix == '.json',
                'Report must be a new JSON file inside research/output/')
        inputs = {args.input.resolve()}
        if args.existing:
            inputs.add(args.existing.resolve())
        require(target not in inputs, 'Report cannot replace an input')
        plan, audit = dry_run(args.input, args.existing)
        payload = json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as output:
            output.write(payload)
        print_report(plan, audit)
        if audit['validation_errors']:
            parser.exit(1)
    except (ValidationError, OSError):
        parser.exit(1, 'Unable to write a new local audit report at the requested path; no sync performed.\n')


if __name__ == '__main__':
    main()
