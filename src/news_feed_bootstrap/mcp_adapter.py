from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RssAdapter(Protocol):
    def fetch_latest(self, opml_path: str, output_path: str) -> None:
        """Fetch latest articles from an OPML subscription file."""


@dataclass(frozen=True)
class McpServerHint:
    id: str
    package_or_repo: str
    best_for: str
    notes: str


MCP_SERVER_HINTS = [
    McpServerHint(
        id="rss-reader-mcp",
        package_or_repo="npm:rss-reader-mcp",
        best_for="RSS aggregation plus article content extraction",
        notes="Use data/active_feeds.opml as the subscription input where supported.",
    ),
    McpServerHint(
        id="buhe-mcp-rss",
        package_or_repo="github:buhe/mcp_rss",
        best_for="Long-lived subscription and article storage",
        notes="Requires MySQL; keep database setup outside this MVP pipeline.",
    ),
    McpServerHint(
        id="imprvhub-mcp-rss-aggregator",
        package_or_repo="github:imprvhub/mcp-rss-aggregator",
        best_for="OPML import, categories, latest article queries",
        notes="Good fit for curated feeds exported by bootstrap.",
    ),
    McpServerHint(
        id="veithly-rss-mcp",
        package_or_repo="github:veithly/rss-mcp",
        best_for="Generic RSS/Atom parsing and RSSHub-compatible URLs",
        notes="Mark RSSHub-generated sources with generated_by=rsshub in downstream metadata.",
    ),
]


def mcp_setup_notes(opml_path: str = "data/active_feeds.opml") -> str:
    lines = [
        "MCP mode is intentionally adapter-only in this MVP.",
        f"Generate or refresh {opml_path}, then import it into one of these RSS MCP servers:",
    ]
    for server in MCP_SERVER_HINTS:
        lines.append(f"- {server.id}: {server.package_or_repo}; {server.best_for}. {server.notes}")
    lines.append("TODO: add a stdio MCP client once the target RSS MCP server is selected.")
    return "\n".join(lines)
