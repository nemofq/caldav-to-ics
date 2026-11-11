"""Tests for api/sync.py: cancelled-occurrence folding, VTIMEZONEs and ICS building."""
import json
import logging
from datetime import date

import pytest
from icalendar import Calendar

import sync
from conftest import FAKE_ENV, FAKE_ICS_URL


def vevents(calendar):
    return [c for c in calendar.subcomponents if c.name == "VEVENT"]


def vtimezone_ids(calendar):
    return [str(c["TZID"]) for c in calendar.subcomponents if c.name == "VTIMEZONE"]


def combined(*ics_documents):
    """Build a calendar the way sync does: VEVENTs only, from several documents."""
    calendar = Calendar()
    for document in ics_documents:
        for component in Calendar.from_ical(document).walk("VEVENT"):
            calendar.add_component(component)
    return calendar


def uploaded_calendar(uploads):
    assert len(uploads) == 1
    return Calendar.from_ical(uploads[0]["data"])


# --- fold_cancelled_overrides -------------------------------------------------


class TestFoldCancelledOverrides:
    def test_cancelled_override_becomes_exdate_on_master(self, fixture_ics):
        calendar = combined(fixture_ics("recurring_with_overrides.ics"))

        assert sync.fold_cancelled_overrides(calendar) == 1

        master = next(e for e in vevents(calendar) if "RECURRENCE-ID" not in e)
        exdates = [d.dt for d in master["EXDATE"].dts]
        assert len(exdates) == 1
        assert exdates[0].isoformat() == "2026-10-12T10:00:00+08:00"
        assert str(exdates[0].tzinfo) == "Asia/Shanghai"
        assert b"EXDATE;TZID=Asia/Shanghai:20261012T100000" in calendar.to_ical()

    def test_cancelled_override_is_removed(self, fixture_ics):
        calendar = combined(fixture_ics("recurring_with_overrides.ics"))

        sync.fold_cancelled_overrides(calendar)

        statuses = [str(e.get("STATUS", "")) for e in vevents(calendar)]
        assert "CANCELLED" not in statuses
        assert len(vevents(calendar)) == 2

    def test_rescheduled_override_is_kept(self, fixture_ics):
        calendar = combined(fixture_ics("recurring_with_overrides.ics"))

        sync.fold_cancelled_overrides(calendar)

        overrides = [e for e in vevents(calendar) if "RECURRENCE-ID" in e]
        assert len(overrides) == 1
        assert str(overrides[0]["SUMMARY"]) == "Weekly standup (moved)"

    def test_all_day_override_folds_into_date_exdate(self, fixture_ics):
        calendar = combined(fixture_ics("all_day_recurring.ics"))

        assert sync.fold_cancelled_overrides(calendar) == 1

        (master,) = vevents(calendar)
        assert [d.dt for d in master["EXDATE"].dts] == [date(2026, 11, 1)]
        assert b"EXDATE;VALUE=DATE:20261101" in calendar.to_ical()

    def test_cancelled_override_without_master_is_left_alone(self, fixture_ics):
        calendar = combined(fixture_ics("recurring_with_overrides.ics"))
        master = next(e for e in vevents(calendar) if "RECURRENCE-ID" not in e)
        calendar.subcomponents.remove(master)

        assert sync.fold_cancelled_overrides(calendar) == 0
        assert len(vevents(calendar)) == 2

    def test_status_match_is_case_insensitive(self, fixture_ics):
        document = fixture_ics("recurring_with_overrides.ics").replace(
            b"STATUS:CANCELLED", b"STATUS:cancelled"
        )
        calendar = combined(document)

        assert sync.fold_cancelled_overrides(calendar) == 1

    def test_cancelled_single_event_is_not_touched(self, fixture_ics):
        document = fixture_ics("utc_event.ics").replace(
            b"SUMMARY:UTC event", b"SUMMARY:UTC event\r\nSTATUS:CANCELLED"
        )
        calendar = combined(document)

        assert sync.fold_cancelled_overrides(calendar) == 0
        assert len(vevents(calendar)) == 1

    def test_overrides_only_fold_into_their_own_uid(self, fixture_ics):
        calendar = combined(
            fixture_ics("recurring_with_overrides.ics"),
            fixture_ics("all_day_recurring.ics"),
        )

        assert sync.fold_cancelled_overrides(calendar) == 2

        masters = {
            str(e["UID"]): e for e in vevents(calendar) if "RECURRENCE-ID" not in e
        }
        assert len(masters["weekly-standup@example.invalid"]["EXDATE"].dts) == 1
        assert len(masters["monthly-review@example.invalid"]["EXDATE"].dts) == 1


# --- sync_caldav_to_blob: ICS building ---------------------------------------


class TestSyncBuildsIcs:
    def test_combines_events_from_every_calendar(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        caldav_server.calendars_list = [
            fake_calendar("Work", [fake_object(fixture_ics("recurring_with_overrides.ics"))]),
            fake_calendar("Personal", [fake_object(fixture_ics("utc_event.ics"))]),
        ]

        result = sync.sync_caldav_to_blob()

        # 3 VEVENTs + 1 VEVENT, minus the folded cancelled override
        assert result == {
            "status": "success",
            "message": "Successfully synchronized 3 events from 2 calendars",
        }
        uids = sorted(str(e["UID"]) for e in vevents(uploaded_calendar(uploads)))
        assert uids == [
            "utc-event@example.invalid",
            "weekly-standup@example.invalid",
            "weekly-standup@example.invalid",
        ]

    def test_connects_with_configured_credentials(self, caldav_server, fake_env):
        sync.sync_caldav_to_blob()

        assert caldav_server.connections == [
            {
                "url": fake_env["CALDAV_URL"],
                "username": fake_env["CALDAV_USERNAME"],
                "password": fake_env["CALDAV_PASSWORD"],
            }
        ]

    def test_sets_calendar_properties(self, uploads):
        sync.sync_caldav_to_blob()

        calendar = uploaded_calendar(uploads)
        assert str(calendar["PRODID"]) == "-//CalDAV to ICS//EN"
        assert str(calendar["VERSION"]) == "2.0"
        assert str(calendar["CALSCALE"]) == "GREGORIAN"
        assert str(calendar["METHOD"]) == "PUBLISH"

    def test_only_vevents_are_copied(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        caldav_server.calendars_list = [
            fake_calendar(
                "Mixed",
                [
                    fake_object(fixture_ics("todo.ics")),
                    fake_object(fixture_ics("utc_event.ics")),
                ],
            )
        ]

        result = sync.sync_caldav_to_blob()

        calendar = uploaded_calendar(uploads)
        assert [c.name for c in calendar.subcomponents] == ["VEVENT"]
        assert result["message"] == "Successfully synchronized 1 events from 1 calendars"

    def test_loads_lazy_objects_and_skips_ghosts(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        lazy = fake_object(fixture_ics("utc_event.ics"), lazy=True)
        ghost = fake_object(fixture_ics("new_york_event.ics"), lazy=True,
                            load_error=Exception("404 Not Found"))
        empty = fake_object(b"", lazy=True)
        caldav_server.calendars_list = [fake_calendar("Work", [lazy, ghost, empty])]

        result = sync.sync_caldav_to_blob()

        assert lazy.loaded and ghost.loaded and empty.loaded
        uids = [str(e["UID"]) for e in vevents(uploaded_calendar(uploads))]
        assert uids == ["utc-event@example.invalid"]
        assert result["message"] == "Successfully synchronized 1 events from 1 calendars"

    def test_already_loaded_objects_are_not_reloaded(
        self, caldav_server, fake_calendar, fake_object, fixture_ics
    ):
        loaded = fake_object(fixture_ics("utc_event.ics"))
        caldav_server.calendars_list = [fake_calendar("Work", [loaded])]

        sync.sync_caldav_to_blob()

        assert not loaded.loaded

    def test_failing_calendar_does_not_abort_sync(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads, capsys
    ):
        caldav_server.calendars_list = [
            fake_calendar("Broken", error=Exception("REPORT not supported")),
            fake_calendar("Work", [fake_object(fixture_ics("utc_event.ics"))]),
        ]

        result = sync.sync_caldav_to_blob()

        assert "Error processing calendar Broken: REPORT not supported" in capsys.readouterr().err
        assert len(vevents(uploaded_calendar(uploads))) == 1
        assert result["message"] == "Successfully synchronized 1 events from 2 calendars"
        assert result["skipped_calendars"] == 1

    def test_every_calendar_failing_raises_without_uploading(
        self, caldav_server, fake_calendar, uploads
    ):
        caldav_server.calendars_list = [
            fake_calendar("Work", error=TimeoutError("read timed out")),
            fake_calendar("Home", error=TimeoutError("read timed out")),
        ]

        with pytest.raises(sync.SyncError, match=r"All 2 calendars failed to load \(TimeoutError\)"):
            sync.sync_caldav_to_blob()

        assert uploads == []

    def test_empty_server_still_uploads_a_valid_calendar(self, uploads):
        result = sync.sync_caldav_to_blob()

        assert vevents(uploaded_calendar(uploads)) == []
        assert result["message"] == "Successfully synchronized 0 events from 0 calendars"

    def test_published_ics_contains_the_exdate(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        caldav_server.calendars_list = [
            fake_calendar("Work", [fake_object(fixture_ics("recurring_with_overrides.ics"))])
        ]

        sync.sync_caldav_to_blob()

        assert b"EXDATE;TZID=Asia/Shanghai:20261012T100000" in uploads[0]["data"]
        assert b"STATUS:CANCELLED" not in uploads[0]["data"]


# --- sync_caldav_to_blob: missing timezones ----------------------------------


class TestSyncAddsMissingTimezones:
    def test_emits_one_vtimezone_per_referenced_tzid(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        caldav_server.calendars_list = [
            fake_calendar(
                "Work",
                [
                    fake_object(fixture_ics("recurring_with_overrides.ics")),
                    fake_object(fixture_ics("new_york_event.ics")),
                ],
            ),
            fake_calendar("Personal", [fake_object(fixture_ics("utc_event.ics"))]),
        ]

        sync.sync_caldav_to_blob()

        assert sorted(vtimezone_ids(uploaded_calendar(uploads))) == [
            "America/New_York",
            "Asia/Shanghai",
        ]

    def test_source_vtimezones_are_not_duplicated(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        # Two objects that each carry their own Asia/Shanghai VTIMEZONE
        document = fixture_ics("recurring_with_overrides.ics")
        caldav_server.calendars_list = [
            fake_calendar("Work", [fake_object(document), fake_object(document)])
        ]

        sync.sync_caldav_to_blob()

        assert vtimezone_ids(uploaded_calendar(uploads)) == ["Asia/Shanghai"]

    def test_floating_and_utc_events_need_no_vtimezone(
        self, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        caldav_server.calendars_list = [
            fake_calendar(
                "Work",
                [
                    fake_object(fixture_ics("utc_event.ics")),
                    fake_object(fixture_ics("all_day_recurring.ics")),
                ],
            )
        ]

        sync.sync_caldav_to_blob()

        assert vtimezone_ids(uploaded_calendar(uploads)) == []


# --- sync_caldav_to_blob: upload and configuration ---------------------------


class TestSyncUpload:
    def test_uploads_once_with_expected_parameters(self, uploads, fake_env):
        sync.sync_caldav_to_blob()

        assert len(uploads) == 1
        call = uploads[0]
        assert call["path"] == fake_env["BLOB_PATH"]
        assert call["access"] == "public"
        assert call["content_type"] == "text/calendar; charset=utf-8"
        assert call["add_random_suffix"] is False
        assert call["allow_overwrite"] is True

    def test_cache_control_max_age_is_60(self, uploads):
        # Without it Blob serves the file with max-age=2592000 (30 days)
        sync.sync_caldav_to_blob()

        assert uploads[0]["cache_control_max_age"] == 60

    def test_ics_url_is_logged_but_not_returned(self, capsys):
        result = sync.sync_caldav_to_blob()

        assert FAKE_ICS_URL in capsys.readouterr().out
        assert FAKE_ICS_URL not in str(result)

    def test_missing_blob_path_raises_before_connecting(
        self, monkeypatch, caldav_server, uploads
    ):
        monkeypatch.delenv("BLOB_PATH")

        with pytest.raises(ValueError, match="BLOB_PATH"):
            sync.sync_caldav_to_blob()

        assert caldav_server.connections == []
        assert uploads == []

    @pytest.mark.parametrize("name", ["CALDAV_URL", "CALDAV_USERNAME", "CALDAV_PASSWORD"])
    def test_missing_caldav_setting_raises_before_connecting(
        self, monkeypatch, caldav_server, uploads, name
    ):
        monkeypatch.delenv(name)

        with pytest.raises(ValueError, match="CALDAV_URL, CALDAV_USERNAME, CALDAV_PASSWORD"):
            sync.sync_caldav_to_blob()

        assert caldav_server.connections == []
        assert uploads == []


# --- /api/sync route ----------------------------------------------------------


def ics_uploads(uploads):
    return [call for call in uploads if call["path"] == FAKE_ENV["BLOB_PATH"]]


def status_uploads(uploads):
    path = FAKE_ENV["BLOB_PATH"] + sync.STATUS_SUFFIX
    return [json.loads(call["data"]) for call in uploads if call["path"] == path]


@pytest.fixture
def client():
    sync.app.config["TESTING"] = True
    return sync.app.test_client()


class TestSyncRoute:
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_success_returns_200_json(self, client, uploads, method):
        response = getattr(client, method)("/api/sync")

        assert response.status_code == 200
        assert response.get_json() == {
            "status": "success",
            "message": "Successfully synchronized 0 events from 0 calendars",
        }
        assert len(ics_uploads(uploads)) == 1

    def test_error_returns_500_json(self, client, monkeypatch, uploads):
        monkeypatch.delenv("BLOB_PATH")

        response = client.get("/api/sync")

        assert response.status_code == 500
        assert response.get_json() == {
            "status": "error",
            "message": "Missing required environment variable: BLOB_PATH",
        }
        assert uploads == []

    def test_response_never_contains_ics_url(self, client):
        response = client.get("/api/sync")

        assert FAKE_ICS_URL not in response.get_data(as_text=True)


# --- /api/sync: status file and failure logging --------------------------------


class TestSyncStatus:
    def test_success_records_ok_status(self, client, uploads):
        client.get("/api/sync")

        [status] = status_uploads(uploads)
        assert status["ok"] is True
        assert status["error"] is None
        assert status["skipped_calendars"] == 0
        assert status["attempted_at"]

    def test_status_upload_parameters(self, client, uploads):
        client.get("/api/sync")

        [call] = [c for c in uploads if c["path"].endswith(sync.STATUS_SUFFIX)]
        assert call["access"] == "public"
        assert call["content_type"] == "application/json"
        assert call["add_random_suffix"] is False
        assert call["allow_overwrite"] is True
        assert call["cache_control_max_age"] == 60

    def test_skipped_calendars_are_recorded(
        self, client, caldav_server, fake_calendar, fake_object, fixture_ics, uploads
    ):
        caldav_server.calendars_list = [
            fake_calendar("Broken", error=Exception("boom")),
            fake_calendar("Work", [fake_object(fixture_ics("utc_event.ics"))]),
        ]

        assert client.get("/api/sync").status_code == 200

        [status] = status_uploads(uploads)
        assert status["ok"] is True
        assert status["skipped_calendars"] == 1

    def test_failure_records_status_without_details_and_logs_error(
        self, client, caldav_server, fake_calendar, uploads, capsys
    ):
        def refuse():
            raise ConnectionError("https://caldav.example.invalid/ test-user refused")

        caldav_server.principal = refuse

        response = client.get("/api/sync")

        assert response.status_code == 500
        assert ics_uploads(uploads) == []
        [status] = status_uploads(uploads)
        assert status["ok"] is False
        # Library messages can carry the CalDAV URL or username: type only
        assert status["error"] == "ConnectionError"
        assert "Sync failed" in capsys.readouterr().err

    def test_all_calendars_failing_records_the_reason(
        self, client, caldav_server, fake_calendar, uploads
    ):
        caldav_server.calendars_list = [fake_calendar("Work", error=TimeoutError("slow"))]

        assert client.get("/api/sync").status_code == 500

        assert ics_uploads(uploads) == []
        [status] = status_uploads(uploads)
        assert status == {**status, "ok": False, "error": "All 1 calendars failed to load (TimeoutError)"}

    def test_status_never_contains_ics_url_or_credentials(self, client, uploads, fake_env):
        client.get("/api/sync")

        [call] = [c for c in uploads if c["path"].endswith(sync.STATUS_SUFFIX)]
        text = call["data"].decode()
        for secret in [FAKE_ICS_URL, *fake_env.values()]:
            assert secret not in text

    def test_status_upload_failure_does_not_change_the_result(
        self, client, monkeypatch, uploads
    ):
        real_put_blob = sync.put_blob

        def put_blob(path, data, **kwargs):
            if path.endswith(sync.STATUS_SUFFIX):
                raise RuntimeError("blob down")
            return real_put_blob(path, data, **kwargs)

        monkeypatch.setattr(sync, "put_blob", put_blob)

        response = client.get("/api/sync")

        assert response.status_code == 200
        assert len(ics_uploads(uploads)) == 1

    def test_without_blob_path_no_status_is_written(self, client, monkeypatch, uploads):
        monkeypatch.delenv("BLOB_PATH")

        assert client.get("/api/sync").status_code == 500
        assert uploads == []


class TestCaldavLogging:
    def test_ical_fixup_warning_is_dropped(self, caplog):
        with caplog.at_level(logging.WARNING, logger="caldav"):
            logging.getLogger("caldav").warning(
                "Ical data was modified to avoid compatibility issues\nSUMMARY:Private"
            )
            logging.getLogger("caldav").warning("Some other caldav warning")

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["Some other caldav warning"]


# --- /api/sync: optional CRON_SECRET -----------------------------------------

CRON_SECRET = "test-cron-secret"


class TestCronSecret:
    @pytest.fixture
    def with_secret(self, monkeypatch):
        monkeypatch.setenv("CRON_SECRET", CRON_SECRET)

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_without_cron_secret_anyone_can_sync(self, client, uploads, method):
        response = getattr(client, method)("/api/sync")

        assert response.status_code == 200
        assert len(ics_uploads(uploads)) == 1

    def test_empty_cron_secret_counts_as_unset(self, client, monkeypatch, uploads):
        monkeypatch.setenv("CRON_SECRET", "")

        assert client.get("/api/sync").status_code == 200
        assert len(ics_uploads(uploads)) == 1

    @pytest.mark.parametrize("method", ["get", "post"])
    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"Authorization": "Bearer wrong-secret"},
            {"Authorization": CRON_SECRET},
            {"Authorization": f"bearer {CRON_SECRET}"},
            {"Authorization": f"Bearer {CRON_SECRET}x"},
            {"Authorization": f"Basic {CRON_SECRET}"},
            {"Authorization": "Bearer éè"},
        ],
        ids=["missing", "wrong", "no-scheme", "lowercase-scheme", "suffix", "basic", "non-ascii"],
    )
    def test_rejects_without_valid_bearer_and_does_not_sync(
        self, client, with_secret, caldav_server, uploads, method, headers
    ):
        response = getattr(client, method)("/api/sync", headers=headers)

        assert response.status_code == 401
        assert response.get_json() == {"status": "error", "message": "Unauthorized"}
        assert caldav_server.connections == []
        # Nothing at all, not even a status file
        assert uploads == []

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_accepts_the_bearer_vercel_cron_sends(
        self, client, with_secret, uploads, method
    ):
        response = getattr(client, method)(
            "/api/sync", headers={"Authorization": f"Bearer {CRON_SECRET}"}
        )

        assert response.status_code == 200
        assert len(ics_uploads(uploads)) == 1

    def test_unauthorized_response_does_not_leak_the_secret(self, client, with_secret):
        response = client.get("/api/sync", headers={"Authorization": "Bearer nope"})

        assert CRON_SECRET not in response.get_data(as_text=True)
