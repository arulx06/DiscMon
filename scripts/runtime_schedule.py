#!/usr/bin/env python3
"""Reconcile existing DiscMon containers; never create or remove resources."""

import fcntl
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("web", "scheduler", "worker", "api", "postgres")
BACKUP = "discmon-backup.service"
LOCK_WAIT = 1500
STATE = Path("/var/lib/discmon-runtime")
DEFAULT_SCHEDULE = {"revision": 1, "start_time": "09:00", "shutdown_time": "21:00",
                    "timezone": "Asia/Kolkata"}


class Unsafe(RuntimeError):
    pass


def validate_schedule(value: object) -> dict:
    if not isinstance(value, dict):
        raise Unsafe("invalid schedule format")
    schedule = {key: value.get(key) for key in DEFAULT_SCHEDULE}
    if (type(schedule["revision"]) is not int or schedule["revision"] < 1
            or schedule["timezone"] != "Asia/Kolkata"):
        raise Unsafe("invalid schedule version or timezone")
    for key in ("start_time", "shutdown_time"):
        if not isinstance(schedule[key], str) or not re.fullmatch(
                r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", schedule[key]):
            raise Unsafe("invalid schedule time")
    start, end = schedule["start_time"], schedule["shutdown_time"]
    if start >= end or start > "20:00" or end < "21:00":
        raise Unsafe("schedule incompatible with protected 20:30 backup")
    return schedule


def operating_hours(schedule: dict | None = None) -> bool:
    schedule = schedule or DEFAULT_SCHEDULE
    current = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%H:%M")
    return schedule["start_time"] <= current < schedule["shutdown_time"]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Unsafe("schedule sync redirect refused")


class ScheduleStore:
    def __init__(self, directory: Path = STATE) -> None:
        self.directory = directory
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise Unsafe("runtime state directory must be owned by controller user with mode 0700")

    def read_private(self, name: str) -> bytes:
        try:
            fd = os.open(self.directory / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}
                        or info.st_nlink != 1):
                    raise Unsafe("runtime file ownership or permissions invalid")
                data = stream.read(4097)
                if len(data) > 4096:
                    raise Unsafe("runtime file too large")
                return data
        except OSError:
            raise Unsafe("runtime file missing or unreadable") from None

    def load(self) -> dict:
        try:
            value = json.loads(self.read_private("schedule.json"))
            if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
                raise ValueError
            synced = datetime.fromisoformat(value["synced_at"])
            if synced.tzinfo is None or synced > datetime.now(UTC):
                raise ValueError
            schedule = validate_schedule(value)
            if (datetime.now(UTC) - synced).total_seconds() > 180:
                print("Schedule snapshot stale: using last verified schedule; host sync unavailable",
                      file=sys.stderr, flush=True)
            return schedule
        except (ValueError, TypeError, KeyError, AttributeError):
            raise Unsafe("runtime snapshot corrupted; no container changes permitted") from None

    def save(self, schedule: dict) -> None:
        schedule = validate_schedule(schedule)
        payload = {**schedule, "schema_version": 1, "synced_at": datetime.now(UTC).isoformat()}
        fd, temporary = tempfile.mkstemp(prefix=".schedule-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / "schedule.json")
            directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def request(self, path: str, payload: dict | None = None) -> dict:
        try:
            token = self.read_private("sync.token").decode("ascii").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
                raise Unsafe("runtime sync token format invalid")
            request = Request(
                "http://127.0.0.1:8000/runtime-sync/" + path,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            opener = build_opener(ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=5) as response:
                raw = response.read(4097)
                if len(raw) > 4096:
                    raise Unsafe("schedule sync response too large")
                return json.loads(raw)
        except HTTPError as error:
            raise Unsafe(f"schedule sync HTTP {error.code}; details suppressed") from None
        except (OSError, ValueError):
            raise Unsafe("schedule sync unavailable or invalid; details suppressed") from None

    def report_error(self, schedule: dict, error: str) -> None:
        try:
            self.request("error", {"revision": schedule["revision"], "error": error})
        except Unsafe:
            print("Host error report unavailable; inspect runtime service journal",
                  file=sys.stderr, flush=True)

    def synchronize(self) -> dict:
        schedule = validate_schedule(self.request("schedule"))
        try:
            self.save(schedule)
        except OSError:
            self.report_error(schedule, "snapshot_write_failed")
            raise Unsafe("runtime snapshot update failed; details suppressed") from None
        # Confirm only after durable installation. Conflicts remain pending in PostgreSQL.
        self.request("ack", schedule)
        return schedule

    def current(self) -> dict:
        try:
            return self.synchronize()
        except Unsafe as error:
            print(f"Host schedule synchronization pending: {error}", file=sys.stderr, flush=True)
            return self.load()


class Controller:
    def __init__(self, docker_config: Path | str) -> None:
        self.env = {
            "PATH": "/usr/bin:/bin", "HOME": str(ROOT), "LANG": "C.UTF-8",
            "DOCKER_CONFIG": str(docker_config),
        }
        self.docker = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
        self.compose = self.docker + [
            "compose", "--project-name", "discmon", "--project-directory", str(ROOT),
            "--env-file", str(ROOT / ".env"), "--file", str(ROOT / "docker-compose.yml"),
        ]

    def run(self, command: list[str], stage: str, timeout: int | None = 30) -> str:
        try:
            result = subprocess.run(
                command, env=self.env, cwd=ROOT, capture_output=True, text=True,
                timeout=timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise Unsafe(f"{stage}: unavailable or timed out (CLI output suppressed)") from None
        if result.returncode:
            raise Unsafe(f"{stage}: command failed, exit={result.returncode} (CLI output suppressed)")
        return result.stdout

    def backup_busy(self) -> bool:
        output = self.run([
            "/usr/bin/systemctl", "show", BACKUP,
            "--property=LoadState,ActiveState,SubState,MainPID,Type,Result",
        ], "backup status")
        properties = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if properties.get("LoadState") != "loaded" or properties.get("Type") != "oneshot":
            raise Unsafe("backup service missing or not oneshot; refusing runtime operation")
        state = properties.get("ActiveState")
        if state in {"inactive", "failed"}:
            if (properties.get("MainPID") != "0"
                    or properties.get("SubState") not in {"dead", "failed"}
                    or not properties.get("Result")):
                raise Unsafe("backup completion unknown; refusing runtime operation")
            if properties.get("Result") != "success" or state == "failed":
                print("Completed backup failed; inspect backup journal (failure not reset)",
                      file=sys.stderr, flush=True)
            return False
        if state in {"active", "activating", "deactivating", "reloading"}:
            return True
        raise Unsafe("unknown backup state; refusing runtime operation")

    def containers(self) -> dict[str, str]:
        ids = self.run(self.docker + [
            "ps", "--all", "--filter", "label=com.docker.compose.project=discmon",
            "--no-trunc", "--format", "{{.ID}}",
        ], "container inventory").split()
        if len(ids) != len(SERVICES) or any(len(item) != 64 or any(c not in "0123456789abcdef" for c in item) for item in ids):
            raise Unsafe("expected exactly five existing discmon containers; refusing runtime operation")
        try:
            records = json.loads(self.run(self.docker + ["inspect", *ids], "container identity"))
            found = {}
            for record in records:
                labels = record["Config"]["Labels"]
                service = labels["com.docker.compose.service"]
                if (service not in SERVICES or service in found
                        or labels["com.docker.compose.project"] != "discmon"
                        or labels["com.docker.compose.project.working_dir"] != str(ROOT)
                        or labels["com.docker.compose.project.config_files"] != str(ROOT / "docker-compose.yml")
                        or labels.get("com.docker.compose.oneoff", "False").lower() != "false"
                        or record["Id"] not in ids):
                    raise Unsafe("container identity mismatch; refusing runtime operation")
                found[service] = record["Id"]
                if service == "postgres":
                    mounts = [m for m in record["Mounts"] if m["Destination"] == "/var/lib/postgresql"]
                    if (len(mounts) != 1 or mounts[0]["Type"] != "volume"
                            or mounts[0]["Name"] != "discmon_pgdata"):
                        raise Unsafe("PostgreSQL volume identity mismatch; refusing runtime operation")
            if set(found) != set(SERVICES):
                raise Unsafe("incomplete container inventory")
            return found
        except (KeyError, TypeError, ValueError):
            raise Unsafe("invalid container identity response (details suppressed)") from None

    def stop(self, containers: dict[str, str]) -> None:
        print("Graceful stop: waiting without forced kill", flush=True)
        for service in SERVICES:
            self.run(self.docker + ["stop", "--timeout", "-1", containers[service]],
                     f"graceful stop {service}", timeout=None)
        print("DiscMon stopped; containers and volumes retained", flush=True)

    def reconcile(self, schedule: dict | None = None) -> None:
        schedule = validate_schedule(schedule or DEFAULT_SCHEDULE)
        containers = self.containers()
        self.run(self.docker + ["update", "--restart=no", *containers.values()], "disable automatic restart")
        if not operating_hours(schedule):
            self.stop(containers)
            return
        if self.containers() != containers:
            raise Unsafe("container identities changed during reconciliation; refusing startup")
        if not operating_hours(schedule):
            self.stop(containers)
            return
        print(f"Within {schedule['start_time']}–{schedule['shutdown_time']} Asia/Kolkata: "
              "start existing DiscMon containers", flush=True)
        try:
            self.run(self.compose + ["start", "--wait", "--wait-timeout", "180", *SERVICES],
                     "startup", timeout=210)
        except Unsafe:
            # A partial start must not leave a silently running subset overnight.
            self.stop(containers)
            raise
        if not operating_hours(schedule):
            self.stop(containers)
        else:
            print("DiscMon started; automatic restart disabled", flush=True)


def main() -> int:
    if len(sys.argv) != 1:
        print("No arguments accepted; controller reconciles current Kolkata time only", file=sys.stderr)
        return 64
    try:
        # Keep the lock until a graceful Docker operation really finishes.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        with tempfile.TemporaryDirectory(prefix="discmon-runtime-") as config, \
                (ROOT / ".runtime.lock").open("a") as lock:
            controller = Controller(config)
            deadline = time.monotonic() + LOCK_WAIT
            announced = False
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    if not controller.backup_busy():
                        break
                    fcntl.flock(lock, fcntl.LOCK_UN)
                except BlockingIOError:
                    pass
                if not announced:
                    print("Waiting for backup/runtime lock; no containers changed", flush=True)
                    announced = True
                if time.monotonic() >= deadline:
                    raise Unsafe("backup/runtime busy after 25 minutes; stack left untouched")
                time.sleep(1)
            store = ScheduleStore()
            schedule = store.current()
            try:
                controller.reconcile(schedule)
                # PostgreSQL/API may have been offline before startup. Pull once more now.
                if operating_hours(schedule):
                    updated = store.current()
                    if updated != schedule:
                        schedule = updated
                        controller.reconcile(schedule)
            except (Unsafe, OSError):
                store.report_error(schedule, "controller_apply_failed")
                raise
        return 0
    except (Unsafe, OSError, ValueError) as error:
        # Never forward arbitrary Docker, systemctl or file contents to the journal.
        message = str(error) if isinstance(error, Unsafe) else "local runtime precondition failed"
        print(f"DiscMon schedule FAILED: {message}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
