"""Staging-only transport boundary. No credentials are loaded or clients constructed."""
from copy import deepcopy
from threading import RLock
from typing import Protocol

from sources import require
from staging import COLUMNS
from staging_sync import Plan, Snapshot, check_unchanged, plan_sync, snapshot


class StagingTransport(Protocol):
    def read_staging(self) -> Snapshot: ...
    def apply(self, plan: Plan) -> None: ...


def validate_plan(plan):
    """Do not allow forged plans to alter review status/notes or arbitrary rows."""
    before = {tuple(row[c] for c in ('school_id', 'field', 'academic_year')): row
              for row in plan.before.records()}
    incoming = []
    for action in plan.actions:
        if action.kind in {'SKIP_APPROVED', 'SKIP_REJECTED'}:
            require(action.key in before, 'Invalid skip key')
            row = dict(before[action.key])
            row['status'] = 'pending'
        else:
            require(action.values is not None and len(action.values) == len(COLUMNS), 'Invalid action values')
            row = dict(zip(COLUMNS, action.values))
        incoming.append(row)
    require(plan_sync(incoming, plan.before) == plan, 'Plan does not match safe synchronization rules')


def apply_rows(plan):
    rows = plan.before.records()
    indexes = {n: i for i, n in enumerate(plan.before.positions)}
    for action in plan.actions:
        if action.kind == 'INSERT':
            rows.append(dict(zip(COLUMNS, action.values)))
        elif action.kind == 'UPDATE':
            rows[indexes[action.row_number]] = dict(zip(COLUMNS, action.values))
    return rows


class MemoryStaging:
    """Local mock with atomic read/check/write inside one lock. No network capability."""
    def __init__(self, rows=()):
        self._rows = deepcopy(list(rows))
        self._lock = RLock()
        self.write_count = 0
        self.read_count = 0

    def read_staging(self):
        with self._lock:
            self.read_count += 1
            return snapshot(self._rows)

    def replace_for_test(self, rows):
        with self._lock:
            self._rows = deepcopy(rows)

    def apply(self, plan):
        with self._lock:
            validate_plan(plan)
            check_unchanged(plan, self.read_staging())
            changes = sum(a.kind in {'INSERT', 'UPDATE'} for a in plan.actions)
            if changes:
                self._rows = apply_rows(plan)
                self.write_count += changes


def decode_grid(grid):
    """Sheets omits trailing empty cells; null fields are represented by blank cells."""
    require(isinstance(grid, list) and grid and grid[0] == list(COLUMNS),
            'Staging row 1 must contain exactly the 18 approved headers in order')
    nullable = {'candidate_value', 'current_value', 'current_year', 'source_url',
                'coverage_numerator', 'coverage_denominator', 'checked_date'}
    records, positions = [], []
    for n, cells in enumerate(grid[1:], start=2):
        require(isinstance(cells, list) and len(cells) <= len(COLUMNS), 'Unexpected Staging columns')
        if not cells or all(v is None or v == '' for v in cells):
            continue
        cells = cells + [''] * (len(COLUMNS) - len(cells))
        row = {c: (None if c in nullable and (v is None or v == '') else v)
               for c, v in zip(COLUMNS, cells)}
        records.append(row)
        positions.append(n)
    return snapshot(records, positions)


def encode(values):
    # Sheets skips JSON null in updates; empty string deliberately clears unknown fields.
    # RAW mode keeps evidence/notes starting with '=' as literal text, not formulas.
    return ['' if value is None else value for value in values]


def write_request(plan):
    validate_plan(plan)
    data = []
    next_row = max(plan.before.positions, default=1) + 1
    for action in plan.actions:
        if action.kind == 'INSERT':
            data.append({'range': f"'Staging'!A{next_row}:R{next_row}",
                         'values': [encode(action.values)]})
            next_row += 1
        elif action.kind == 'UPDATE':
            n = action.row_number
            # P=status and Q=review_notes are never included in update requests.
            data.extend([
                {'range': f"'Staging'!A{n}:O{n}", 'values': [encode(action.values[:15])]},
                {'range': f"'Staging'!R{n}", 'values': [encode(action.values[17:18])]},
            ])
    return {'valueInputOption': 'RAW', 'data': data}


class LiveWritesDisabled(RuntimeError):
    pass


class GoogleSheetsStaging:
    """Injected Sheets v4 client, hard-coded Staging tab. No arbitrary worksheet API.

    Writes are disabled unless a future caller supplies an exclusive edit-window
    context manager. It MUST exclude human/UI edits and every other writer, not just
    lock this Python process. Read/check/write alone is NOT a Sheets compare-and-swap.
    """
    def __init__(self, service, spreadsheet_id, *, exclusive_edit_window=None):
        self._service = service
        self._spreadsheet_id = spreadsheet_id
        self._exclusive_edit_window = exclusive_edit_window

    def read_staging(self):
        response = self._service.spreadsheets().values().get(
            spreadsheetId=self._spreadsheet_id, range="'Staging'",
            valueRenderOption='UNFORMATTED_VALUE').execute()
        return decode_grid(response.get('values', []))

    def apply(self, plan):
        validate_plan(plan)
        request = write_request(plan)
        if not request['data']:
            return
        if self._exclusive_edit_window is None:
            raise LiveWritesDisabled('Real writes require an externally enforced exclusive Staging edit window')
        with self._exclusive_edit_window():
            check_unchanged(plan, self.read_staging())
            # One batch, no blind retries. On uncertain completion, re-read and replan.
            self._service.spreadsheets().values().batchUpdate(
                spreadsheetId=self._spreadsheet_id, body=request).execute()
