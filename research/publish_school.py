"""Offline dry-run only. This command cannot connect to or write a database."""
import argparse
import json
from pathlib import Path

from school_publish import plan_publish
from sources import load_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true', required=True)
    args = parser.parse_args()
    plan = plan_publish(load_json(args.master), load_json(args.database))
    print(json.dumps(plan.report(), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
