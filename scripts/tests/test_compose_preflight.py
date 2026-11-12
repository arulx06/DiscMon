"""No pytest fixtures, database access, or runtime Compose operations."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "compose_preflight.py"
SPEC = importlib.util.spec_from_file_location("preflight", SCRIPT)
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
PROJECT = "discmon-preflight-20261112-a17c"
SENTINEL = "secret-sentinel-never-echo"


def fixture():
    services = {}
    for name in sorted(p.SERVICES):
        service = {"networks": {"default": None}, "environment": {}}
        if name in {"api", "worker", "scheduler"}:
            service["environment"]["DATABASE_URL"] = (
                f"postgresql+psycopg://discmon:{SENTINEL}@postgres:5432/discmon")
        ports = {"postgres": (55432, 5432), "api": (8000, 8000),
                 "web": (3000, 3000), "changedetection": (5000, 5000)}
        if name in ports:
            published, target = ports[name]
            service["ports"] = [{"host_ip": "127.0.0.1", "published": str(published),
                                 "target": target, "protocol": "tcp"}]
        if name == "postgres":
            service["image"] = "postgres:18-alpine"
            service["environment"]["POSTGRES_DB"] = "discmon"
            service["volumes"] = [{"type": "volume", "source": "pgdata"}]
        if name == "web":
            service["environment"]["INTERNAL_API_URL"] = "http://api:8000"
        if name == "changedetection":
            service["profiles"] = ["changedetection"]
        services[name] = service
    return {"name": PROJECT, "services": services,
            "volumes": {key: {"name": f"{PROJECT}_{key}"}
                        for key in ("pgdata", "changedetection")},
            "networks": {"default": {"name": f"{PROJECT}_default"}}}


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.config = fixture()
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.redirect.__exit__(None, None, None)
        self.assertNotIn(SENTINEL, self.output.getvalue())

    def invoke(self, host=False, responder=None):
        commands = []

        def run(command, **kwargs):
            commands.append(command)
            self.assertEqual(set(kwargs["env"]), {"PATH", "HOME", "DOCKER_CONFIG", "LANG"})
            if command[1:3] == ["compose", "version"]:
                output = "2.40.3"
            elif command[1:] == ["compose", "config", "--help"]:
                output = "--no-env-resolution --format"
            elif command[1] == "compose":
                self.assertIn("config", command)
                self.assertIn("--no-env-resolution", command)
                self.assertEqual(command[command.index("--env-file") + 1], "/dev/null")
                self.assertEqual(command[command.index("--project-name") + 1], PROJECT)
                output = json.dumps(self.config)
            else:
                self.assertIn(command[1], {"info", "ps", "volume", "network"})
                if command[1] in {"volume", "network"}:
                    self.assertEqual(command[2], "ls")
                output = ""
            if responder:
                return responder(command, output)
            return subprocess.CompletedProcess(command, 0, output, "")

        with patch.object(p.shutil, "which", return_value="/usr/bin/docker"), \
                patch.object(p.subprocess, "run", side_effect=run):
            p.main(["--project", PROJECT] + (["--check-host"] if host else []))
        return commands

    def test_static_success_only_capabilities_and_two_renders(self):
        os.environ["DATABASE_URL"] = SENTINEL
        os.environ["OWNER_API_TOKEN"] = SENTINEL
        commands = self.invoke()
        self.assertEqual(len(commands), 4)
        self.assertIn("STATIC ONLY", self.output.getvalue())
        self.assertIn("isolation NOT established", self.output.getvalue())
        self.assertIn("fixed ports", self.output.getvalue())

    def test_project_identities_and_unknown_secret_input(self):
        for args in ([], ["--project", ""], ["--project", "discmon"],
                     ["--project", "discmon-dev"], ["--project", "production"],
                     ["--project", "discmon-preflight-production"],
                     ["--project", "discmon-preflight-Xbad_bad"],
                     ["--project", "discmon-preflight-short"],
                     ["--project", PROJECT, "--env-file", SENTINEL]):
            with self.subTest(args=args), patch.object(p.subprocess, "run") as run:
                with self.assertRaises(p.Unsafe):
                    p.main(args)
                run.assert_not_called()

    def test_inherited_routing_rejected_without_echo(self):
        for key in ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES",
                    "COMPOSE_PROFILES", "DOCKER_HOST", "DOCKER_CONTEXT"):
            with self.subTest(key=key), patch.dict(os.environ, {key: SENTINEL}):
                with self.assertRaises(p.Unsafe) as error:
                    self.invoke()
                self.assertNotIn(SENTINEL, str(error.exception))

    def test_missing_docker(self):
        with patch.object(p.shutil, "which", return_value=None):
            with self.assertRaisesRegex(p.Unsafe, "Docker CLI unavailable"):
                p.main(["--project", PROJECT])

    def test_compose_unavailable_invalid_config_and_secret_diagnostics(self):
        for failed_stage in ("version", "config"):
            def responder(command, output):
                failed = failed_stage in command
                return subprocess.CompletedProcess(command, int(failed),
                                                   SENTINEL if failed else output, SENTINEL)
            with self.subTest(stage=failed_stage), self.assertRaises(p.Unsafe) as error:
                self.invoke(responder=responder)
            self.assertNotIn(SENTINEL, str(error.exception))

    def test_supported_compose_v5_uses_identical_safety_checks(self):
        def responder(command, output):
            if "version" in command:
                output = "v5.0.0"
            return subprocess.CompletedProcess(command, 0, output, "")
        self.invoke(responder=responder)
        self.assertIn("CONFIG PASS", self.output.getvalue())

    def test_unsupported_compose_version(self):
        def responder(command, output):
            return subprocess.CompletedProcess(command, 0, "1.29.2", "")
        with self.assertRaisesRegex(p.Unsafe, "Compose v2"):
            self.invoke(responder=responder)

    def test_invalid_json(self):
        def responder(command, output):
            return subprocess.CompletedProcess(command, 0,
                                               SENTINEL if "config" in command and "--help" not in command else output, "")
        with self.assertRaisesRegex(p.Unsafe, "Invalid resolved"):
            self.invoke(responder=responder)

    def test_unsafe_resource_definitions(self):
        mutations = [
            lambda c: c.update(name="discmon"),
            lambda c: c["volumes"]["pgdata"].update(name="discmon_pgdata"),
            lambda c: c["volumes"]["pgdata"].update(external=True),
            lambda c: c["volumes"]["pgdata"].update(driver_opts={"device": "/private"}),
            lambda c: c["networks"]["default"].update(name="discmon_default"),
            lambda c: c["services"]["api"].update(network_mode="host"),
            lambda c: c["services"]["api"].update(container_name="discmon-api"),
            lambda c: c["services"]["api"].update(env_file=["/private"]),
            lambda c: c.update(secrets={"private": {"file": "/private"}}),
            lambda c: c["services"]["postgres"]["volumes"][0].update(source="discmon_pgdata"),
            lambda c: c["services"]["api"].update(volumes=[{"type": "bind", "source": "/private"}]),
            lambda c: c["services"]["api"]["ports"][0].update(host_ip="0.0.0.0"),
            lambda c: c["services"]["api"]["ports"][0].update(published="3000"),
            lambda c: c["services"]["api"].update(profiles=["production"]),
            lambda c: c["services"].pop("worker"),
        ]
        for index, mutate in enumerate(mutations):
            config = copy.deepcopy(self.config)
            mutate(config)
            with self.subTest(case=index), self.assertRaises(p.Unsafe):
                p.inspect_config(config, PROJECT)

    def test_external_or_ambiguous_db_routing(self):
        for url in (f"postgresql+psycopg://u:{SENTINEL}@production:5432/discmon",
                    "postgresql+psycopg://discmon:x@postgres:5432/discmon?host=production",
                    "postgresql+psycopg://discmon:x@postgres:bad/discmon"):
            self.config["services"]["api"]["environment"]["DATABASE_URL"] = url
            with self.assertRaises(p.Unsafe):
                p.inspect_config(self.config, PROJECT)

    def test_host_success_read_only_inventory_and_bind_probes(self):
        with patch.object(p.socket, "socket") as sock:
            commands = self.invoke(host=True)
        self.assertEqual(len(commands), 12)
        self.assertEqual(sock.return_value.__enter__.return_value.bind.call_count, 4)
        self.assertIn("HOST CHECK PASS", self.output.getvalue())

    def test_existing_resources_by_name_and_label_rejected(self):
        for kind in ("ps", "volume", "network"):
            for labelled in (False, True):
                def responder(command, output):
                    if command[1] == kind and ("--filter" in command) == labelled:
                        output = "arbitrary-name" if labelled else PROJECT + "_pgdata"
                    return subprocess.CompletedProcess(command, 0, output, "")
                with self.subTest(kind=kind, labelled=labelled), self.assertRaises(p.Unsafe):
                    self.invoke(host=True, responder=responder)

    def test_docker_nat_published_ports_rejected_without_socket_listener(self):
        for mapping in ("127.0.0.1:8000->8000/tcp", "0.0.0.0:2999-3001->1-3/tcp",
                        "[::]:55432->5432/tcp", "unparseable->routing"):
            def responder(command, output):
                if command[-1] == "{{.Ports}}":
                    output = mapping
                return subprocess.CompletedProcess(command, 0, output, "")
            with self.subTest(mapping=mapping), patch.object(p.socket, "socket") as sock:
                with self.assertRaises(p.Unsafe):
                    self.invoke(host=True, responder=responder)
                sock.assert_not_called()

    def test_missing_required_compose_capability(self):
        def responder(command, output):
            if "--help" in command:
                output = "--format"
            return subprocess.CompletedProcess(command, 0, output, "")
        with self.assertRaisesRegex(p.Unsafe, "lacks required"):
            self.invoke(responder=responder)

    def test_daemon_unavailable(self):
        def responder(command, output):
            return subprocess.CompletedProcess(command, int(command[1] == "info"), output, SENTINEL)
        with self.assertRaisesRegex(p.Unsafe, "daemon unavailable"):
            self.invoke(host=True, responder=responder)

    def test_occupied_port(self):
        with patch.object(p.socket, "socket") as sock:
            sock.return_value.__enter__.return_value.bind.side_effect = OSError("occupied")
            with self.assertRaisesRegex(p.Unsafe, "occupied or unavailable"):
                self.invoke(host=True)

    def test_actual_occupied_local_port_probe(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            number = listener.getsockname()[1]
            with patch.object(p, "call", return_value=""):
                with self.assertRaisesRegex(p.Unsafe, str(number)):
                    p.check_host("docker", {}, PROJECT, {number})

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI not installed")
    def test_real_compose_in_fresh_copy_ignores_dotenv_and_shell_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("docker-compose.yml", "docker-compose.dev.yml"):
                shutil.copyfile(p.ROOT / name, root / name)
            (root / ".env").write_text('THIS IS NOT A VALID ENV FILE!!!="\n')
            with patch.object(p, "ROOT", root), patch.dict(os.environ, {"OWNER_API_TOKEN": SENTINEL}):
                p.main(["--project", PROJECT])
            self.assertIn("CONFIG PASS", self.output.getvalue())

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI not installed")
    def test_real_invalid_configuration_suppresses_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker-compose.yml").write_text(f"services: [{SENTINEL}\n")
            with patch.object(p, "ROOT", root):
                with self.assertRaises(p.Unsafe) as error:
                    p.main(["--project", PROJECT])
                self.assertNotIn(SENTINEL, str(error.exception))


if __name__ == "__main__":
    unittest.main()
