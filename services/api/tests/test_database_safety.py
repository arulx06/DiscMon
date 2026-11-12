"""Run without a live database: python -m unittest discover -s tests -p test_database_safety.py."""

from __future__ import annotations

import asyncio
import importlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import make_url

API_ROOT = Path(__file__).resolve().parents[1]
URL = "postgresql+psycopg://dummy:dummy-secret@127.0.0.1:1/discmon_test"
SAFE_ENV = {"APP_ENV": "test", "DATABASE_URL": URL, "TEST_DATABASE_URL": URL}
# Standalone unittest imports the guard but never opens a connection.
with patch.dict(os.environ, SAFE_ENV, clear=True):
    guard = importlib.import_module("conftest")


def environment(url: str = URL) -> dict[str, str]:
    return {**SAFE_ENV, "DATABASE_URL": url, "TEST_DATABASE_URL": url}


def invalid_environments() -> list[dict[str, str]]:
    cases = [
        {key: value for key, value in SAFE_ENV.items() if key != missing}
        for missing in ("APP_ENV", "DATABASE_URL", "TEST_DATABASE_URL")
    ]
    cases += [{**SAFE_ENV, "APP_ENV": value} for value in ("production", "development", "TEST", "")]
    cases += [
        environment(url)
        for url in (
            URL.replace("discmon_test", "discmon"),
            URL.replace("discmon_test", "test"),
            URL.replace("127.0.0.1", "db.example.invalid"),
            URL.replace("127.0.0.1", "192.0.2.1"),
            URL.replace("127.0.0.1", "127.0.0.1,192.0.2.1"),
            URL.replace("127.0.0.1:1", ""),
            URL.replace(":1/", ":bad/"),
            URL.replace(":1/", ":0/"),
            URL.replace(":1/", ":65536/"),
            URL.replace("postgresql+psycopg", "sqlite"),
            URL.replace("postgresql+psycopg", "postgresql+asyncpg"),
            "not-a-url-dummy-secret",
            URL + "?host=192.0.2.1",
            URL + "?host=127.0.0.1",
            URL + "?port=5432",
            URL + "?hostaddr=192.0.2.1",
            URL + "?service=unsafe",
            URL + "?dbname=discmon",
            URL + "?options=-c%20role=other",
            URL + "?user=other",
            URL + "?HOST=192.0.2.1",
            URL + "?host=/var/run/postgresql&host=/tmp/other",
            "postgresql+psycopg://dummy:dummy-secret@/discmon_test?host=/tmp/unapproved",
            "postgresql+psycopg://dummy:dummy-secret@/discmon_test?host=/tmp/discmon-test-a/../other",
        )
    ]
    cases += [
        {**SAFE_ENV, "TEST_DATABASE_URL": url}
        for url in (
            URL.replace(":1/", ":2/"),
            URL.replace("discmon_test", "other_test"),
            URL.replace("dummy:", "other:"),
            URL.replace("dummy-secret", "different-secret"),
            URL.replace("127.0.0.1", "localhost"),
        )
    ]
    cases += [
        {**SAFE_ENV, key: "dummy"}
        for key in (
            "PGHOST",
            "PGPORT",
            "PGDATABASE",
            "PGSERVICE",
            "PGSERVICEFILE",
            "PGOPTIONS",
            "PGHOSTADDR",
            "PGUSER",
            "PGPASSWORD",
            "database_url",
            "app_env",
        )
    ]
    return cases


class DatabaseSafetyTests(unittest.TestCase):
    def test_invalid_configuration_is_rejected(self):
        for index, environ in enumerate(invalid_environments()):
            with self.subTest(case=index), self.assertRaises(pytest.UsageError) as failure:
                guard.validate_test_environment(environ)
            self.assertNotIn("dummy-secret", str(failure.exception))
            self.assertNotIn("postgresql+psycopg://", str(failure.exception))

    def test_ci_loopback_and_approved_socket_configuration(self):
        for url in (
            URL.replace("127.0.0.1:1", "localhost:55432"),
            URL.replace("127.0.0.1:1", "[::1]:55432"),
            "postgresql+psycopg://dummy@/discmon_test?host=/var/run/postgresql",
            "postgresql+psycopg://dummy@:55432/discmon_test?host=/tmp/discmon-test-safety",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    guard.validate_test_environment(environment(url)).database, "discmon_test"
                )

    def test_default_port_matches_explicit_port(self):
        environ = environment(URL.replace(":1/", "/"))
        environ["TEST_DATABASE_URL"] = URL.replace(":1/", ":5432/")
        self.assertEqual(guard.validate_test_environment(environ).port, 5432)

    def test_collection_rejects_before_engine_creation_and_redacts_credentials(self):
        script = (
            "import sqlalchemy.ext.asyncio as sa; "
            "sa.create_async_engine = lambda *a, **k: "
            "(_ for _ in ()).throw(RuntimeError('ENGINE_CREATION_REACHED')); "
            "import pytest; raise SystemExit(pytest.main(['--collect-only', '-q', "
            "'tests/test_database_safety.py']))"
        )
        base = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("PG") and key.upper() not in SAFE_ENV
        }
        for index, environ in enumerate(invalid_environments()):
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=API_ROOT,
                env={**base, **environ},
                capture_output=True,
                text=True,
                timeout=20,
            )
            output = result.stdout + result.stderr
            with self.subTest(case=index):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Test database safety:", output)
                self.assertNotIn("ENGINE_CREATION_REACHED", output)
                self.assertNotIn("dummy-secret", output)
                self.assertNotIn("postgresql+psycopg://", output)

    def test_cached_application_settings_rejected_before_engine_creation(self):
        script = (
            "from app.config import get_settings; "
            "get_settings().database_url = "
            "'postgresql+psycopg://dummy:dummy-secret@192.0.2.1/discmon'; "
            "import sqlalchemy.ext.asyncio as sa; "
            "sa.create_async_engine = lambda *a, **k: "
            "(_ for _ in ()).throw(RuntimeError('ENGINE_CREATION_REACHED')); "
            "import pytest; raise SystemExit(pytest.main(['--collect-only', '-q', "
            "'tests/test_database_safety.py']))"
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("PG") and key.upper() not in SAFE_ENV
        }
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=API_ROOT,
            env={**env, **SAFE_ENV},
            capture_output=True,
            text=True,
            timeout=20,
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Test database safety:", output)
        self.assertNotIn("ENGINE_CREATION_REACHED", output)
        self.assertNotIn("dummy-secret", output)
        self.assertNotIn("postgresql+psycopg://", output)

    def test_collection_accepts_ci_and_socket_without_connecting(self):
        for url in (
            URL.replace("127.0.0.1:1", "localhost:55432"),
            "postgresql+psycopg://dummy@/discmon_test?host=/tmp/discmon-test-safety",
        ):
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.upper().startswith("PG") and key.upper() not in SAFE_ENV
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "--collect-only",
                    "-q",
                    "tests/test_database_safety.py",
                ],
                cwd=API_ROOT,
                env={**env, **environment(url)},
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_connected_identity_and_endpoint(self):
        target = guard.validate_test_environment(SAFE_ENV)
        identity = {"database": "discmon_test", "username": "dummy", "session_username": "dummy"}
        info = {
            "dbname": "discmon_test",
            "user": "dummy",
            "host": "127.0.0.1",
            "hostaddr": "127.0.0.1",
            "port": 1,
        }
        guard.validate_connected_database(target, make_url(URL), identity, SimpleNamespace(**info))
        for key in identity:
            with self.subTest(key=key), self.assertRaises(pytest.UsageError):
                guard.validate_connected_database(
                    target, make_url(URL), {**identity, key: "unexpected"}, SimpleNamespace(**info)
                )
        for key, value in (
            ("dbname", "discmon"),
            ("user", "other"),
            ("host", "192.0.2.1"),
            ("hostaddr", "192.0.2.1"),
            ("hostaddr", ""),
            ("hostaddr", None),
            ("host", None),
            ("port", 5432),
        ):
            with self.subTest(key=key), self.assertRaises(pytest.UsageError):
                guard.validate_connected_database(
                    target, make_url(URL), identity, SimpleNamespace(**{**info, key: value})
                )
        with self.assertRaises(pytest.UsageError):
            guard.validate_connected_database(
                target, make_url(URL.replace(":1/", ":2/")), identity, SimpleNamespace(**info)
            )

    def test_resolved_localhost_endpoint(self):
        url = URL.replace("127.0.0.1", "localhost")
        target = guard.validate_test_environment(environment(url))
        identity = {"database": "discmon_test", "username": "dummy", "session_username": "dummy"}
        for address in ("127.0.0.1", "::1"):
            info = SimpleNamespace(
                dbname="discmon_test", user="dummy", host="localhost", hostaddr=address, port=1
            )
            guard.validate_connected_database(target, make_url(url), identity, info)
        info.hostaddr = "192.0.2.1"
        with self.assertRaises(pytest.UsageError):
            guard.validate_connected_database(target, make_url(url), identity, info)
        del info.hostaddr
        with self.assertRaises(pytest.UsageError):
            guard.validate_connected_database(target, make_url(url), identity, info)

    def test_connected_socket_identity(self):
        url = "postgresql+psycopg://dummy@/discmon_test?host=/tmp/discmon-test-safety"
        target = guard.validate_test_environment(environment(url))
        identity = {"database": "discmon_test", "username": "dummy", "session_username": "dummy"}
        info = SimpleNamespace(
            dbname="discmon_test",
            user="dummy",
            host="/tmp/discmon-test-safety",
            hostaddr="",
            port=5432,
        )
        guard.validate_connected_database(target, make_url(url), identity, info)
        info.host = "/tmp/other"
        with self.assertRaises(pytest.UsageError):
            guard.validate_connected_database(target, make_url(url), identity, info)

    def test_fixture_checks_same_connection_before_truncation(self):
        async def check(database: str) -> list[str]:
            statements = []
            connection = AsyncMock()
            result = MagicMock()
            result.mappings.return_value.one.return_value = {
                "database": database,
                "username": "dummy",
                "session_username": "dummy",
            }

            async def execute(statement):
                statements.append(str(statement))
                return result

            connection.execute.side_effect = execute
            raw = MagicMock()
            raw.driver_connection.info = SimpleNamespace(
                dbname=database, user="dummy", host="127.0.0.1", hostaddr="127.0.0.1", port=1
            )
            connection.get_raw_connection.return_value = raw
            engine = MagicMock(url=make_url(URL))
            engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
            engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)
            with (
                patch.object(guard, "engine", engine),
                patch.object(
                    guard, "_test_database_target", guard.validate_test_environment(SAFE_ENV)
                ),
            ):
                fixture = guard.clean_database.__wrapped__()
                if database == "discmon_test":
                    await anext(fixture)
                    await fixture.aclose()
                else:
                    with self.assertRaises(pytest.UsageError):
                        await anext(fixture)
            return statements

        rejected = asyncio.run(check("discmon"))
        self.assertEqual(len(rejected), 1)
        self.assertTrue(rejected[0].startswith("SELECT current_database()"))
        accepted = asyncio.run(check("discmon_test"))
        self.assertEqual(len(accepted), 2)
        self.assertTrue(accepted[1].startswith("TRUNCATE TABLE "))
        self.assertTrue(accepted[1].endswith(" RESTART IDENTITY CASCADE"))
