"""Shared fixtures for the api/sync.py tests.

Every test runs with fake credentials, a recording stand-in for put_blob, a
fake CalDAV client and sockets disabled, so no test can reach CalDAV or Blob
even when the real secrets are present in the environment.
"""
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

import sync

FIXTURES = Path(__file__).parent / "fixtures"

FAKE_ICS_URL = "https://fake-store.public.blob.vercel-storage.invalid/calendar-test.ics"

FAKE_ENV = {
    "CALDAV_URL": "https://caldav.example.invalid/",
    "CALDAV_USERNAME": "test-user",
    "CALDAV_PASSWORD": "test-password",
    "BLOB_PATH": "calendar-test.ics",
}

# Real credentials that must never be visible to the code under test
SCRUBBED_ENV = [
    "BLOB_READ_WRITE_TOKEN",
    "VERCEL_BLOB_READ_WRITE_TOKEN",
    "VERCEL_OIDC_TOKEN",
    "CRON_SECRET",
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("Network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def fake_env(monkeypatch):
    for name in SCRUBBED_ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in FAKE_ENV.items():
        monkeypatch.setenv(name, value)
    return dict(FAKE_ENV)


@pytest.fixture(autouse=True)
def uploads(monkeypatch):
    """Replace put_blob with a recorder; each call is stored as a dict."""
    calls = []

    def fake_put_blob(path, data, **kwargs):
        calls.append({"path": path, "data": data, **kwargs})
        return SimpleNamespace(url=FAKE_ICS_URL, pathname=path)

    monkeypatch.setattr(sync, "put_blob", fake_put_blob)
    return calls


class FakeObject:
    """A CalDAV object. lazy=True mimics caldav 3.x stubs that need load()."""

    def __init__(self, data, lazy=False, load_error=None):
        self._payload = data
        self.data = None if lazy else data
        self._load_error = load_error
        self.loaded = False

    def load(self):
        self.loaded = True
        if self._load_error:
            raise self._load_error
        self.data = self._payload
        return self


class FakeCalendar:
    def __init__(self, name, objects=(), error=None):
        self.name = name
        self._objects = list(objects)
        self._error = error

    def objects(self):
        if self._error:
            raise self._error
        return list(self._objects)


class FakeServer:
    """Stands in for caldav.DAVClient: the class, the client and the principal."""

    def __init__(self):
        self.calendars_list = []
        self.connections = []

    def __call__(self, url, username, password):
        self.connections.append({"url": url, "username": username, "password": password})
        return self

    def principal(self):
        return self

    def calendars(self):
        return self.calendars_list


@pytest.fixture(autouse=True)
def caldav_server(monkeypatch):
    server = FakeServer()
    monkeypatch.setattr(sync, "DAVClient", server)
    return server


@pytest.fixture
def fixture_ics():
    def load(name):
        return (FIXTURES / name).read_bytes()

    return load


@pytest.fixture
def fake_object():
    return FakeObject


@pytest.fixture
def fake_calendar():
    return FakeCalendar
