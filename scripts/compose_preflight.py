#!/usr/bin/env python3
"""Read-only Compose inspection; never a runtime acceptance or launch command."""

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {"postgres", "api", "web", "worker", "scheduler", "changedetection"}


class Unsafe(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Unsafe(message)


def call(command, env):
    try:
        result = subprocess.run(command, env=env, cwd=ROOT, capture_output=True,
                                text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Unsafe("Required CLI unavailable or timed out; no runtime action taken.") from None
    # Compose diagnostics can contain interpolated secrets. Never forward them.
    require(result.returncode == 0,
            "CLI check failed (system-installed Compose v2/v5 with config --no-env-resolution --format json required); "
            "diagnostics suppressed to protect secrets.")
    return result.stdout


def inspect_config(config, project):
    require(config.get("name") == project, "Unexpected resolved project identity.")
    require(not config.get("secrets") and not config.get("configs"),
            "External secret/config inputs are not accepted.")
    services = config.get("services", {})
    require(set(services) == SERVICES, "Unexpected or missing services.")
    volumes = config.get("volumes", {})
    networks = config.get("networks", {})
    require(set(volumes) == {"pgdata", "changedetection"}, "Unexpected persistent volumes.")
    require(set(networks) == {"default"}, "Unexpected networks.")
    for kind, resources in (("volume", volumes), ("network", networks)):
        for key, resource in resources.items():
            require(resource.get("name") == f"{project}_{key}"
                    and not resource.get("external")
                    and resource.get("driver", "local" if kind == "volume" else "bridge")
                    == ("local" if kind == "volume" else "bridge")
                    and not resource.get("driver_opts"),
                    f"Unsafe {kind}: external, unscoped or custom storage/routing.")
    ports = set()
    summaries = []
    for name, service in services.items():
        require(not any(service.get(key) for key in
                        ("container_name", "network_mode", "privileged", "external_links",
                         "volumes_from", "devices", "secrets", "configs", "env_file")),
                "Service uses ambiguous host or external resources.")
        require(set(service.get("networks", {})) == {"default"}, "Unexpected service routing.")
        profiles = service.get("profiles", [])
        require(profiles == (["changedetection"] if name == "changedetection" else []),
                "Unexpected service profiles.")
        service_ports = []
        for port in service.get("ports", []):
            require(port.get("host_ip") == "127.0.0.1"
                    and str(port.get("published", "")).isdigit()
                    and port.get("protocol", "tcp") == "tcp", "Unsafe or ambiguous host binding.")
            number = int(port["published"])
            require(1024 <= number <= 65535 and number not in ports,
                    "Invalid or overlapping fixed host ports.")
            ports.add(number)
            service_ports.append(f"127.0.0.1:{number}->{int(port['target'])}/tcp")
        binds = anonymous = 0
        for mount in service.get("volumes", []):
            kind = mount.get("type")
            if kind == "volume" and mount.get("source"):
                require(mount["source"] in volumes, "Unscoped persistent mount.")
            elif kind == "volume":
                anonymous += 1
            elif kind == "bind":
                # Inspect path metadata only: never open a bind source.
                allowed = {str(ROOT / path) for path in
                           ("source_registry_seed.yaml", "secrets", "services/api", "apps/web")}
                require(mount.get("source") in allowed, "Unexpected private/host bind source.")
                binds += 1
            else:
                raise Unsafe("Unsupported mount type.")
        environment = service.get("environment", {})
        if name in {"api", "worker", "scheduler"}:
            try:
                url = urlsplit(environment.get("DATABASE_URL", ""))
                valid = (url.scheme == "postgresql+psycopg" and url.hostname == "postgres"
                         and url.port == 5432 and url.path == "/discmon"
                         and url.username == "discmon" and not url.query and not url.fragment)
            except ValueError:
                valid = False
            require(valid, "Database routing is not the Compose-local postgres service.")
        if name == "postgres":
            require(service.get("image") == "postgres:18-alpine"
                    and environment.get("POSTGRES_DB") == "discmon",
                    "Unexpected PostgreSQL image/database.")
        if name == "web":
            require(environment.get("INTERNAL_API_URL") == "http://api:8000",
                    "Web API routing is not Compose-local.")
        summaries.append(f"  {name}: profiles={','.join(profiles) or 'none'}; "
                         f"ports={','.join(service_ports) or 'none'}; "
                         f"binds={binds}; anonymous-volumes={anonymous}")
    require(ports == {55432, 8000, 3000, 5000}, "Unexpected fixed port layout.")
    return ports, summaries


def check_host(docker, env, project, ports):
    try:
        call([docker, "info", "--format", "{{.ServerVersion}}"], env)
    except Unsafe:
        raise Unsafe("Local Docker daemon unavailable; host isolation NOT established.") from None
    # Docker NAT publishing need not own a host socket (userland proxy may be off).
    published = call([docker, "ps", "-a", "--format", "{{.Ports}}"], env)
    for mapping in published.replace("\n", ",").split(","):
        if "->" not in mapping:
            continue
        match = re.search(r":(\d+)(?:-(\d+))?->\d+(?:-\d+)?/(tcp|udp)$", mapping.strip())
        require(match is not None, "Ambiguous existing Docker published-port metadata.")
        start = int(match[1])
        end = int(match[2] or match[1])
        require(match[3] != "tcp" or not any(start <= port <= end for port in ports),
                "Existing Docker published TCP port conflicts with the fixed port layout.")
    # Names, project labels and published ports only; never environments or mounts.
    for resource, listing, template in (
        ("container", ["ps", "-a"], "{{.Names}}"),
        ("volume", ["volume", "ls"], "{{.Name}}"),
        ("network", ["network", "ls"], "{{.Name}}"),
    ):
        names = call([docker, *listing, "--format", template], env).splitlines()
        require(not any(name == project or name.startswith(project + "_")
                        or name.startswith(project + "-") for name in names),
                f"Existing {resource} name conflicts with the proposed project.")
        labelled = call([docker, *listing, "--filter",
                         f"label=com.docker.compose.project={project}", "--format", template], env)
        require(not labelled.strip(), f"Existing {resource} belongs to the proposed project.")
    for number in sorted(ports):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", number))
        except OSError:
            raise Unsafe(f"Fixed localhost port {number} is occupied or unavailable.") from None


def main(args):
    require(len(args) in (2, 3) and args[0] == "--project"
            and (len(args) == 2 or args[2] == "--check-host"),
            "Usage: python3 scripts/compose_preflight.py --project discmon-preflight-<unique-suffix> [--check-host]")
    project = args[1]
    require(re.fullmatch(r"discmon-preflight-[a-z0-9][a-z0-9-]{7,39}", project) is not None
            and not any(word in project for word in ("prod", "default", "live")),
            "Require a unique non-production discmon-preflight- identity (8-40 character suffix).")
    require(not any(os.environ.get(key) for key in
                    ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES",
                     "COMPOSE_PROFILES", "DOCKER_HOST", "DOCKER_CONTEXT")),
            "Unexpected inherited Compose/Docker routing input; unset it before inspection.")
    docker = shutil.which("docker")
    require(docker is not None, "Docker CLI unavailable; install Docker Compose v2/v5 for static rendering.")
    # Empty HOME/config and explicit env file prevent implicit private configuration.
    with tempfile.TemporaryDirectory(prefix="discmon-preflight-") as home:
        env = {"PATH": os.defpath, "HOME": home, "DOCKER_CONFIG": home,
               "LANG": "C.UTF-8"}
        version = call([docker, "compose", "version", "--short"], env).strip()
        require(re.fullmatch(r"v?[25]\.\d+\.\d+(?:[-+][a-zA-Z0-9.~-]+)?", version) is not None,
                "Docker Compose v2/v5 with config --format json required.")
        capabilities = call([docker, "compose", "config", "--help"], env)
        require(all(flag in capabilities for flag in ("--no-env-resolution", "--format")),
                "Compose lacks required config --no-env-resolution / --format capabilities.")
        print("Docker Compose v2/v5 available; inherited application settings ignored.")
        ports = set()
        for files in (("docker-compose.yml",), ("docker-compose.yml", "docker-compose.dev.yml")):
            command = [docker, "compose", "--env-file", "/dev/null", "--project-directory",
                       str(ROOT), "--project-name", project]
            for file in files:
                command += ["--file", str(ROOT / file)]
            command += ["--profile", "*", "config", "--no-env-resolution", "--format", "json"]
            try:
                config = json.loads(call(command, env))
                found_ports, summaries = inspect_config(config, project)
            except (ValueError, TypeError, KeyError, AttributeError):
                raise Unsafe("Invalid resolved Compose configuration; contents suppressed.") from None
            ports.update(found_ports)
            print("Configuration: " + " + ".join(files))
            print("\n".join(summaries))
            print(f"  scoped volumes: {project}_pgdata, {project}_changedetection")
            print(f"  scoped network: {project}_default; DB: postgres:5432/discmon (credentials hidden)")
        print("RISK: fixed ports are shared across projects, including optional profiles.")
        print("RISK: repository bind mounts include secrets; a future runtime drill must remove private binds.")
        if len(args) == 3:
            check_host(docker, env, project, ports)
            print("HOST CHECK PASS: no matching resources and ports available at this instant only.")
        else:
            print("STATIC ONLY: existing resources and occupied ports NOT checked; isolation NOT established.")
        print("CONFIG PASS: no services started; no runtime authorization or clean-volume acceptance implied.")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Unsafe as error:
        print(f"PREFLIGHT REFUSED: {error}", file=sys.stderr)
        sys.exit(1)
