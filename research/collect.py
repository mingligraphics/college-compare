"""Local-only entry point. Never writes to Sheets, Supabase, CSV or frontend."""
import argparse
import json
from pathlib import Path

from sources import ValidationError, load_json, load_sources, require
from staging import build_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True, type=Path)
    parser.add_argument('--candidates', required=True, type=Path)
    parser.add_argument('--current', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parent / 'output'
        target = args.output.resolve()
        require(target.is_relative_to(root.resolve()) and target.suffix == '.json',
                'Output must be a new JSON file inside research/output/')
        require(target not in {args.sources.resolve(), args.candidates.resolve(), args.current.resolve()},
                'Output cannot replace an input')
        rows = build_rows(load_json(args.candidates), load_json(args.current), load_sources(args.sources))
        payload = json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        # Validate the complete batch before writing. Existing outputs are never overwritten.
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as output:
            output.write(payload)
        print(f'Validated {len(rows)} pending Staging rows: {target}')
    except (ValidationError, OSError, ValueError, TypeError) as exc:
        parser.exit(1, f'Validation failed: {exc}\n')


if __name__ == '__main__':
    main()
