#!/usr/bin/env python3
"""Merge local ADIF logs into station_log.json, called by submit_lotw.sh after a LoTW upload."""
import copy
import datetime
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from adif_parser import parse_adif_file
from models import load_station_log, save_station_log, merge_contacts

STATION_LOG_FILE = 'station_log.json'

# Exit codes: 0 = saved real changes, 10 = nothing actually changed, 2 = aborted (unsafe to save)


def main(log_paths):
    existing_size = os.path.getsize(STATION_LOG_FILE) if os.path.exists(STATION_LOG_FILE) else 0
    station_log = load_station_log()
    original_count = len(station_log['contacts'])

    # Guard: if the file exists with real content but loaded as empty, load_station_log()
    # swallowed a read/parse error and returned a blank log. Saving now would wipe history.
    if existing_size > 100 and original_count == 0:
        print(f"ABORT: {STATION_LOG_FILE} is {existing_size} bytes on disk but loaded 0 contacts "
              f"(likely a read/parse failure) — refusing to overwrite it.", file=sys.stderr)
        return 2

    # merge_contacts' "updated" counter fires on every key match, even when no field actually
    # changes, so it's not a reliable "did anything change" signal. Snapshot for a real diff.
    before_snapshot = copy.deepcopy(station_log['contacts'])

    total_new_files_merged = 0

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
        total_new_files_merged += 1
        print(f"{path}: +{added} new, {updated} matched")

    final_count = len(station_log['contacts'])

    # Guard: merging should only ever grow (or hold steady) the contact count.
    # A shrink means something upstream is broken — don't persist it.
    if final_count < original_count:
        print(f"ABORT: merge would shrink contact count ({original_count} -> {final_count}), "
              f"not saving.", file=sys.stderr)
        return 2

    if station_log['contacts'] == before_snapshot:
        print("No new or updated contacts")
        return 10

    if total_new_files_merged == 0:
        # Nothing parsed at all (all files missing/errored) — don't touch the log.
        print("No source logs were readable, nothing to sync")
        return 10

    station_log['header']['total_contacts'] = final_count
    station_log['header']['last_updated'] = datetime.datetime.now().isoformat()

    try:
        save_station_log(station_log)
    except Exception as e:
        print(f"ABORT: failed to save {STATION_LOG_FILE}: {e}", file=sys.stderr)
        return 2

    # Verify what actually landed on disk matches what we intended to write.
    reloaded = load_station_log()
    if len(reloaded['contacts']) != final_count:
        print(f"ABORT: {STATION_LOG_FILE} on disk has {len(reloaded['contacts'])} contacts, "
              f"expected {final_count} — something went wrong during save.", file=sys.stderr)
        return 2

    print(f"Saved {STATION_LOG_FILE}: {final_count - original_count} new contact(s), "
          f"{final_count} total")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: sync_lotw_log.py <adif-file> [more-adif-files...]", file=sys.stderr)
        sys.exit(1)
    sys.exit(main(sys.argv[1:]))
