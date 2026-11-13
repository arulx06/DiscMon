"""Offline schedule tests: mocked commands and real, isolated advisory locks."""

import contextlib
import fcntl
import importlib.util
import io
import json
import subprocess
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "runtime_schedule", Path(__file__).resolve().parents[1] / "runtime_schedule.py",
)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)
REPO = runtime.ROOT
SECRET = "synthetic-secret-not-for-journal"


def records(root=REPO):
    return [{
        "Id": f"{index:064x}",
        "Config": {"Labels": {
            "com.docker.compose.project": "discmon",
            "com.docker.compose.service": service,
            "com.docker.compose.project.working_dir": str(root),
            "com.docker.compose.project.config_files": str(root / "docker-compose.yml"),
            "com.docker.compose.oneoff": "False",
        }},
        "Mounts": [{"Destination": "/var/lib/postgresql", "Type": "volume", "Name": "discmon_pgdata"}],
    } for index, service in enumerate(runtime.SERVICES, 1)]


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.data = records()
        self.backup = "inactive"
        self.fail = None
        self.controller = runtime.Controller("/isolated/docker-config")

    def fake_run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[0] == "/usr/bin/systemctl":
            output = f"LoadState=loaded\nType=oneshot\nActiveState={self.backup}\n"
        elif "inspect" in command:
            output = json.dumps(self.data)
        elif "ps" in command:
            output = "\n".join(item["Id"] for item in self.data)
        else:
            output = ""
        code = 17 if self.fail and self.fail in command else 0
        return subprocess.CompletedProcess(command, code, stdout=output, stderr=SECRET)

    def reconcile(self, hours):
        with patch.object(runtime.subprocess, "run", side_effect=self.fake_run), \
                patch.object(runtime, "operating_hours", side_effect=hours):
            self.controller.reconcile()

    def test_0900_start_and_explicit_identity(self):
        self.reconcile([True, True])
        commands = [command for command, _ in self.calls]
        start = next(command for command in commands if "start" in command)
        self.assertIn("--project-name", start)
        self.assertEqual(start[start.index("--project-name") + 1], "discmon")
        self.assertEqual(start[start.index("--file") + 1], str(REPO / "docker-compose.yml"))
        self.assertIn("--wait", start)
        self.assertFalse(any("stop" in command for command in commands))
        self.assertLess(next(i for i, c in enumerate(commands) if "update" in c), commands.index(start))

    def test_2100_stop_retains_every_resource_and_never_forces_kill(self):
        self.reconcile([False])
        stops = [(c, k) for c, k in self.calls if "stop" in c]
        self.assertEqual(len(stops), 5)
        self.assertEqual([c[-1] for c, _ in stops], [item["Id"] for item in self.data])
        for command, options in stops:
            self.assertEqual(command[-3:-1], ["--timeout", "-1"])
            self.assertIsNone(options["timeout"])
        for command, _ in self.calls:
            self.assertFalse(set(command) & {"down", "rm", "prune", "kill", "volume", "up", "exec", "build"})

    def test_boot_and_missed_events_use_current_time(self):
        for hour, inside in [(2, False), (10, True), (22, False), (9, True), (21, False)]:
            with self.subTest(hour=hour):
                self.calls.clear()
                self.reconcile([inside, inside] if inside else [inside])
                self.assertEqual(any("start" in c for c, _ in self.calls), inside)
        # A missed stop followed by a morning resume must start, not replay stop.
        self.calls.clear()
        self.reconcile([True, True])
        self.assertFalse(any("stop" in c for c, _ in self.calls))

    def test_timezone_boundaries_independent_of_host_timezone(self):
        real_datetime = datetime
        for utc, expected in [("2026-11-13T03:29:59", False), ("2026-11-13T03:30:00", True),
                              ("2026-11-13T15:29:59", True), ("2026-11-13T15:30:00", False)]:
            with self.subTest(utc=utc), patch.object(runtime, "datetime") as clock:
                clock.now.side_effect = lambda zone, utc=utc: real_datetime.fromisoformat(utc).replace(
                    tzinfo=UTC).astimezone(zone)
                self.assertEqual(runtime.operating_hours(), expected)
                self.assertEqual(str(clock.now.call_args.args[0]), "Asia/Kolkata")

    def test_start_crossing_cutoff_stops_again(self):
        self.reconcile([True, False])
        self.assertEqual(sum("stop" in c for c, _ in self.calls), 5)

    def test_failed_start_stops_partial_stack_and_reports_redacted_error(self):
        self.fail = "start"
        with self.assertRaisesRegex(runtime.Unsafe, "startup: command failed, exit=17") as error:
            self.reconcile([True])
        self.assertNotIn(SECRET, str(error.exception))
        self.assertEqual(sum("stop" in c for c, _ in self.calls), 5)

    def test_failed_stop_does_not_stop_database_or_escalate(self):
        self.fail = "stop"
        with self.assertRaisesRegex(runtime.Unsafe, "graceful stop web"):
            self.reconcile([False])
        self.assertEqual(sum("stop" in c for c, _ in self.calls), 1)

    def test_docker_unavailable_leaves_stack_untouched(self):
        with patch.object(runtime.subprocess, "run", side_effect=FileNotFoundError(SECRET)), \
                self.assertRaises(runtime.Unsafe) as error:
            self.controller.reconcile()
        self.assertNotIn(SECRET, str(error.exception))

    def test_timeout_redacted(self):
        with patch.object(runtime.subprocess, "run", side_effect=subprocess.TimeoutExpired(SECRET, 30)), \
                self.assertRaises(runtime.Unsafe) as error:
            self.controller.reconcile()
        self.assertNotIn(SECRET, str(error.exception))

    def test_identity_ambiguity_never_changes_containers(self):
        mutations = [
            lambda d: d.pop(),
            lambda d: d.append(d[0]),
            lambda d: d[0]["Config"]["Labels"].update({"com.docker.compose.project": "discmon-smoke-isolated"}),
            lambda d: d[0]["Config"]["Labels"].update({"com.docker.compose.project.config_files": "/other.yml"}),
            lambda d: d[0]["Config"]["Labels"].update({"com.docker.compose.project.working_dir": "/other"}),
            lambda d: d[0]["Config"]["Labels"].update({"com.docker.compose.oneoff": "True"}),
            lambda d: d[0]["Config"]["Labels"].update({"com.docker.compose.service": "postgres"}),
            lambda d: d[-1]["Mounts"][0].update({"Name": "discmon_smoke_pgdata"}),
            lambda d: d[-1]["Mounts"][0].update({"Type": "bind"}),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.data = records()
                self.calls.clear()
                mutation(self.data)
                with self.assertRaises(runtime.Unsafe):
                    self.reconcile([False])
                self.assertFalse(any("update" in c or "start" in c or "stop" in c for c, _ in self.calls))

    def test_subprocess_environment_excludes_credentials_and_smoke_overrides(self):
        with patch.dict("os.environ", {"COMPOSE_PROJECT_NAME": "discmon-smoke-isolated", "SECRET": SECRET}):
            self.reconcile([True, True])
        for command, options in self.calls:
            self.assertNotIn(SECRET, str(options))
            self.assertNotIn("COMPOSE_PROJECT_NAME", options["env"])
            self.assertEqual(command[1:3], ["--host", "unix:///var/run/docker.sock"])
            self.assertTrue(options["capture_output"])

    def test_backup_states_fail_closed(self):
        for state in ["active", "activating", "deactivating", "inactive"]:
            self.backup = state
            with patch.object(runtime.subprocess, "run", side_effect=self.fake_run):
                self.assertEqual(self.controller.backup_busy(), state != "inactive")
        with patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, "LoadState=not-found\n", SECRET)), self.assertRaises(runtime.Unsafe):
            self.controller.backup_busy()

    def test_failed_backup_blocks_shutdown_instead_of_hiding_failure(self):
        self.backup = "failed"
        with patch.object(runtime.subprocess, "run", side_effect=self.fake_run), self.assertRaisesRegex(
                runtime.Unsafe, "backup failed"):
            self.controller.backup_busy()
        self.assertFalse(any("stop" in c for c, _ in self.calls))

    def test_late_backup_after_shutdown_fails_without_partial_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts/backup.sh").write_text((REPO / "scripts/backup.sh").read_text())
            docker = root / "fake-docker"
            docker.write_text("#!/bin/bash\nexit 9\n")
            docker.chmod(0o700)
            result = subprocess.run(["/bin/bash", str(root / "scripts/backup.sh")],
                                    env={"PATH": "/usr/bin:/bin", "DOCKER_BIN": str(docker)},
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 9)
            self.assertEqual(list((root / "backups").iterdir()), [])

    def run_main(self, directory, busy, reconcile, **patches):
        with patch.object(runtime, "ROOT", Path(directory)), \
                patch.object(runtime.sys, "argv", ["runtime_schedule.py"]), \
                patch.object(runtime.signal, "signal"), \
                patch.object(runtime.Controller, "backup_busy", side_effect=busy), \
                patch.object(runtime.Controller, "reconcile", side_effect=reconcile), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(patch.object(runtime.time, name, side_effect=value))
            return runtime.main()

    def test_backup_still_running_waits_and_rechecks_before_shutdown(self):
        operations = []
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_main(directory, [True, True, False], lambda: operations.append("stop"), sleep=lambda _: None)
        self.assertEqual(result, 0)
        self.assertEqual(operations, ["stop"])

    def test_backup_never_finishes_no_runtime_operation(self):
        operations = []
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_main(directory, lambda: True, lambda: operations.append("stop"), monotonic=[0, 1501])
        self.assertEqual(result, 1)
        self.assertEqual(operations, [])

    def test_concurrent_invocation_cannot_enter_runtime_operation(self):
        operations = []
        with tempfile.TemporaryDirectory() as directory, (Path(directory) / ".runtime.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_main(directory, lambda: False, lambda: operations.append("start"), monotonic=[0, 1501])
        self.assertEqual(result, 1)
        self.assertEqual(operations, [])

    def test_main_failure_is_journal_ready_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime, "ROOT", Path(directory)), \
                patch.object(runtime.sys, "argv", ["runtime_schedule.py"]), \
                patch.object(runtime.signal, "signal"), \
                patch.object(runtime.Controller, "backup_busy", side_effect=OSError(SECRET)), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(runtime.main(), 1)
        self.assertIn("DiscMon schedule FAILED", stderr.getvalue())
        self.assertNotIn(SECRET, stderr.getvalue())

    def test_backup_script_holds_same_lock_until_dump_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts/backup.sh").write_text((REPO / "scripts/backup.sh").read_text())
            docker = root / "fake-docker"
            docker.write_text('#!/bin/bash\ntouch "${PWD}/dump-entered"\nwhile ! test -e "${PWD}/finish-dump"; do sleep 0.02; done\nprintf dump\n')
            docker.chmod(0o700)
            with (root / ".runtime.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                process = subprocess.Popen(["/bin/bash", str(root / "scripts/backup.sh")],
                                           env={"PATH": "/usr/bin:/bin", "DOCKER_BIN": str(docker)},
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    time.sleep(0.1)
                    self.assertFalse((root / "dump-entered").exists())
                    fcntl.flock(lock, fcntl.LOCK_UN)
                    deadline = time.monotonic() + 5
                    while not (root / "dump-entered").exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue((root / "dump-entered").exists())
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    (root / "finish-dump").touch()
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertIn("Backup written:", stdout)
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    (root / "finish-dump").touch()
                    if process.poll() is None:
                        process.communicate(timeout=5)

    def test_timer_and_service_safety_settings(self):
        timer = (REPO / "deploy/systemd/discmon-runtime.timer").read_text()
        service = (REPO / "deploy/systemd/discmon-runtime.service").read_text()
        for setting in ["OnCalendar=*-*-* *:*:00 Asia/Kolkata", "Persistent=true", "OnBootSec=30s"]:
            self.assertIn(setting, timer)
        for setting in ["TimeoutStartSec=infinity", "TimeoutStopSec=infinity", "SendSIGKILL=no", "User=arulxamv"]:
            self.assertIn(setting, service)
        self.assertFalse(list((REPO / "deploy/systemd").glob("*backup*")))


if __name__ == "__main__":
    unittest.main()
