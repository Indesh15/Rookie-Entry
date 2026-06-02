#!/usr/bin/env python3
"""
Strip one page of MCP rows to the allowed column set and append to a JSONL file.

Usage:
    python3 scripts/process_batch.py <poll_id> <batch_json_file> <output_jsonl>

batch_json_file: path to a JSON file containing the items array from one
                 live_data_get_report_flat call.

Prints the number of rows appended to stdout.
Exits 1 on error.
"""
import json
import sys

KEEP_COLS = frozenset([
    "ADM1_2_3_4_1",
    "ADM1_2_3_4_2",
    "GDR",
    "AGE",
    "EDC",
    "AST_BNK",
    "AST_TV",
    "SurveyDate",
    "UserId",
    "EnumeratorId",
    "IsOffline",
    "SurveyId",
    "PollId",
    "SurveyState",
    "RejectedReason",
    "_pid",
])


def main():
    if len(sys.argv) < 4:
        print("ERROR: usage: process_batch.py <poll_id> <batch_json> <output_jsonl>",
              file=sys.stderr)
        sys.exit(1)

    poll_id = int(sys.argv[1])
    batch_file = sys.argv[2]
    output_file = sys.argv[3]

    with open(batch_file, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not isinstance(items, list):
        print(f"ERROR: batch file must contain a JSON array, got {type(items)}",
              file=sys.stderr)
        sys.exit(1)

    with open(output_file, "a", encoding="utf-8") as f:
        for row in items:
            stripped = {k: v for k, v in row.items() if k in KEEP_COLS}
            stripped["_pid"] = poll_id
            f.write(json.dumps(stripped, separators=(",", ":")) + "\n")

    print(len(items))


if __name__ == "__main__":
    main()
