from __future__ import annotations

import json

from app.collectors.base import SourceAdapter, fetch_result_from_response
from app.collectors.http import HttpResponse, SafeFetcher
from app.config import get_settings
from app.schemas.collector import FetchResult, NormalizedCandidate, SourceConfig
from app.services.eligibility import infer_country_codes, infer_remote_countries
from app.services.normalize import classify_opportunity, parse_compensation_text
from app.services.text import excerpt, html_to_text
from app.services.time import extract_deadline_from_text, now_utc, parse_datetime
from app.services.urls import canonicalize_url, domain_of


class GitHubAdapter(SourceAdapter):
    kind = "github"
    supports_closure = False

    def allowed_hosts(self, source: SourceConfig) -> set[str]:
        base = source.config_json.get("base_url", "https://api.github.com")
        return {domain_of(base) or "api.github.com"}

    def _repos(self, source: SourceConfig) -> list[str]:
        repos = source.config_json.get("repos") or []
        if isinstance(repos, str):
            repos = [repos]
        repo = source.config_json.get("repo")
        if repo and repo not in repos:
            repos.append(repo)
        if not repos:
            raise ValueError("GitHub source requires config.repos")
        return [str(item).strip("/") for item in repos if item]

    async def fetch(
        self, source: SourceConfig, fetcher: SafeFetcher, cursor: str | None = None
    ) -> FetchResult:
        settings = get_settings()
        base = source.config_json.get("base_url", "https://api.github.com").rstrip("/")
        mode = source.config_json.get("mode", "releases")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        combined: list[dict] = []
        bodies: list[bytes] = []
        status = 200
        elapsed = 0
        last_headers: dict[str, str] = {}
        for repo in self._repos(source):
            if mode == "issues":
                labels = source.config_json.get("labels") or []
                label_query = ",".join(str(label) for label in labels)
                url = f"{base}/repos/{repo}/issues?state=open&per_page=50"
                if label_query:
                    url += f"&labels={label_query}"
            else:
                url = f"{base}/repos/{repo}/releases?per_page=30"
            response = await fetcher.get(url, headers=headers, conditional=False)
            elapsed += response.elapsed_ms
            last_headers = response.headers
            if response.error_class or response.status_code >= 400:
                status = response.status_code or status
                error = HttpResponse(
                    url=url,
                    status_code=response.status_code,
                    headers=response.headers,
                    content=b"",
                    elapsed_ms=elapsed,
                    error_class=response.error_class or "http_error",
                    error_message=(
                        response.error_message or f"GitHub returned {response.status_code}"
                    ),
                )
                return fetch_result_from_response(
                    source, error, content_json=None, scan_complete=False, source_url=url
                )
            try:
                items = json.loads(response.content)
                if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                    raise ValueError("Expected a GitHub API array of objects")
            except ValueError:
                error = HttpResponse(
                    url=url,
                    status_code=response.status_code,
                    headers=response.headers,
                    content=response.content,
                    elapsed_ms=elapsed,
                    error_class="invalid_response",
                    error_message="GitHub returned malformed JSON or an unexpected response shape",
                )
                return fetch_result_from_response(
                    source, error, content_json=None, scan_complete=False, source_url=url
                )
            bodies.append(response.content)
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    combined.append({"repo": repo, "item": item})
        content = b"\n".join(bodies)
        combined_response = HttpResponse(
            url=base,
            status_code=status,
            headers=last_headers,
            content=content,
            elapsed_ms=elapsed,
        )
        return fetch_result_from_response(
            source,
            combined_response,
            content_json={"items": combined, "mode": mode},
            scan_complete=False,
            source_url=base,
        )

    def parse(self, source: SourceConfig, result: FetchResult) -> list[NormalizedCandidate]:
        payload = result.content_json or {}
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("GitHub adapter produced no items")
        mode = payload.get("mode", "releases")
        candidates: list[NormalizedCandidate] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            repo = entry.get("repo")
            item = entry.get("item") or {}
            if mode == "issues" and "pull_request" in item:
                continue
            title = str(item.get("name") or item.get("title") or "").strip()
            url = item.get("html_url")
            if not title or not url:
                continue
            body = item.get("body") or ""
            text = html_to_text(body)
            external = item.get("id") or item.get("tag_name") or url
            published = parse_datetime(
                item.get("published_at") or item.get("created_at") or item.get("updated_at")
            )
            deadline = extract_deadline_from_text(text, now_utc())
            canonical = canonicalize_url(str(url))
            owner = str(repo).split("/")[0] if repo else source.name
            candidate = NormalizedCandidate(
                source_external_id=str(external),
                provider_key=f"github:{repo}:{mode}:{external}",
                title=title,
                organization_name=owner,
                organization_domain=None,
                opportunity_type=classify_opportunity(title, text),
                description_summary=excerpt(text, 1200),
                requirements_summary=excerpt(text, 2000),
                official_url=canonical,
                application_url=None,
                compensation=parse_compensation_text(text),
                published_at=published,
                deadline_on=deadline["deadline_on"],
                deadline_at=deadline["deadline_at"],
                deadline_timezone=deadline["deadline_timezone"],
                deadline_precision=deadline["deadline_precision"],
                source_payload={
                    "repo": repo,
                    "item": item,
                    "release_id": item.get("id"),
                    "tag_name": item.get("tag_name"),
                    "number": item.get("number"),
                },
                evidence_excerpt=excerpt(text, 600),
            )
            candidate.country_codes = infer_country_codes(candidate)
            candidate.allowed_remote_countries = infer_remote_countries(candidate)
            candidate.is_remote = "remote" in text.lower()
            candidates.append(candidate)
        return candidates
