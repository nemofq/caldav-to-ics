import hmac
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv
from caldav import DAVClient
from icalendar import Calendar
from vercel.blob.sync import put_blob
from flask import Flask, jsonify, request

app = Flask(__name__)

# load local env
load_dotenv('.env.local')

# Next to the ICS, at BLOB_PATH + this suffix, every authorized sync attempt
# records its outcome, so a missed or failed run stays visible on the status
# page after the function logs have expired.
STATUS_SUFFIX = ".status.json"


class SyncError(Exception):
    """A sync failure whose message is safe to publish in the status file."""


class _DropIcalFixupWarnings(logging.Filter):
    """Drop caldav's "Ical data was modified" warning.

    caldav logs it whenever it cleans up a server's iCalendar data (Feishu
    sends trailing spaces, for example). It is harmless, and it copies the
    event's text, including titles and meeting links, into the logs.
    """

    def filter(self, record):
        return not str(record.msg).startswith("Ical data was modified")


logging.getLogger("caldav").addFilter(_DropIcalFixupWarnings())

def fold_cancelled_overrides(calendar):
    """Replace cancelled recurrence overrides with EXDATEs on their masters.

    Feishu deletes a previously edited occurrence by marking its override
    (RECURRENCE-ID) STATUS:CANCELLED, without adding an EXDATE to the master.
    That's valid iCalendar, but consumers such as GAS-ICS-Sync drop cancelled
    events outright, which resurrects the occurrence from the RRULE. EXDATE
    is the form every consumer understands. Returns the number folded.
    """
    vevents = [c for c in calendar.subcomponents if c.name == 'VEVENT']
    masters = {}
    for component in vevents:
        if 'RECURRENCE-ID' not in component:
            masters.setdefault(str(component.get('UID')), []).append(component)

    folded = 0
    for component in vevents:
        if ('RECURRENCE-ID' not in component
                or str(component.get('STATUS', '')).upper() != 'CANCELLED'):
            continue
        uid_masters = masters.get(str(component.get('UID')))
        if not uid_masters:
            continue
        for master in uid_masters:
            # Same value type and TZID as the RECURRENCE-ID, so it matches the
            # instance the RRULE generates
            master.add('EXDATE', component['RECURRENCE-ID'].dt)
        calendar.subcomponents.remove(component)
        folded += 1
    return folded

def sync_caldav_to_blob():

    # Read configuration from environment variables
    caldav_url = os.environ.get("CALDAV_URL")
    caldav_username = os.environ.get("CALDAV_USERNAME")
    caldav_password = os.environ.get("CALDAV_PASSWORD")
    blob_path = os.environ.get("BLOB_PATH")

    # Validate BLOB_PATH is provided
    if not blob_path:
        raise ValueError("Missing required environment variable: BLOB_PATH")

    # Validate required environment variables
    if not all([caldav_url, caldav_username, caldav_password]):
        raise ValueError("Missing required environment variables: CALDAV_URL, CALDAV_USERNAME, CALDAV_PASSWORD")

    # Connect to CalDAV server
    client = DAVClient(
        url=caldav_url,
        username=caldav_username,
        password=caldav_password
    )

    # Get all calendars
    calendars = client.principal().calendars()

    # Create an integrated iCalendar
    combined_calendar = Calendar()
    combined_calendar.add('prodid', '-//CalDAV to ICS//EN')
    combined_calendar.add('version', '2.0')
    combined_calendar.add('calscale', 'GREGORIAN')
    combined_calendar.add('method', 'PUBLISH')

    # Collect all events from all calendars
    event_count = 0
    calendar_count = len(calendars)
    failed_calendars = 0
    failure_types = set()

    for calendar in calendars:
        try:
            # Use objects() instead of events() — caldav 3.x events() uses
            # REPORT which some servers (e.g. Feishu) don't support properly
            events = calendar.objects()

            for event in events:
                # caldav 3.x returns lazy stubs — explicitly fetch data
                # Wrap in try/except to skip 404s (ghost entries on server)
                try:
                    if not event.data:
                        event.load()
                except Exception:
                    continue

                event_data = event.data
                if not event_data:
                    continue

                cal = Calendar.from_ical(event_data)

                # Only add VEVENT components to the integrated calendar
                for component in cal.walk():
                    if component.name == 'VEVENT':
                        combined_calendar.add_component(component)
                        event_count += 1
        except Exception as e:
            failed_calendars += 1
            failure_types.add(type(e).__name__)
            print(f"Error processing calendar {calendar.name}: {str(e)}", file=sys.stderr)

    # One broken calendar is skipped, but if every calendar failed (e.g. the
    # server timed out) uploading would replace the ICS with an empty one
    if calendar_count and failed_calendars == calendar_count:
        # Exception type names only: messages can carry the CalDAV URL
        reasons = ", ".join(sorted(failure_types))
        raise SyncError(f"All {calendar_count} calendars failed to load ({reasons})")

    event_count -= fold_cancelled_overrides(combined_calendar)

    # Only VEVENTs are copied above, so emit a VTIMEZONE for every TZID they
    # reference. Without these, some clients treat TZID times as floating/UTC,
    # which breaks EXDATE matching and resurrects deleted occurrences.
    combined_calendar.add_missing_timezones()

    # Convert the integrated calendar to iCalendar data
    ical_data = combined_calendar.to_ical()

    # Upload to Vercel Blob. The sync put_blob() reuses the SDK's
    # process-wide default session, so nothing leaks per invocation.
    uploaded = put_blob(
        blob_path,
        ical_data,
        access="public",
        content_type="text/calendar; charset=utf-8",
        add_random_suffix=False,
        # 60s is Blob's floor — it clamps anything lower up to this. Required:
        # omitting it entirely serves max-age=2592000 (30 days).
        cache_control_max_age=60,
        allow_overwrite=True,
    )

    # Logged, never returned: /api/sync is unauthenticated, so the response
    # body must not carry the secret ICS URL. Function logs are owner-only.
    print(f"Uploaded ICS to {uploaded.url}")

    result = {
        "status": "success",
        "message": f"Successfully synchronized {event_count} events from {calendar_count} calendars"
    }
    if failed_calendars:
        result["skipped_calendars"] = failed_calendars
    return result

def record_status(ok, error=None, skipped_calendars=0):
    """Upload the outcome of this sync attempt next to the ICS.

    Holds only a time, a flag, a count and a short reason that never
    contains URLs, credentials or calendar data. Failures here are logged and
    swallowed, so they never change the sync's own result.
    """
    blob_path = os.environ.get("BLOB_PATH")
    if not blob_path:
        return
    status = {
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "error": error,
        "skipped_calendars": skipped_calendars,
    }
    try:
        put_blob(
            blob_path + STATUS_SUFFIX,
            json.dumps(status).encode(),
            access="public",
            content_type="application/json",
            add_random_suffix=False,
            cache_control_max_age=60,
            allow_overwrite=True,
        )
    except Exception:
        print("Error recording sync status:", file=sys.stderr)
        traceback.print_exc()

def public_reason(error):
    """A short failure reason that is safe to publish: no URLs or data."""
    if isinstance(error, SyncError):
        return str(error)
    # Library messages can carry the CalDAV URL, so only the type is kept
    return type(error).__name__

def is_authorized(req):
    """Check the request against CRON_SECRET, if one is configured.

    Without CRON_SECRET anyone can trigger a sync, as before. With it, the
    request must carry "Authorization: Bearer <CRON_SECRET>", which Vercel
    cron sends automatically when the variable is set on the project.
    """
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        return True
    expected = f"Bearer {secret}".encode()
    provided = req.headers.get("Authorization", "").encode()
    # Constant-time; bytes so a non-ASCII header is a mismatch, not an error
    return hmac.compare_digest(provided, expected)

# Handler for Vercel Serverless function
@app.route("/api/sync", methods=['POST', 'GET'])
def api_sync():
    # Checked before anything else: an unauthorized request must not sync
    if not is_authorized(request):
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 401

    try:
        result = sync_caldav_to_blob()
    except Exception as e:
        # stderr shows up as an error in the Vercel logs
        print("Sync failed:", file=sys.stderr)
        traceback.print_exc()
        record_status(False, error=public_reason(e))
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

    record_status(True, skipped_calendars=result.get("skipped_calendars", 0))
    return jsonify(result), 200
