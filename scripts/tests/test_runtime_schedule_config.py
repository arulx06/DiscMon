"""Offline tests for the host schedule snapshot and sync boundary."""

import contextlib
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

SPEC = importlib.util.spec_from_file_location(
    "runtime_schedule", Path(__file__).resolve().parents[1] / "runtime_schedule.py",
)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)
ScheduleStore = runtime.ScheduleStore


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        self.read_size = size
        return self.body


class ScheduleConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "state"
        self.directory.mkdir(mode=0o700)
        self.store = runtime.ScheduleStore(self.directory)
        self.schedule = dict(runtime.DEFAULT_SCHEDULE)
        self.new_schedule = {**self.schedule, "revision": 2, "start_time": "10:00"}

    def tearDown(self):
        self.temporary.cleanup()

    def write_snapshot(self, schedule=None, synced_at=None, raw=None):
        if raw is None:
            raw = {
                **(schedule or self.schedule),
                "schema_version": 1,
                "synced_at": synced_at or datetime.now(UTC).isoformat(),
            }
            raw = json.dumps(raw).encode()
        path = self.directory / "schedule.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    def write_token(self, mode=0o600, content=b"a" * 40):
        path = self.directory / "sync.token"
        path.write_bytes(content)
        path.chmod(mode)
        return path

    def test_state_directory_requires_owned_private_directory(self):
        self.assertEqual(self.directory.lstat().st_uid, os.geteuid())
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.directory.chmod(0o755)
        with self.assertRaisesRegex(runtime.Unsafe, "mode 0700"):
            runtime.ScheduleStore(self.directory)

    def test_snapshot_is_atomic_private_and_round_trips_validated_schedule(self):
        with patch.object(runtime.os, "replace", wraps=os.replace) as replace:
            self.store.save(self.new_schedule)
        replace.assert_called_once()
        source, destination = map(Path, replace.call_args.args)
        self.assertEqual(destination, self.directory / "schedule.json")
        self.assertEqual(source.parent, self.directory)
        self.assertFalse(source.exists())
        info = destination.stat()
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertEqual(info.st_uid, os.geteuid())
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        self.assertEqual(self.store.load(), self.new_schedule)
        self.assertEqual(json.loads(destination.read_text())["schema_version"], 1)

    def test_schedule_times_are_strict_and_preserve_backup_window(self):
        for start, end in [
            ("08:00", "21:00"),
            ("20:00", "21:00"),
            ("09:00", "23:59"),
        ]:
            with self.subTest(start=start, end=end):
                self.assertEqual(runtime.validate_schedule({
                    **self.schedule, "start_time": start, "shutdown_time": end,
                })["start_time"], start)
        for start, end in [
            ("20:01", "21:00"),
            ("09:00", "20:59"),
            ("09:00", "09:00"),
            ("10:00", "09:00"),
            ("9:00", "21:00"),
            ("09:0", "21:00"),
            ("09:60", "21:00"),
            ("24:00", "25:00"),
            ("09:00:00", "21:00"),
        ]:
            with self.subTest(start=start, end=end), self.assertRaises(runtime.Unsafe):
                runtime.validate_schedule({
                    **self.schedule, "start_time": start, "shutdown_time": end,
                })

    def test_snapshot_schema_and_file_permissions_fail_closed(self):
        invalid_snapshots = [
            b"{",
            json.dumps({**self.schedule, "schema_version": 2,
                        "synced_at": datetime.now(UTC).isoformat()}).encode(),
            json.dumps({**self.schedule, "schema_version": True,
                        "synced_at": datetime.now(UTC).isoformat()}).encode(),
            json.dumps({**self.schedule, "schema_version": 1,
                        "synced_at": "not-a-timestamp"}).encode(),
            json.dumps({**self.schedule, "schema_version": 1,
                        "synced_at": datetime.now().replace(tzinfo=None).isoformat()}).encode(),
            json.dumps({**self.schedule, "schema_version": 1,
                        "synced_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat()}).encode(),
            json.dumps({**self.schedule, "start_time": "9:00", "schema_version": 1,
                        "synced_at": datetime.now(UTC).isoformat()}).encode(),
        ]
        for raw in invalid_snapshots:
            with self.subTest(raw=raw):
                self.write_snapshot(raw=raw)
                with self.assertRaises(runtime.Unsafe):
                    self.store.load()
        self.write_snapshot()
        (self.directory / "schedule.json").chmod(0o644)
        with self.assertRaisesRegex(runtime.Unsafe, "permissions invalid"):
            self.store.load()

    def test_missing_snapshot_refuses_main_before_container_reconciliation(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / ".runtime.lock").touch()
            calls = []
            with patch.object(runtime, "ROOT", root), \
                    patch.object(runtime.sys, "argv", ["runtime_schedule.py"]), \
                    patch.object(runtime.signal, "signal"), \
                    patch.object(runtime.Controller, "backup_busy", return_value=False), \
                    patch.object(runtime.Controller, "reconcile", side_effect=calls.append), \
                    patch.object(runtime, "ScheduleStore", side_effect=lambda: ScheduleStore(self.directory)), \
                    patch.object(ScheduleStore, "request", side_effect=runtime.Unsafe("offline")), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runtime.main(), 1)
            self.assertEqual(calls, [])

    def test_corrupt_snapshot_refuses_main_before_container_reconciliation(self):
        self.write_snapshot(raw=b"not json")
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / ".runtime.lock").touch()
            calls = []
            with patch.object(runtime, "ROOT", root), \
                    patch.object(runtime.sys, "argv", ["runtime_schedule.py"]), \
                    patch.object(runtime.signal, "signal"), \
                    patch.object(runtime.Controller, "backup_busy", return_value=False), \
                    patch.object(runtime.Controller, "reconcile", side_effect=calls.append), \
                    patch.object(runtime, "ScheduleStore", side_effect=lambda: ScheduleStore(self.directory)), \
                    patch.object(ScheduleStore, "request", side_effect=runtime.Unsafe("offline")), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runtime.main(), 1)
            self.assertEqual(calls, [])

    def test_sync_uses_fixed_local_authenticated_bounded_no_proxy_request(self):
        token = self.write_token()
        response = FakeResponse(json.dumps(self.new_schedule).encode())

        class Opener:
            def open(_, request, timeout):
                self.assertEqual(request.full_url, "http://127.0.0.1:8000/runtime-sync/schedule")
                self.assertEqual(request.get_header("Authorization"), "Bearer " + "a" * 40)
                self.assertEqual(request.get_header("Content-type"), "application/json")
                self.assertEqual(timeout, 5)
                self.assertEqual(response.body, json.dumps(self.new_schedule).encode())
                return response

        with patch.object(runtime, "build_opener") as build_opener:
            build_opener.return_value = Opener()
            result = self.store.request("schedule")
        self.assertEqual(result, self.new_schedule)
        self.assertEqual(response.read_size, 4097)
        handlers = build_opener.call_args.args
        self.assertTrue(any(isinstance(handler, runtime.ProxyHandler) and handler.proxies == {}
                            for handler in handlers))
        self.assertTrue(any(isinstance(handler, runtime.NoRedirect) for handler in handlers))
        proxy_handler = next(handler for handler in handlers
                             if isinstance(handler, runtime.ProxyHandler))
        self.assertEqual(proxy_handler.proxies, {})
        self.assertEqual(stat.S_IMODE(token.stat().st_mode), 0o600)
        with self.assertRaisesRegex(runtime.Unsafe, "redirect refused"):
            runtime.NoRedirect().redirect_request(
                Request("http://127.0.0.1:8000/runtime-sync/schedule"), None,
                302, "Found", {"Location": "http://elsewhere/"},
                "http://elsewhere/",
            )

    def test_sync_rejects_nonprivate_token_and_oversized_response(self):
        token = self.write_token(mode=0o644)
        with self.assertRaisesRegex(runtime.Unsafe, "permissions invalid"):
            self.store.request("schedule")
        token.chmod(0o600)
        response = FakeResponse(b" " * 4097)

        class Opener:
            def open(_, *_args, **_kwargs):
                return response

        with patch.object(runtime, "build_opener", return_value=Opener()), self.assertRaisesRegex(
                runtime.Unsafe, "response too large"):
            self.store.request("schedule")

    def test_snapshot_fallback_warns_when_stale(self):
        old = datetime.now(UTC) - timedelta(seconds=181)
        self.write_snapshot(synced_at=old.isoformat())
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(self.store.load(), self.schedule)
        self.assertIn("snapshot stale", stderr.getvalue())

    def test_conflicting_ack_keeps_installed_snapshot_and_pending_state(self):
        self.write_snapshot()

        def request(path, payload=None):
            if path == "schedule":
                return self.new_schedule
            self.assertEqual(path, "ack")
            self.assertEqual(payload, self.new_schedule)
            raise runtime.Unsafe("schedule sync HTTP 409; details suppressed")

        with patch.object(self.store, "request", side_effect=request), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(self.store.current(), self.new_schedule)
        self.assertIn("synchronization pending", stderr.getvalue())
        self.assertEqual(self.store.load(), self.new_schedule)

    def test_snapshot_install_failure_does_not_acknowledge_schedule(self):
        self.write_snapshot()
        with patch.object(self.store, "request", return_value=self.new_schedule) as request, \
                patch.object(runtime.os, "replace", side_effect=OSError("install failed")), \
                self.assertRaisesRegex(runtime.Unsafe, "runtime snapshot update failed"):
            self.store.synchronize()
        self.assertEqual([call.args[0] for call in request.call_args_list], ["schedule", "error"])
        self.assertEqual(request.call_args_list[1].args[1], {
            "revision": self.new_schedule["revision"], "error": "snapshot_write_failed",
        })
        self.assertEqual(self.store.load(), self.schedule)

    def test_offline_startup_then_post_start_sync_reconciles_new_saved_schedule(self):
        self.write_snapshot()
        requests = []

        def request(path, payload=None):
            requests.append(path)
            if path == "schedule" and requests.count("schedule") == 1:
                raise runtime.Unsafe("offline")
            if path == "schedule":
                return self.new_schedule
            return {}

        reconciled = []
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / ".runtime.lock").touch()
            with patch.object(runtime, "ROOT", root), \
                    patch.object(runtime.sys, "argv", ["runtime_schedule.py"]), \
                    patch.object(runtime.signal, "signal"), \
                    patch.object(runtime.Controller, "backup_busy", return_value=False), \
                    patch.object(runtime.Controller, "reconcile", side_effect=reconciled.append), \
                    patch.object(runtime, "ScheduleStore", side_effect=lambda: ScheduleStore(self.directory)), \
                    patch.object(ScheduleStore, "request", side_effect=request), \
                    patch.object(runtime, "operating_hours", return_value=True), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runtime.main(), 0)
        self.assertEqual(reconciled, [self.schedule, self.new_schedule])
        self.assertEqual(requests, ["schedule", "schedule", "ack"])
        self.assertEqual(self.store.load(), self.new_schedule)

    def test_custom_minute_boundaries_use_saved_window_on_boot_or_resume(self):
        schedule = {**self.schedule, "start_time": "10:15", "shutdown_time": "21:30"}
        for utc, inside in [("2026-11-13T04:44:59", False),
                            ("2026-11-13T04:45:00", True),
                            ("2026-11-13T15:59:59", True),
                            ("2026-11-13T16:00:00", False)]:
            with self.subTest(utc=utc), patch.object(runtime, "datetime") as clock:
                clock.now.side_effect = lambda zone, utc=utc: datetime.fromisoformat(utc).replace(
                    tzinfo=UTC).astimezone(zone)
                self.assertEqual(runtime.operating_hours(schedule), inside)

    def test_compose_exposes_no_host_runtime_control_interfaces(self):
        compose = (runtime.ROOT / "docker-compose.yml").read_text()
        for forbidden in ("docker.sock", "/var/lib/discmon-runtime", "/run/systemd"):
            self.assertNotIn(forbidden, compose)

    def test_failed_backup_with_running_control_process_is_unknown(self):
        output = (
            "LoadState=loaded\nType=oneshot\nActiveState=failed\nSubState=failed\n"
            "MainPID=0\nControlPID=42\nResult=exit-code\n"
        )
        with patch.object(runtime.Controller, "run", return_value=output), \
                self.assertRaisesRegex(runtime.Unsafe, "backup completion unknown"):
            runtime.Controller("/isolated/docker-config").backup_busy()


if __name__ == "__main__":
    unittest.main()
