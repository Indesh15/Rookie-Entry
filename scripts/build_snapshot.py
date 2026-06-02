#!/usr/bin/env python3
"""
Build the final window.__SNAP__ JSON from accumulated JSONL pull files.

Usage:
    python3 scripts/build_snapshot.py \
        <completed_jsonl> <rejected_jsonl> \
        <output_snap_json> <baseline_json>

Reads completed_jsonl (reportId=1 rows) and rejected_jsonl (reportId=3 rows).
Splits the combined set by SurveyState == "Rejected" as the authoritative rule.
Runs integrity checks against the baseline.

Prints a JSON summary to stdout.
Exits 2 if integrity check fails (caller should stop the run).
Exits 1 on other errors.
"""
import json
import sys
from datetime import datetime, timezone

POLL_IDS = [21403849, 21403869, 21403879, 21403889, 21403899]


def read_jsonl(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except FileNotFoundError:
        pass
    return rows


def main():
    if len(sys.argv) < 5:
        print("ERROR: usage: build_snapshot.py <completed_jsonl> <rejected_jsonl> "
              "<output_snap_json> <baseline_json>", file=sys.stderr)
        sys.exit(1)

    completed_file = sys.argv[1]
    rejected_file = sys.argv[2]
    output_file = sys.argv[3]
    baseline_file = sys.argv[4]

    with open(baseline_file, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    completed_raw = read_jsonl(completed_file)
    rejected_raw = read_jsonl(rejected_file)
    all_raw = completed_raw + rejected_raw

    all_rows = [r for r in all_raw if r.get("SurveyState") != "Rejected"]
    rej_rows = [r for r in all_raw if r.get("SurveyState") == "Rejected"]

    summary = {
        "new_completed": len(all_rows),
        "new_rejected": len(rej_rows),
        "baseline_completed": baseline["completed"],
        "baseline_rejected": baseline["rejected"],
        "delta_completed": len(all_rows) - baseline["completed"],
        "delta_rejected": len(rej_rows) - baseline["rejected"],
        "integrity_ok": True,
        "integrity_reason": None,
    }

    # Guard: empty snapshot
    if len(all_rows) == 0:
        summary["integrity_ok"] = False
        summary["integrity_reason"] = "STOP: new completed row count is 0"
        print(json.dumps(summary))
        sys.exit(2)

    # Guard: >20% drop from baseline (skip if baseline is 0 — first run)
    if baseline["completed"] > 0:
        ratio = len(all_rows) / baseline["completed"]
        if ratio < 0.80:
            summary["integrity_ok"] = False
            summary["integrity_reason"] = (
                f"STOP: completed count dropped {(1-ratio)*100:.1f}% "
                f"(new={len(all_rows)}, baseline={baseline['completed']})"
            )
            print(json.dumps(summary))
            sys.exit(2)

    # Per-poll counts for caller's per-poll check
    per_poll_new = {}
    for pid in POLL_IDS:
        per_poll_new[pid] = sum(
            1 for r in all_rows
            if r.get("_pid") == pid or str(r.get("_pid")) == str(pid)
        )
    summary["per_poll_new"] = per_poll_new
    summary["per_poll_baseline"] = baseline.get("per_poll", {})

    # Distinct operator count
    summary["distinct_operators"] = len(
        {r.get("EnumeratorId") or r.get("UserId") for r in all_rows} - {None}
    )

    saved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap = {
        "allRows": all_rows,
        "rejRows": rej_rows,
        "activePollIds": POLL_IDS,
        "savedAt": saved_at,
        "source": "Claude (automated)",
    }
    summary["savedAt"] = saved_at

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))

    print(json.dumps(summary))


if __name__ == "__main__":
    main()
