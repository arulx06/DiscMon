#!/usr/bin/env python3
"""Render and validate the fixed smoke overlay, without contacting a Docker daemon."""

import json
import os
import re
import shutil
import sys
import tempfile
from urllib.parse import urlsplit

import compose_preflight as preflight

Unsafe = preflight.Unsafe
require = preflight.require
FILES = ("docker-compose.yml", "docker-compose.smoke.yml")
DEFAULT_PORTS = {"postgres": 56432, "api": 38000, "web": 33000}
TARGET_PORTS = {"postgres": 5432, "api": 8000, "web": 3000}
DB_URL = "postgresql+psycopg://discmon_smoke_user:smoke-only-not-a-secret@postgres:5432/discmon_smoke_test"


def validate_project(project):
    require(isinstance(project, str)
            and re.fullmatch(r"discmon-smoke-[a-z0-9][a-z0-9-]{7,39}", project) is not None
            and not any(word in project for word in ("prod", "default", "live")),
            "Require a fresh non-production discmon-smoke- identity (8-40 character suffix).")


def validate_ports(ports):
    require(set(ports) == set(DEFAULT_PORTS)
            and all(type(port) is int and 1024 <= port <= 65535
                    and port not in {3000, 8000, 55432, 5000} for port in ports.values())
            and len(set(ports.values())) == 3,
            "Require distinct non-production host ports between 1024 and 65535.")


def environments(ports):
    origin = f"http://127.0.0.1:{ports['web']}"
    return {
        "postgres": {"POSTGRES_USER": "discmon_smoke_user",
                     "POSTGRES_PASSWORD": "smoke-only-not-a-secret",
                     "POSTGRES_DB": "discmon_smoke_test"},
        "api": {"APP_ENV": "test", "APP_BASE_URL": origin, "DATABASE_URL": DB_URL,
                "OWNER_AUTH_MODE": "token", "OWNER_API_TOKEN": "smoke-only-owner-token",
                "SESSION_SECRET": "smoke-only-session-secret", "ALLOWED_ORIGINS": origin,
                "SHEETS_SYNC_ENABLED": "false", "AI_ENABLED": "false"},
        "web": {"INTERNAL_API_URL": "http://api:8000",
                "INTERNAL_API_TOKEN": "smoke-only-owner-token",
                "NEXT_PUBLIC_APP_NAME": "DiscMon Smoke Test"},
    }


def inspect_config(config, project, ports):
    validate_project(project)
    validate_ports(ports)
    require(config.get("name") == project, "Unexpected resolved smoke project identity.")
    require(set(config) <= {"name", "services", "volumes", "networks"},
            "Unexpected top-level configuration, secrets or inherited extensions.")
    volumes = config.get("volumes", {})
    require(volumes == {"pgdata": {"name": f"{project}_pgdata"}},
            "Unsafe volume: require only fresh project-scoped pgdata, without external/custom storage.")
    networks = config.get("networks", {})
    require(set(networks) == {"default"}, "Unexpected network layout.")
    network = networks["default"]
    require(set(network) <= {"name", "internal", "driver", "ipam"}
            and network.get("name") == f"{project}_default"
            and network.get("internal") is True
            and network.get("driver", "bridge") == "bridge" and not network.get("ipam"),
            "Unsafe network: require a project-scoped internal bridge without external/custom routing.")
    services = config.get("services", {})
    require(set(services) == set(DEFAULT_PORTS),
            "Only postgres, api and web may exist, even with all profiles enabled.")
    common = {"command", "entrypoint", "environment", "networks", "ports", "restart"}
    extras = {"postgres": {"image", "healthcheck", "volumes"},
              "api": {"build", "depends_on", "healthcheck"},
              "web": {"build", "depends_on"}}
    expected_env = environments(ports)
    for name, service in services.items():
        require(set(service) <= common | extras[name],
                "Unexpected service capability, profile, mount or private input.")
        require(service.get("restart") == "no" and not service.get("entrypoint"),
                "Unexpected restart policy or entrypoint.")
        require(service.get("networks") == {"default": None}, "Unexpected service network routing.")
        require(service.get("environment") == expected_env[name],
                "Unsafe environment or database/API routing; values suppressed.")
        bindings = service.get("ports", [])
        require(len(bindings) == 1, "Unsafe inherited or missing published ports.")
        port = bindings[0]
        require(set(port) <= {"mode", "host_ip", "target", "published", "protocol"}
                and port.get("host_ip") == "127.0.0.1"
                and str(port.get("published")) == str(ports[name])
                and port.get("target") == TARGET_PORTS[name]
                and port.get("protocol", "tcp") == "tcp"
                and port.get("mode", "ingress") == "ingress",
                "Unsafe, public or production host binding.")
        if name == "postgres":
            require(service.get("image") == "postgres:18-alpine" and not service.get("command"),
                    "Require the unmodified PostgreSQL 18 image startup.")
            mount = service.get("volumes", [])
            require(len(mount) == 1 and mount[0].get("type") == "volume"
                    and mount[0].get("source") == "pgdata"
                    and mount[0].get("target") == "/var/lib/postgresql"
                    and set(mount[0]) <= {"type", "source", "target", "volume"}
                    and not mount[0].get("volume"),
                    "Unsafe PostgreSQL mount; no host, backup, secret or reused storage accepted.")
            expected_health = {"test": ["CMD-SHELL", "pg_isready -U discmon_smoke_user -d discmon_smoke_test"],
                               "interval": "5s", "timeout": "5s", "retries": 20}
            require(service.get("healthcheck") == expected_health,
                    "Missing or incorrect isolated PostgreSQL healthcheck.")
        else:
            path = "services/api" if name == "api" else "apps/web"
            require(service.get("build") == {"context": str(preflight.ROOT / path), "dockerfile": "Dockerfile"},
                    "Unexpected build context or private build configuration.")
            dependency = "postgres" if name == "api" else "api"
            require(service.get("depends_on") == {
                dependency: {"condition": "service_healthy", "required": True}},
                "Unexpected dependency or automatic service startup.")
            if name == "api":
                require(service.get("command") == ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
                        and service.get("healthcheck") == {
                            "test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=3)"],
                            "interval": "10s", "timeout": "5s", "retries": 12},
                        "Unexpected API startup or liveness check.")
            else:
                require(not service.get("command"), "Unexpected web startup command.")
    database = services["postgres"]["environment"]
    route = urlsplit(services["api"]["environment"]["DATABASE_URL"])
    require(route.scheme == "postgresql+psycopg" and route.hostname == "postgres"
            and route.port == 5432 and not route.query and not route.fragment
            and route.username == database["POSTGRES_USER"]
            and route.password == database["POSTGRES_PASSWORD"]
            and route.path == "/" + database["POSTGRES_DB"],
            "Database routing or test credential consistency failed; values suppressed.")


def main(args):
    usage = "Usage: python3 scripts/compose_smoke.py --project discmon-smoke-<unique-suffix> [--db-port N] [--api-port N] [--web-port N]"
    require(len(args) >= 2 and len(args) % 2 == 0 and args[0] == "--project", usage)
    project = args[1]
    validate_project(project)
    ports = DEFAULT_PORTS.copy()
    options = {"--db-port": "postgres", "--api-port": "api", "--web-port": "web"}
    seen = set()
    for key, value in zip(args[2::2], args[3::2]):
        require(key in options and key not in seen and re.fullmatch(r"[0-9]{4,5}", value), usage)
        seen.add(key)
        ports[options[key]] = int(value)
    validate_ports(ports)
    require(not any(os.environ.get(key) for key in
                    ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES",
                     "COMPOSE_PROFILES", "DOCKER_HOST", "DOCKER_CONTEXT")),
            "Unexpected inherited Compose/Docker routing input; unset it before static inspection.")
    docker = shutil.which("docker")
    require(docker is not None, "Docker CLI unavailable; actual Compose validation not performed.")
    with tempfile.TemporaryDirectory(prefix="discmon-smoke-") as home:
        env = {"PATH": os.defpath, "HOME": home, "DOCKER_CONFIG": home, "LANG": "C.UTF-8",
               "DISCMON_SMOKE_PROJECT": project,
               "DISCMON_SMOKE_DB_PORT": str(ports["postgres"]),
               "DISCMON_SMOKE_API_PORT": str(ports["api"]),
               "DISCMON_SMOKE_WEB_PORT": str(ports["web"])}
        version = preflight.call([docker, "compose", "version", "--short"], env).strip()
        match = re.fullmatch(r"v?([25])\.(\d+)\.(\d+)(?:[-+][a-zA-Z0-9.~-]+)?", version)
        require(match is not None and (int(match[1]) == 5 or
                (int(match[2]), int(match[3])) >= (24, 4)),
                "Require Compose v2 >= 2.24.4 or v5 with !override/!reset support.")
        help_text = preflight.call([docker, "compose", "config", "--help"], env)
        require(all(flag in help_text for flag in ("--no-env-resolution", "--format")),
                "Compose lacks required static config capabilities.")
        command = [docker, "compose", "--env-file", "/dev/null", "--project-directory",
                   str(preflight.ROOT), "--project-name", project]
        for file in FILES:
            command += ["--file", str(preflight.ROOT / file)]
        command += ["--profile", "*", "config", "--no-env-resolution", "--format", "json"]
        try:
            config = json.loads(preflight.call(command, env))
            inspect_config(config, project, ports)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise Unsafe("Malformed resolved Compose configuration; contents suppressed.") from None
    print(f"SMOKE CONFIG PASS: {project}; base + smoke override; all profiles inspected.")
    for name in ("postgres", "api", "web"):
        print(f"  {name}: 127.0.0.1:{ports[name]}->{TARGET_PORTS[name]}/tcp; restart=no")
    print(f"  volume: {project}_pgdata -> /var/lib/postgresql; no host/secret mounts")
    print(f"  network: {project}_default (internal bridge); no external resources")
    print("  DB: postgres:5432/discmon_smoke_test; web API: http://api:8000; credentials hidden")
    print("  worker/scheduler/changedetection absent; external integrations disabled")
    print("STATIC ONLY: no daemon queries or runtime actions; freshness/ports/health NOT established.")
    print("M0 remains PARTIAL; the runtime drill requires separate explicit owner authorization.")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Unsafe as error:
        print(f"SMOKE REFUSED: {error}", file=sys.stderr)
        sys.exit(1)
