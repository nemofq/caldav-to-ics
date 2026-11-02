# caldav-to-ics

Open-source tool that syncs a CalDAV server into a single ICS file on Vercel Blob, so
calendar services (Google Calendar, GAS-ICS-Sync, ...) can subscribe to it. Next.js
frontend, Python/Flask function as the backend. It must work with any CalDAV server.

## Layout

- `api/sync.py`: Flask app, deployed as the Vercel Python function `/api/sync`. Fetches
  every CalDAV object, keeps VEVENTs, folds cancelled recurrence overrides into EXDATEs,
  adds missing VTIMEZONEs and uploads one ICS with `put_blob`.
- `app/`: Next.js page showing the last sync time (from Blob `list()` metadata) and a
  Sync Now button.
- `vercel.json`: daily cron (`0 0 * * *`) calling `/api/sync`.
- `.env.example` and the README "Run Locally" table: every env var the code reads.

## Commands

```bash
pnpm install
pnpm run lint
pnpm run build
pnpm run dev   # Next.js on :3000 and Flask on :5328 (needs uv)
uv venv && uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The pytest suite in `tests/` runs offline: fake credentials, mocked CalDAV and Blob,
sockets disabled. CI (`.github/workflows/ci.yml`) runs lint, build and tests on pull
requests.

## Rules

- **Keep it generic.** No assumptions tied to one CalDAV server or one deployment.
  Server-specific workarounds (e.g. for Feishu/Lark) are fine only when they are harmless
  on other servers, with a comment naming the server that needs them. No personal
  deployment details (project names, schedules, URLs).
- **Keep `.env.example` and the README env table in sync with the code.** When the code
  starts reading an env var, or one changes meaning, update both in the same change, and
  mark optional ones as optional.
- **No commit attribution lines** (no `Co-Authored-By` or `Claude-Session` trailers) in this
  repo.
- **Secrets**: never print env var values or put credentials, real calendar data or an ICS
  URL in code, logs, commits, issues or PRs. The ICS URL is secret, since an unguessable
  `BLOB_PATH` is its only protection: it is printed to the function logs and never returned
  by `/api/sync`.
- Don't run `/api/sync` or `sync_caldav_to_blob()` with real credentials from a session; it
  overwrites the configured Blob file.
- Keep `cache_control_max_age=60` on the Blob upload; without it Blob serves the file with
  a 30-day cache.
- `CRON_SECRET` is optional and both modes must keep working: unset (or empty) means
  `/api/sync` is open; set means it requires `Authorization: Bearer <CRON_SECRET>`, which
  Vercel cron sends automatically, and the Sync Now button prompts for it on a 401.
- **pnpm only, never npm.** Only use dependency versions published at least one day ago
  (`minimumReleaseAge` in `pnpm-workspace.yaml`, `min-release-age` in `.npmrc`; for Python,
  check the PyPI upload date before raising a lower bound).
- **Python deps: `uv pip install -r requirements.txt`**, never `uv pip sync`: the file isn't
  a lockfile, so sync strips transitive dependencies.

## Workflow

- Branch from `main`, one PR per task; write a plan first for multi-file changes.
