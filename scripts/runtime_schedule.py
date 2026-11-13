#!/usr/bin/env python3
"""Reconcile existing DiscMon containers; never create or remove resources."""

import fcntl
import json
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("web", "scheduler", "worker", "api", "postgres")
BACKUP = "discmon-backup.service"
LOCK_WAIT = 1500


class Unsafe(RuntimeError):
    pass


def operating_hours():
    return 9 <= datetime.now(ZoneInfo("Asia/Kolkata")).hour < 21


class Controller:
    def __init__(self, docker_config):
        self.env = {
            "PATH": "/usr/bin:/bin", "HOME": str(ROOT), "LANG": "C.UTF-8",
            "DOCKER_CONFIG": str(docker_config),
        }
        self.docker = ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
        self.compose = self.docker + [
            "compose", "--project-name", "discmon", "--project-directory", str(ROOT),
            "--env-file", str(ROOT / ".env"), "--file", str(ROOT / "docker-compose.yml"),
        ]

    def run(self, command, stage, timeout=30):
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

    def backup_busy(self):
        output = self.run([
            "/usr/bin/systemctl", "show", BACKUP,
            "--property=LoadState,ActiveState,Type,Result",
        ], "backup status")
        properties = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if properties.get("LoadState") != "loaded" or properties.get("Type") != "oneshot":
            raise Unsafe("backup service missing or not oneshot; refusing runtime operation")
        state = properties.get("ActiveState")
        if state == "failed" or properties.get("Result") != "success":
            raise Unsafe("backup failed; inspect its journal before resetting failure; stack left untouched")
        if state == "inactive":
            return False
        if state in {"active", "activating", "deactivating", "reloading"}:
            return True
        raise Unsafe("unknown backup state; refusing runtime operation")

    def containers(self):
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

    def stop(self, containers):
        print("Graceful stop: waiting without forced kill", flush=True)
        for service in SERVICES:
            self.run(self.docker + ["stop", "--timeout", "-1", containers[service]],
                     f"graceful stop {service}", timeout=None)
        print("DiscMon stopped; containers and volumes retained", flush=True)

    def reconcile(self):
        containers = self.containers()
        self.run(self.docker + ["update", "--restart=no", *containers.values()], "disable automatic restart")
        if not operating_hours():
            self.stop(containers)
            return
        print("Within 09:00–21:00 Asia/Kolkata: start existing DiscMon containers", flush=True)
        try:
            self.run(self.compose + ["start", "--wait", "--wait-timeout", "180", *SERVICES],
                     "startup", timeout=210)
        except Unsafe:
            # A partial start must not leave a silently running subset overnight.
            self.stop(containers)
            raise
        if not operating_hours():
            self.stop(containers)
        else:
            print("DiscMon started; automatic restart disabled", flush=True)


def main():
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
            controller.reconcile()
        return 0
    except (Unsafe, OSError, ValueError) as error:
        # Never forward arbitrary Docker, systemctl or file contents to the journal.
        message = str(error) if isinstance(error, Unsafe) else "local runtime precondition failed"
        print(f"DiscMon schedule FAILED: {message}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
