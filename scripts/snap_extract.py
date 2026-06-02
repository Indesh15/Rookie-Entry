#!/usr/bin/env python3
"""
Extract window.__SNAP__ baseline from the dashboard HTML.

Usage:
    python3 scripts/snap_extract.py <html_file> <output_baseline_json>

Prints a JSON summary to stdout. Exits 1 on error.
"""
import json
import sys

POLL_IDS = [21403849, 21403869, 21403879, 21403889, 21403899]
SNAP_MARKER = "window.__SNAP__="


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: snap_extract.py <html_file> <output_json>"}))
        sys.exit(1)

    html_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(html_file, "r", encoding="utf-8") as f:
        html = f.read()

    if not html.startswith("<html"):
        print(json.dumps({"error": "content_not_html"}))
        sys.exit(1)

    idx = html.find(SNAP_MARKER)
    if idx == -1:
        print(json.dumps({"error": "snap_marker_not_found"}))
        sys.exit(1)

    after = html[idx + len(SNAP_MARKER):]
    try:
        decoder = json.JSONDecoder()
        snap, _ = decoder.raw_decode(after)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"snap_parse_failed: {e}"}))
        sys.exit(1)

    all_rows = snap.get("allRows", [])
    rej_rows = snap.get("rejRows", [])

    per_poll = {}
    for pid in POLL_IDS:
        per_poll[pid] = sum(
            1 for r in all_rows
            if r.get("_pid") == pid or str(r.get("_pid")) == str(pid)
            or r.get("PollId") == pid or str(r.get("PollId")) == str(pid)
        )

    baseline = {
        "completed": len(all_rows),
        "rejected": len(rej_rows),
        "per_poll": per_poll,
        "prev_savedAt": snap.get("savedAt", ""),
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(baseline, f)

    print(json.dumps(baseline))


if __name__ == "__main__":
    main()
