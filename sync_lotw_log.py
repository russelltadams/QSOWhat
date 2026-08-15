#!/usr/bin/env python3
"""Merge local ADIF logs into station_log.json, called by submit_lotw.sh after a LoTW upload."""
import datetime
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from adif_parser import parse_adif_file
from models import load_station_log, save_station_log, merge_contacts


def main(log_paths):
    station_log = load_station_log()
    total_added = 0
    total_updated = 0

    for path in log_paths:
        if not os.path.isfile(path):
            print(f"skip (not found): {path}")
            continue

        try:
            parsed = parse_adif_file(path)
        except Exception as e:
            print(f"error parsing {path}: {e}", file=sys.stderr)
            continue

        before = len(station_log['contacts'])
        merged, updated = merge_contacts(station_log['contacts'], parsed['contacts'])
        added = len(merged) - before

        station_log['contacts'] = merged
        total_added += added
        total_updated += updated
        print(f"{path}: +{added} new, {updated} updated")

    if total_added or total_updated:
        station_log['header']['total_contacts'] = len(station_log['contacts'])
        station_log['header']['last_updated'] = datetime.datetime.now().isoformat()
        save_station_log(station_log)
        print(f"Saved station_log.json: {total_added} new, {total_updated} updated")
        return 0

    print("No new or updated contacts")
    return 10


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: sync_lotw_log.py <adif-file> [more-adif-files...]", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv[1:]))
