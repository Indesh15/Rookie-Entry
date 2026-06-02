#!/usr/bin/env python3
"""
Replace window.__SNAP__=...;  in the dashboard HTML with a new snapshot.

Usage:
    python3 scripts/snap_inject.py <template_html> <new_snap_json> <output_html>

Locates window.__SNAP__= in the template, uses json.JSONDecoder to find the
exact end of the JSON object (handles nested braces and string literals),
then splices in the new compact JSON. Changes nothing else in the HTML.

Prints "OK: <byte_count>" to stdout on success.
Exits 1 on error.
"""
import json
import sys


SNAP_MARKER = "window.__SNAP__="


def main():
    if len(sys.argv) < 4:
        print("ERROR: usage: snap_inject.py <template_html> <new_snap_json> <output_html>",
              file=sys.stderr)
        sys.exit(1)

    template_file = sys.argv[1]
    new_snap_file = sys.argv[2]
    output_file = sys.argv[3]

    with open(template_file, "r", encoding="utf-8") as f:
        html = f.read()

    with open(new_snap_file, "r", encoding="utf-8") as f:
        new_snap_str = f.read().strip()

    # Validate the new snapshot is valid JSON
    try:
        json.loads(new_snap_str)
    except json.JSONDecodeError as e:
        print(f"ERROR: new snapshot JSON is invalid: {e}", file=sys.stderr)
        sys.exit(1)

    idx = html.find(SNAP_MARKER)
    if idx == -1:
        print("ERROR: window.__SNAP__= not found in template", file=sys.stderr)
        sys.exit(1)

    after = html[idx + len(SNAP_MARKER):]
    try:
        decoder = json.JSONDecoder()
        _, end = decoder.raw_decode(after)
    except json.JSONDecodeError as e:
        print(f"ERROR: could not parse existing __SNAP__ JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Find the semicolon that terminates the assignment
    rest = after[end:]
    semi_offset = rest.find(";")
    if semi_offset == -1:
        print("ERROR: no semicolon found after __SNAP__ JSON", file=sys.stderr)
        sys.exit(1)

    full_end = idx + len(SNAP_MARKER) + end + semi_offset + 1  # include the ;

    new_html = html[:idx] + f"{SNAP_MARKER}{new_snap_str};" + html[full_end:]

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"OK: {len(new_html.encode('utf-8'))} bytes written to {output_file}")


if __name__ == "__main__":
    main()
