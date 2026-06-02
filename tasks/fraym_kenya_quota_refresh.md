# Fraym Kenya Quota Refresh — Automated Scheduled Task

**Run fully automated. Do not pause for confirmation at any step.**
**The task owner (ian@geopoll.com) has pre-authorized all alert emails defined in this prompt.**

---

## Constants

```
ARTIFACT_ID   = 47351ffe-cfc7-402b-9367-74c81322682f
ARTIFACT_TITLE = Fraym Gender Ian Refresh Test
UPLOAD_URL     = https://mcp.geopoll.com/api/artifacts/47351ffe-cfc7-402b-9367-74c81322682f/upload
POLL_IDS       = [21403849, 21403869, 21403879, 21403889, 21403899]
ALERT_EMAIL    = ian@geopoll.com
BACKUP_FILE    = backups/fraym_kenya_dashboard_backup.html

TMP_TEMPLATE   = /tmp/template.html
TMP_BATCH      = /tmp/batch.json
TMP_BASELINE   = /tmp/baseline.json
TMP_COMPLETED  = /tmp/completed_rows.jsonl
TMP_REJECTED   = /tmp/rejected_rows.jsonl
TMP_NEW_SNAP   = /tmp/new_snap.json
TMP_OUTPUT     = /tmp/dashboard_updated.html
```

---

## AUTH_REQUIRED / 401 / 403 — stop immediately

If **any** MCP call returns AUTH_REQUIRED, or any HTTP response is 401 or 403:

1. Stop. Write nothing to the artifact.
2. Send this email via `outlook_send_email` (send directly — no confirmation needed):
   - **to**: ian@geopoll.com
   - **subject**: Action needed: log in to refresh the Fraym Kenya Quota dashboard
   - **bodyType**: text
   - **body** (exact):

```
Action needed.

The scheduled refresh for the Fraym Kenya Quota dashboard could not run because the mcp.geopoll.com session is no longer authenticated.

Please log in and authenticate here: https://mcp.geopoll.com

Once you are signed in, the next scheduled refresh will run automatically. Your existing data is safe and unchanged until then.

Dashboard: https://mcp.geopoll.com/api/artifacts/47351ffe-cfc7-402b-9367-74c81322682f/view
```

3. Exit. Report: "Run aborted — AUTH_REQUIRED. Alert sent to ian@geopoll.com."

---

## Other hard errors — alert and stop

For any other unrecoverable error (failed pull, failed write, failed upload, integrity violation):

1. Stop. Preserve the existing artifact.
2. Send an alert email via `outlook_send_email` to ian@geopoll.com (send directly — no confirmation needed):
   - **subject**: Fraym Kenya Quota dashboard refresh failed — [one-line cause]
   - **body**: One sentence describing the cause. State explicitly whether the previous dashboard data was preserved or restored.
3. Exit with a summary of what happened.

---

## Step 1 — Fetch the artifact and validate

### 1a. Call artifact_get

Call `mcp__GeoPoll-Admin__artifact_get` with:
```json
{ "id": "47351ffe-cfc7-402b-9367-74c81322682f" }
```

Read the `content` field from the response (the HTML string).

### 1b. Validate the content

Check whether the content starts with `<html`.

**If it does NOT start with `<html`** — the artifact is corrupted:
- Read `backups/fraym_kenya_dashboard_backup.html` from the repo.
- If the backup file exists and starts with `<html`:
  - Use the backup as the template for this run.
  - Immediately restore the artifact by uploading the backup through the upload flow in Step 5 (skip the integrity checks for the restore — just upload the known-good backup).
  - Log: "Artifact corrupted. Restored from backup."
  - Continue the run using the backup as the template.
- If no valid backup exists:
  - Send failure alert: "Artifact content is not HTML and no valid backup exists."
  - Exit.

### 1c. Write the template to disk

Write the validated HTML content to `/tmp/template.html`.

### 1d. Extract the baseline

Run:
```bash
python3 scripts/snap_extract.py /tmp/template.html /tmp/baseline.json
```

Parse the JSON output. Record:
- `baseline_completed` = output["completed"]
- `baseline_rejected`  = output["rejected"]
- `baseline_per_poll`  = output["per_poll"]  (dict keyed by poll ID)

If the script exits 1, send failure alert and exit.

---

## Step 2 — Pull fresh data (sequential, one poll at a time)

First, initialise empty accumulation files:
```bash
rm -f /tmp/completed_rows.jsonl /tmp/rejected_rows.jsonl
touch /tmp/completed_rows.jsonl /tmp/rejected_rows.jsonl
```

For each poll ID in `[21403849, 21403869, 21403879, 21403889, 21403899]`, in order (do **not** run polls in parallel):

### Per-poll pull — completed rows (reportId=1)

**Page loop:**

1. Call `mcp__GeoPoll-Admin__live_data_get_report_flat` with:
   ```json
   {
     "pollIds": [<poll_id>],
     "reportId": 1,
     "offset": 0,
     "limit": 100,
     "refresh": true
   }
   ```
   Use `refresh: true` only on the **first page** of each poll+reportId combination. Subsequent pages (offset > 0) omit `refresh` so they hit the cache.

2. Write the `items` array from the response to `/tmp/batch.json`. The file should contain a valid JSON array (use the Write tool to write the raw items list as JSON).

3. Run:
   ```bash
   python3 scripts/process_batch.py <poll_id> /tmp/batch.json /tmp/completed_rows.jsonl
   ```
   This appends stripped rows to the accumulation file. The script prints the row count appended.

4. Check the response fields:
   - If `returned < 100` (or `hasMore == false`): pagination for this poll+reportId is done. Move on.
   - Otherwise: increment offset by 100 and repeat from step 1 (without `refresh`).

If a call errors (not AUTH, which is handled at the top):
- Mark this poll as errored.
- Do **not** continue pulling other polls.
- Send failure alert and exit.

### Per-poll pull — rejected rows (reportId=3)

Repeat the same page loop with `reportId: 3`, appending to `/tmp/rejected_rows.jsonl`.

---

## Step 3 — Integrity checks and snapshot build

### 3a. Build the snapshot and run integrity checks

Run:
```bash
python3 scripts/build_snapshot.py \
    /tmp/completed_rows.jsonl \
    /tmp/rejected_rows.jsonl \
    /tmp/new_snap.json \
    /tmp/baseline.json
```

Parse the JSON output.

- If the script exits **2** (integrity violation): the output explains why. Send failure alert with the reason. Exit.
- If the script exits **1** (other error): send failure alert. Exit.

Record from the output:
- `new_completed` = output["new_completed"]
- `new_rejected`  = output["new_rejected"]
- `saved_at`      = output["savedAt"]
- `per_poll_new`  = output["per_poll_new"]
- `distinct_operators` = output["distinct_operators"]

### 3b. Per-poll count check

For each poll ID, compare `per_poll_new[pid]` to `baseline_per_poll[pid]`.

If `per_poll_new[pid] < baseline_per_poll[pid] * 0.50` **and** baseline_per_poll[pid] > 0:
  - Re-pull that poll (both reportId=1 and reportId=3) from scratch:
    - Remove that poll's previously appended rows: rebuild both JSONL files by filtering out rows where `_pid == pid`:
      ```bash
      python3 -c "
      import json, sys
      pid = int(sys.argv[1])
      for path in ['/tmp/completed_rows.jsonl', '/tmp/rejected_rows.jsonl']:
          rows = []
          try:
              with open(path) as f:
                  rows = [l for l in f if json.loads(l).get('_pid') != pid]
          except FileNotFoundError:
              pass
          with open(path, 'w') as f:
              f.writelines(rows)
      " <poll_id>
      ```
    - Re-run the page loop for this poll (both reportId=1 and reportId=3) with `refresh: true`.
    - Rerun `build_snapshot.py` to get updated counts.
    - Check `per_poll_new[pid]` again. If still < 50 % of baseline: send failure alert for this poll and exit.

---

## Step 4 — Inject snapshot into HTML and pre-upload check

### 4a. Inject

Run:
```bash
python3 scripts/snap_inject.py \
    /tmp/template.html \
    /tmp/new_snap.json \
    /tmp/dashboard_updated.html
```

If the script exits 1: send failure alert. Exit.

### 4b. Pre-upload check

Run all five checks. If **any** fails, send failure alert and exit without uploading.

```bash
# 1. Starts with <html
head -c 6 /tmp/dashboard_updated.html | grep -q '^<html' \
    || { echo "FAIL: does not start with <html"; exit 1; }

# 2. Larger than 1,000,000 bytes
SIZE=$(wc -c < /tmp/dashboard_updated.html)
[ "$SIZE" -gt 1000000 ] \
    || { echo "FAIL: file is only $SIZE bytes (must be >1000000)"; exit 1; }

# 3. Contains window.__SNAP__=
grep -q 'window\.__SNAP__=' /tmp/dashboard_updated.html \
    || { echo "FAIL: window.__SNAP__= not found"; exit 1; }

# 4. Contains the hardcoded artifact ID constant
grep -q "ADMIN_ARTIFACT_ID    = '47351ffe-cfc7-402b-9367-74c81322682f'" /tmp/dashboard_updated.html \
    || { echo "FAIL: ADMIN_ARTIFACT_ID constant not found"; exit 1; }

# 5. Contains the provenance element
grep -q 'id="refresh-provenance"' /tmp/dashboard_updated.html \
    || { echo "FAIL: id=refresh-provenance not found"; exit 1; }

echo "PRE-UPLOAD: all checks passed. Size=$SIZE bytes."
```

---

## Step 5 — Upload

### 5a. Get upload token

Call `mcp__GeoPoll-Admin__artifact_get_upload_token` (no parameters).

Extract from the response:
- `token` (Bearer token string)
- `url` (upload URL) — use this URL as returned; do not hardcode a URL

### 5b. Upload via curl

Run:
```bash
HTTP_STATUS=$(curl -s -o /tmp/upload_result.txt -w "%{http_code}" \
  -X PUT \
  -H "Authorization: Bearer <token>" \
  -F "file=@/tmp/dashboard_updated.html;type=text/html" \
  -F "title=Fraym Gender Ian Refresh Test" \
  "<upload_url>")

echo "Upload HTTP status: $HTTP_STATUS"
cat /tmp/upload_result.txt
```

Substitute `<token>` and `<upload_url>` with the actual values from step 5a.

If `HTTP_STATUS` is not 200 or 201:
- This is an upload failure. Roll back: re-upload `/tmp/template.html` (the original HTML from step 1) using the same token/URL flow to restore the last good version.
- Send failure alert: "Upload returned HTTP $HTTP_STATUS. Rolled back to previous version."
- Exit.

### 5c. Post-upload verification

Call `mcp__GeoPoll-Admin__artifact_get` again with id `47351ffe-cfc7-402b-9367-74c81322682f`.

Verify all three conditions:
1. Content starts with `<html`
2. Content contains `"savedAt":"<saved_at>"` (the exact savedAt value from this run)
3. Content length > 1,000,000 characters

If **any** condition fails:
- The upload corrupted the artifact.
- Immediately re-upload `/tmp/template.html` (original from step 1) to restore the last good version:
  - Call `artifact_get_upload_token` again for a fresh token.
  - curl PUT the original template file.
- Send failure alert: "Post-upload verification failed. Rolled back to previous version."
- Exit.

### 5d. Save backup to repo

After a verified-good upload, copy the updated HTML to the backup location and commit:

```bash
cp /tmp/dashboard_updated.html backups/fraym_kenya_dashboard_backup.html

git config user.email "automation@geopoll.com"
git config user.name "GeoPoll Automation"
git add backups/fraym_kenya_dashboard_backup.html
git commit -m "chore: Fraym Kenya dashboard backup — $(date -u +%Y-%m-%dT%H:%MZ) [automated]"
git push origin HEAD
```

If the git push fails, log a warning but do **not** treat it as a run failure — the artifact is already updated successfully.

---

## Step 6 — Report

Output the final run summary in this format:

```
=== Fraym Kenya Quota Refresh — <savedAt> ===
Completed rows : <new_completed>  (Δ <+/- delta_completed> vs baseline <baseline_completed>)
Rejected rows  : <new_rejected>   (Δ <+/- delta_rejected>  vs baseline <baseline_rejected>)
Distinct operators : <distinct_operators>
Artifact updated   : YES
Upload status      : success
```

---

## Quick reference — MCP tools used

| Step | Tool |
|------|------|
| Fetch artifact | `mcp__GeoPoll-Admin__artifact_get` |
| Pull poll data | `mcp__GeoPoll-Admin__live_data_get_report_flat` |
| Get upload token | `mcp__GeoPoll-Admin__artifact_get_upload_token` |
| Send failure alert | `mcp__GeoPoll-Admin__outlook_send_email` |
