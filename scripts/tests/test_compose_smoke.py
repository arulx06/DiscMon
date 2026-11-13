"""Static-only tests for the isolated smoke Compose validator."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "compose_smoke.py"
REPO_ROOT = SCRIPT.parents[1]
sys.path.insert(0, str(SCRIPT.parent))
try:
    SPEC = importlib.util.spec_from_file_location("compose_smoke", SCRIPT)
    smoke = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(smoke)
finally:
    sys.path.remove(str(SCRIPT.parent))

Unsafe = smoke.Unsafe
PROJECT = "discmon-smoke-20261113-a17c"
SENTINEL = "synthetic-smoke-secret-sentinel"
DEFAULT_PORTS = smoke.DEFAULT_PORTS.copy()
COMPOSE_CAPABILITIES = "--no-env-resolution --format"
CHILD_ENV_KEYS = {
    "PATH", "HOME", "DOCKER_CONFIG", "LANG", "DISCMON_SMOKE_PROJECT",
    "DISCMON_SMOKE_DB_PORT", "DISCMON_SMOKE_API_PORT", "DISCMON_SMOKE_WEB_PORT",
}


def resolved_config(project=PROJECT, ports=None, root=None):
    ports = dict(DEFAULT_PORTS if ports is None else ports)
    root = Path(smoke.preflight.ROOT if root is None else root)
    environment = smoke.environments(ports)
    environment["api"]["DATABASE_URL"] = smoke.DB_URL
    services = {}
    for name in ("postgres", "api", "web"):
        service = {
            "restart": "no",
            "networks": {"default": None},
            "environment": environment[name],
            "ports": [{
                "host_ip": "127.0.0.1",
                "published": str(ports[name]),
                "target": smoke.TARGET_PORTS[name],
                "protocol": "tcp",
            }],
        }
        if name == "postgres":
            service.update({
                "image": "postgres:18-alpine",
                "volumes": [{
                    "type": "volume",
                    "source": "pgdata",
                    "target": "/var/lib/postgresql",
                }],
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U discmon_smoke_user -d discmon_smoke_test"],
                    "interval": "5s",
                    "timeout": "5s",
                    "retries": 20,
                },
            })
        else:
            path = "services/api" if name == "api" else "apps/web"
            dependency = "postgres" if name == "api" else "api"
            service["build"] = {"context": str(root / path), "dockerfile": "Dockerfile"}
            service["depends_on"] = {
                dependency: {"condition": "service_healthy", "required": True},
            }
            if name == "api":
                service["command"] = [
                    "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000",
                ]
                service["healthcheck"] = {
                    "test": [
                        "CMD", "python", "-c",
                        "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=3)",
                    ],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 12,
                }
        services[name] = service
    return {
        "name": project,
        "services": services,
        "volumes": {"pgdata": {"name": f"{project}_pgdata"}},
        "networks": {
            "default": {
                "name": f"{project}_default",
                "internal": True,
            },
        },
    }


@contextlib.contextmanager
def copied_compose_project():
    with tempfile.TemporaryDirectory(prefix="discmon-smoke-test-") as directory:
        root = Path(directory)
        for name in smoke.FILES:
            shutil.copyfile(REPO_ROOT / name, root / name)
        for name in ("services/api", "apps/web", "secrets"):
            (root / name).mkdir(parents=True, exist_ok=True)
        (root / "services/api/Dockerfile").write_text("FROM scratch\n")
        (root / "apps/web/Dockerfile").write_text("FROM scratch\n")
        (root / "source_registry_seed.yaml").write_text("sources: []\n")
        yield root


class ComposeSmokeTests(unittest.TestCase):
    def setUp(self):
        self.config = resolved_config()

    def assert_config_rejected(self, config, ports=None, message=None):
        with self.assertRaises(Unsafe) as caught:
            smoke.inspect_config(config, PROJECT, DEFAULT_PORTS if ports is None else ports)
        if message:
            self.assertIn(message, str(caught.exception))
        self.assertNotIn(SENTINEL, str(caught.exception))

    def run_mocked(self, config=None, *, version="2.40.3", capabilities=COMPOSE_CAPABILITIES,
                   config_output=None, parent_env=None, args=None):
        calls = []

        def fake_call(command, env):
            calls.append((list(command), dict(env)))
            if command[2] == "version":
                return version
            if "--help" in command:
                return capabilities
            if config_output is not None:
                return config_output
            return json.dumps(self.config if config is None else config)

        stdout = io.StringIO()
        stderr = io.StringIO()
        arguments = ["--project", PROJECT] + ([] if args is None else args)
        with patch.dict(os.environ, {} if parent_env is None else parent_env, clear=True), \
                patch.object(smoke.shutil, "which", return_value="/usr/bin/docker"), \
                patch.object(smoke.preflight, "call", side_effect=fake_call), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            smoke.main(arguments)
        return calls, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def compose_operation(command):
        if command[2] == "version":
            return "version"
        if "config" in command[2:]:
            return "config"
        return command[2]

    def assert_only_static_compose_calls(self, calls):
        self.assertEqual(
            [self.compose_operation(command) for command, _ in calls],
            ["version", "config", "config"],
        )
        for command, env in calls:
            self.assertEqual(command[1], "compose")
            self.assertNotIn(
                self.compose_operation(command),
                {"info", "ps", "up", "run", "exec", "build", "pull", "start"},
            )
            self.assertEqual(set(env), CHILD_ENV_KEYS)
            self.assertEqual(env["HOME"], env["DOCKER_CONFIG"])
            self.assertEqual(env["DISCMON_SMOKE_PROJECT"], PROJECT)
        config_command = calls[2][0]
        self.assertEqual(config_command[config_command.index("--env-file") + 1], "/dev/null")
        self.assertIn("--no-env-resolution", config_command)
        self.assertEqual(config_command[config_command.index("--format") + 1], "json")
        self.assertEqual(config_command[config_command.index("--profile") + 1], "*")

    def test_valid_resolved_model_is_isolated_and_canonical(self):
        smoke.inspect_config(self.config, PROJECT, DEFAULT_PORTS)
        self.assertEqual(self.config["volumes"], {"pgdata": {"name": f"{PROJECT}_pgdata"}})
        self.assertTrue(self.config["networks"]["default"]["internal"])
        self.assertEqual(set(self.config["services"]), {"postgres", "api", "web"})
        self.assertTrue(
            self.config["services"]["api"]["environment"]["DATABASE_URL"] == smoke.DB_URL,
        )
        self.assert_database_environment_consistent(self.config)

    def assert_database_environment_consistent(self, config):
        postgres_environment = config["services"]["postgres"]["environment"]
        api_url = config["services"]["api"]["environment"]["DATABASE_URL"]
        parsed_url = urlsplit(api_url)
        self.assertTrue(api_url == smoke.DB_URL)
        self.assertTrue(parsed_url.username == postgres_environment["POSTGRES_USER"])
        self.assertTrue(parsed_url.password == postgres_environment["POSTGRES_PASSWORD"])
        self.assertTrue(parsed_url.hostname == "postgres")
        self.assertTrue(parsed_url.port == 5432)
        self.assertTrue(parsed_url.path.lstrip("/") == postgres_environment["POSTGRES_DB"])

    def test_protected_project_names_and_unsafe_ports_are_refused(self):
        invalid_names = (
            "discmon",
            "discmon-dev",
            "discmon-smoke-short",
            "discmon-smoke-production-20261113",
            "discmon-smoke-default-20261113",
            "discmon-smoke-live-20261113",
            "discmon-smoke-INVALID-20261113",
            "discmon-smoke-20261113_aaaa",
        )
        for project in invalid_names:
            with self.subTest(project=project), self.assertRaises(Unsafe):
                smoke.validate_project(project)
        invalid_ports = (
            {**DEFAULT_PORTS, "postgres": 55432},
            {**DEFAULT_PORTS, "api": 8000},
            {**DEFAULT_PORTS, "web": 3000},
            {"postgres": 38001, "api": 38001, "web": 33001},
            {**DEFAULT_PORTS, "web": 80},
        )
        for ports in invalid_ports:
            with self.subTest(ports=ports), self.assertRaises(Unsafe):
                smoke.validate_ports(ports)

    def test_reused_external_and_custom_volumes_or_networks_are_refused(self):
        mutations = (
            ("external volume", lambda c: c["volumes"]["pgdata"].update({"external": True})),
            ("reused volume", lambda c: c["volumes"]["pgdata"].update({"name": "production_pgdata"})),
            ("custom volume", lambda c: c["volumes"].update({"shared": {"name": "shared"}})),
            ("external network", lambda c: c["networks"]["default"].update({"external": True})),
            ("custom network", lambda c: c["networks"]["default"].update({"driver": "overlay"})),
            ("reused network", lambda c: c["networks"]["default"].update({"name": "production"})),
            ("extra network", lambda c: c["networks"].update({"outside": {"name": "outside"}})),
            ("non-internal network", lambda c: c["networks"]["default"].update({"internal": False})),
        )
        for label, mutate in mutations:
            config = copy.deepcopy(self.config)
            mutate(config)
            with self.subTest(resource=label):
                self.assert_config_rejected(config)

    def test_secret_bind_and_extra_mounts_are_refused(self):
        mutations = (
            lambda c: c["services"]["postgres"].update({"volumes": [{
                "type": "bind", "source": "/secrets", "target": "/var/lib/postgresql",
            }]}),
            lambda c: c["services"]["postgres"]["volumes"].append({
                "type": "volume", "source": "other", "target": "/backup",
            }),
            lambda c: c["services"]["api"].update({"volumes": [{
                "type": "bind", "source": "/secrets", "target": "/secrets",
            }]}),
            lambda c: c["services"]["api"].update({"secrets": ["owner-token"]}),
            lambda c: c.update({"secrets": {"owner-token": {"file": "/private/token"}}}),
        )
        for index, mutate in enumerate(mutations):
            config = copy.deepcopy(self.config)
            mutate(config)
            with self.subTest(mount=index):
                self.assert_config_rejected(config)

    def test_inherited_production_ports_and_public_binds_are_refused(self):
        production_ports = {"postgres": 55432, "api": 8000, "web": 3000}
        for service, host_port in production_ports.items():
            config = copy.deepcopy(self.config)
            config["services"][service]["ports"][0]["published"] = str(host_port)
            with self.subTest(service=service, port=host_port):
                self.assert_config_rejected(config)
        for host_ip in ("0.0.0.0", "::", "192.0.2.10"):
            config = copy.deepcopy(self.config)
            config["services"]["api"]["ports"][0]["host_ip"] = host_ip
            with self.subTest(host_ip=host_ip):
                self.assert_config_rejected(config, message="Unsafe, public or production host binding.")
        config = copy.deepcopy(self.config)
        config["services"]["api"]["ports"].append({
            "host_ip": "127.0.0.1", "published": "8000", "target": 8000, "protocol": "tcp",
        })
        self.assert_config_rejected(config, message="Unsafe inherited or missing published ports.")

    def test_enabled_worker_scheduler_changedetection_and_profiles_are_refused(self):
        for service in ("worker", "scheduler", "changedetection"):
            config = copy.deepcopy(self.config)
            config["services"][service] = {}
            with self.subTest(service=service):
                self.assert_config_rejected(config)
        for profile in ("changedetection", "production", "default"):
            config = copy.deepcopy(self.config)
            config["services"]["api"]["profiles"] = [profile]
            with self.subTest(profile=profile):
                self.assert_config_rejected(config)

    def test_remote_canonical_and_mismatched_database_urls(self):
        self.assert_database_environment_consistent(self.config)
        bad_urls = (
            "postgresql+psycopg://discmon_smoke_user:********@remote.example:5432/discmon_smoke_test",
            "postgresql+psycopg://discmon_smoke_user:********@localhost:5432/discmon_smoke_test",
            "postgresql+psycopg://discmon_smoke_user:********@postgres:5432/discmon",
            "postgresql+psycopg://other_user:********@postgres:5432/discmon_smoke_test",
            "postgresql+psycopg://discmon_smoke_user:synthetic-password@postgres:5432/discmon_smoke_test",
            "postgresql://discmon_smoke_user:********@postgres:5432/discmon_smoke_test",
        )
        for index, url in enumerate(bad_urls):
            config = copy.deepcopy(self.config)
            config["services"]["api"]["environment"]["DATABASE_URL"] = url
            with self.subTest(database_url_case=index):
                self.assert_config_rejected(config)

    def test_inherited_compose_and_docker_routing_environment_is_refused(self):
        routing_variables = (
            "COMPOSE_FILE",
            "COMPOSE_PROJECT_NAME",
            "COMPOSE_ENV_FILES",
            "COMPOSE_PROFILES",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
        )
        for variable in routing_variables:
            with self.subTest(variable=variable):
                with patch.dict(os.environ, {variable: SENTINEL}, clear=True):
                    with patch.object(smoke.preflight, "call") as call:
                        with self.assertRaises(Unsafe) as caught:
                            smoke.main(["--project", PROJECT])
                self.assertNotIn(SENTINEL, str(caught.exception))
                call.assert_not_called()

    def test_unknown_and_duplicate_port_options_are_refused_before_compose(self):
        invalid_arguments = (
            ["--project", PROJECT, "--env-file", SENTINEL],
            ["--project", PROJECT, "--unknown-option", "value"],
            ["--project", PROJECT, "--db-port", "39001", "--db-port", "39002"],
        )
        for arguments in invalid_arguments:
            with self.subTest(option_case=len(arguments)):
                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(smoke.shutil, "which") as which:
                        with patch.object(smoke.preflight, "call") as call:
                            with self.assertRaises(Unsafe):
                                smoke.main(arguments[1:])
                which.assert_not_called()
                call.assert_not_called()

    def test_postgres_image_and_healthcheck_must_be_exact(self):
        mutations = (
            lambda c: c["services"]["postgres"].update({"image": "postgres:latest"}),
            lambda c: c["services"]["postgres"].pop("healthcheck"),
            lambda c: c["services"]["postgres"]["healthcheck"].update({"retries": 1}),
            lambda c: c["services"]["postgres"]["healthcheck"]["test"].__setitem__(
                1, "pg_isready -U production -d production",
            ),
        )
        for index, mutate in enumerate(mutations):
            config = copy.deepcopy(self.config)
            mutate(config)
            with self.subTest(change=index):
                self.assert_config_rejected(config)

    def test_sentinel_environment_and_credentials_are_not_echoed(self):
        config = copy.deepcopy(self.config)
        config["services"]["api"]["environment"]["DATABASE_URL"] = SENTINEL
        with self.assertRaises(Unsafe) as caught:
            smoke.inspect_config(config, PROJECT, DEFAULT_PORTS)
        self.assertNotIn(SENTINEL, str(caught.exception))
        calls, output, errors = self.run_mocked(
            config=self.config,
            parent_env={"OWNER_API_TOKEN": SENTINEL, "DATABASE_URL": SENTINEL},
        )
        self.assert_only_static_compose_calls(calls)
        self.assertNotIn(SENTINEL, output + errors + repr(calls))

    def test_malformed_json_and_resolved_config_are_suppressed(self):
        for value in (SENTINEL + " {", "null", "[]"):
            with self.subTest(value=value[:8]), patch.dict(os.environ, {}, clear=True):
                stdout = io.StringIO()
                stderr = io.StringIO()
                calls = []

                def fake_call(command, env):
                    calls.append(command)
                    if command[2] == "version":
                        return "2.40.3"
                    if "--help" in command:
                        return COMPOSE_CAPABILITIES
                    return value

                with patch.object(smoke.shutil, "which", return_value="/usr/bin/docker"), \
                        patch.object(smoke.preflight, "call", side_effect=fake_call), \
                        contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(Unsafe) as caught:
                        smoke.main(["--project", PROJECT])
                self.assertIn("Malformed resolved Compose configuration", str(caught.exception))
                self.assertNotIn(SENTINEL, str(caught.exception) + stdout.getvalue() + stderr.getvalue())
                self.assertEqual(len(calls), 3)

    def test_unsupported_compose_versions_and_capabilities_refuse_before_config(self):
        for version in ("1.29.2", "2.24.3", "3.0.0", "v2.24.3"):
            with self.subTest(version=version), self.assertRaises(Unsafe):
                self.run_mocked(version=version)
        for capabilities in ("--format", "--no-env-resolution", ""):
            calls = []

            def fake_call(command, env):
                calls.append(list(command))
                return "2.40.3" if command[2] == "version" else capabilities

            with self.subTest(capabilities=capabilities):
                with patch.dict(os.environ, {}, clear=True):
                    with patch.object(smoke.shutil, "which", return_value="/usr/bin/docker"):
                        with patch.object(smoke.preflight, "call", side_effect=fake_call):
                            with self.assertRaises(Unsafe):
                                smoke.main(["--project", PROJECT])
            self.assertEqual([self.compose_operation(command) for command in calls],
                             ["version", "config"])
            self.assertIn("--help", calls[-1])
        for version in ("2.24.4", "5.0.0"):
            with self.subTest(version=version):
                calls, _, _ = self.run_mocked(version=version)
                self.assert_only_static_compose_calls(calls)

    def test_missing_docker_cli_is_refused_without_invoking_compose(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(smoke.shutil, "which", return_value=None), \
                patch.object(smoke.preflight, "call") as call:
            with self.assertRaisesRegex(Unsafe, "Docker CLI unavailable"):
                smoke.main(["--project", PROJECT])
        call.assert_not_called()

    def test_invocation_uses_only_sanitized_static_compose_commands(self):
        calls, output, errors = self.run_mocked(
            parent_env={"OWNER_API_TOKEN": SENTINEL, "DATABASE_URL": SENTINEL},
        )
        self.assert_only_static_compose_calls(calls)
        self.assertIn("SMOKE CONFIG PASS", output)
        self.assertNotIn(SENTINEL, output + errors + repr(calls))

    def test_compose_failure_diagnostics_are_suppressed(self):
        failed = subprocess.CompletedProcess(
            ["docker", "compose", "version"], 1, SENTINEL, SENTINEL,
        )
        with patch.dict(os.environ, {"OWNER_API_TOKEN": SENTINEL}, clear=True), \
                patch.object(smoke.shutil, "which", return_value="/usr/bin/docker"), \
                patch.object(smoke.preflight.subprocess, "run", return_value=failed) as run:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaises(Unsafe) as caught:
                    smoke.main(["--project", PROJECT])
        self.assertIn("diagnostics suppressed", str(caught.exception))
        self.assertNotIn(SENTINEL, str(caught.exception) + stdout.getvalue() + stderr.getvalue())
        run.assert_called_once()
        self.assertEqual(set(run.call_args.kwargs["env"]), CHILD_ENV_KEYS)

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI absent; real Compose config check not available")
    def test_real_compose_default_and_custom_ports_ignore_dotenv_and_private_inputs(self):
        with copied_compose_project() as root:
            (root / ".env").write_text("INVALID ENVIRONMENT SYNTAX !!! = \"ignored\"\n")
            private_home = root / "private-home"
            private_config = private_home / ".docker"
            private_config.mkdir(parents=True)
            (private_config / "config.json").write_text(json.dumps({
                "auths": {"https://registry.invalid": {"auth": SENTINEL}},
            }))
            parent_env = {
                "HOME": str(private_home),
                "DOCKER_CONFIG": str(private_config),
                "OWNER_API_TOKEN": SENTINEL,
                "DATABASE_URL": SENTINEL,
                "POSTGRES_PASSWORD": SENTINEL,
            }
            for custom_ports in (None, {"postgres": 56433, "api": 38001, "web": 33001}):
                ports = DEFAULT_PORTS if custom_ports is None else custom_ports
                commands = []
                environments = []
                rendered_configs = []
                original_call = smoke.preflight.call

                def observed_call(command, env):
                    commands.append(list(command))
                    environments.append(dict(env))
                    self.assertNotEqual(env["HOME"], str(private_home))
                    self.assertNotEqual(env["DOCKER_CONFIG"], str(private_config))
                    self.assertEqual(set(env), CHILD_ENV_KEYS)
                    output = original_call(command, env)
                    if "config" in command[2:] and "--format" in command:
                        rendered_configs.append(json.loads(output))
                    return output

                stdout = io.StringIO()
                stderr = io.StringIO()
                arguments = ["--project", PROJECT]
                if custom_ports:
                    arguments += [
                        "--db-port", str(custom_ports["postgres"]),
                        "--api-port", str(custom_ports["api"]),
                        "--web-port", str(custom_ports["web"]),
                    ]
                with patch.dict(os.environ, parent_env, clear=True), \
                        patch.object(smoke.preflight, "ROOT", root), \
                        patch.object(smoke.preflight, "call", side_effect=observed_call), \
                        contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    smoke.main(arguments)
                self.assertEqual(len(commands), 3)
                self.assertEqual(len(rendered_configs), 1)
                self.assert_database_environment_consistent(rendered_configs[0])
                self.assertEqual([self.compose_operation(command) for command in commands], ["version", "config", "config"])
                for command in commands:
                    self.assertEqual(command[1], "compose")
                    self.assertNotIn(command[2], {"info", "ps", "up", "run", "exec", "build", "pull"})
                self.assertEqual(commands[2][commands[2].index("--env-file") + 1], "/dev/null")
                self.assertIn("--no-env-resolution", commands[2])
                self.assertEqual(environments[-1]["DISCMON_SMOKE_DB_PORT"], str(ports["postgres"]))
                self.assertEqual(environments[-1]["DISCMON_SMOKE_API_PORT"], str(ports["api"]))
                self.assertEqual(environments[-1]["DISCMON_SMOKE_WEB_PORT"], str(ports["web"]))
                self.assertIn("SMOKE CONFIG PASS", stdout.getvalue())
                self.assertNotIn(SENTINEL, stdout.getvalue() + stderr.getvalue() + repr(environments))

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI absent; real Compose config check not available")
    def test_real_compose_rejects_inherited_ports_secret_mount_and_malformed_yaml(self):
        scenarios = (
            ("inherited ports", lambda root: self._remove_port_override_tags(root),
             "Unsafe inherited or missing published ports."),
            ("secret bind mount", lambda root: self._add_secret_bind(root),
             "Unexpected service capability, profile, mount or private input."),
            ("malformed YAML", lambda root: (root / "docker-compose.smoke.yml").write_text(
                "services: [" + SENTINEL + "\n",
            ), "CLI check failed"),
        )
        for label, mutate, expected in scenarios:
            with self.subTest(scenario=label), copied_compose_project() as root:
                mutate(root)
                stdout = io.StringIO()
                stderr = io.StringIO()
                calls = []
                original_call = smoke.preflight.call

                def observed_call(command, env):
                    calls.append(list(command))
                    self.assertEqual(set(env), CHILD_ENV_KEYS)
                    return original_call(command, env)

                with patch.dict(os.environ, {"OWNER_API_TOKEN": SENTINEL}, clear=True), \
                        patch.object(smoke.preflight, "ROOT", root), \
                        patch.object(smoke.preflight, "call", side_effect=observed_call), \
                        contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(Unsafe) as caught:
                        smoke.main(["--project", PROJECT])
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn(SENTINEL, str(caught.exception) + stdout.getvalue() + stderr.getvalue())
                self.assertEqual([self.compose_operation(command) for command in calls], ["version", "config", "config"])
                self.assertTrue(all(command[1] == "compose" for command in calls))
                self.assertFalse(any(self.compose_operation(command) in {"info", "ps", "up", "run", "exec"}
                                     for command in calls))

    @staticmethod
    def _remove_port_override_tags(root):
        path = root / "docker-compose.smoke.yml"
        source = path.read_text()
        updated = source.replace("ports: !override", "ports:")
        if updated == source:
            raise AssertionError("Smoke overlay port override tags were not found")
        path.write_text(updated)

    @staticmethod
    def _add_secret_bind(root):
        path = root / "docker-compose.smoke.yml"
        source = path.read_text()
        marker = "    volumes: !reset []"
        replacement = "    volumes: !override\n      - ./secrets:/secrets:ro"
        if source.count(marker) != 1:
            raise AssertionError("Smoke API volume reset was not found exactly once")
        path.write_text(source.replace(marker, replacement))


if __name__ == "__main__":
    unittest.main()
