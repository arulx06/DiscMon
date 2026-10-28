from __future__ import annotations

from app.collectors.ashby import AshbyAdapter
from app.collectors.base import SourceAdapter
from app.collectors.github import GitHubAdapter
from app.collectors.greenhouse import GreenhouseAdapter
from app.collectors.lever import LeverAdapter
from app.collectors.rss_atom import RSSAtomAdapter
from app.collectors.static_html import ChangedetectionAdapter, ManualAdapter, StaticHTMLAdapter
from app.db.models.enums import SourceKind

_ADAPTERS: dict[str, SourceAdapter] = {
    SourceKind.ats_greenhouse.value: GreenhouseAdapter(),
    SourceKind.ats_lever.value: LeverAdapter(),
    SourceKind.ats_ashby.value: AshbyAdapter(),
    SourceKind.rss.value: RSSAtomAdapter(),
    SourceKind.github.value: GitHubAdapter(),
    SourceKind.static_html.value: StaticHTMLAdapter(),
    SourceKind.manual.value: ManualAdapter(),
    SourceKind.changedetection.value: ChangedetectionAdapter(),
    SourceKind.newsletter.value: ManualAdapter(),
    SourceKind.discovery_search.value: ManualAdapter(),
}


def get_adapter(kind: str) -> SourceAdapter:
    try:
        return _ADAPTERS[str(kind)]
    except KeyError as exc:
        raise ValueError(f"No adapter registered for source kind: {kind}") from exc


def adapter_kinds() -> list[str]:
    return sorted(_ADAPTERS)
