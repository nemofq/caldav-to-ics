# caldav-to-ics

Open-source tool that syncs a CalDAV server into a single ICS file on Vercel Blob, so
calendar services (Google Calendar, GAS-ICS-Sync, ...) can subscribe to it. Next.js
frontend, Python/Flask function as the backend. It must work with any CalDAV server.

## Layout

- `api/sync.py`: Flask app, deployed as a private Vercel Python function. Fetches every
  CalDAV object, keeps VEVENTs, folds cancelled recurrence overrides into EXDATEs, adds
  missing VTIMEZONEs and uploads one ICS with `put_blob`. If every calendar fails to load
  it raises instead of uploading an empty ICS. It answers POST on any path, because the
  path of the scheduler's request isn't documented.
- `vercel.json`: gives `api/sync.py` a `schedule/v1beta` trigger, which makes it private
  (no public URL, only Vercel's scheduler can invoke it, so there is no secret), and
  defines the `sync` schedule that runs it hourly.
- `app/`: Next.js page showing the last sync time (from Blob `list()` metadata, in
  `app/lastSync.js`), an overdue warning after 3 hours without an upload, and a Sync Now
  button. The button calls the server action in `app/actions.js`, which asks the scheduler
  to run the `sync` schedule now through `@vercel/schedules` (authenticated by the
  deployment's OIDC token) and returns once the run is accepted. It refuses when the ICS
  was uploaded in the last 10 minutes; a failed sync uploads nothing, so it can be retried
  at once. Under `pnpm run dev` there is no scheduler, so the action posts to the local
  Flask server instead.
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
  by the sync function.
- Don't run a sync (`sync_caldav_to_blob()`, the Flask app or Sync Now) with real
  credentials from a session; it overwrites the configured Blob file.
- Keep `cache_control_max_age=60` on the Blob upload; without it Blob serves the file with
  a 30-day cache.
- The sync function must stay private (the `schedule/v1beta` trigger in `vercel.json`):
  nothing else protects it. Sync Now is open to anyone who can load the page, so keep the
  cooldown in `app/actions.js`.
- **pnpm only, never npm.** Only use dependency versions published at least one day ago
  (`minimumReleaseAge` in `pnpm-workspace.yaml`, `min-release-age` in `.npmrc`; for Python,
  check the PyPI upload date before raising a lower bound). `pnpm-lock.yaml` is gitignored,
  so installs resolve the newest versions allowed by the `package.json` ranges. ESLint stays
  on v9: `.ncurc.json` rejects `eslint` upgrades.
- **Python deps: `uv pip install -r requirements.txt`**, never `uv pip sync`: the file isn't
  a lockfile, so sync strips transitive dependencies.

## Workflow

- Branch from `main`, one PR per task; write a plan first for multi-file changes.
