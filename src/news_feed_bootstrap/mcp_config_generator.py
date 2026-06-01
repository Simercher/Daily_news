from __future__ import annotations

from .config import PROJECT_ROOT, resolve_path
from .utils import write_json


def generate_mcp_config_hint(
    server: str = "imprvhub_mcp_rss_aggregator",
    output_path: str = "data/logs/mcp_config_hint.json",
) -> dict:
    opml_path = str(resolve_path("data/active_feeds.opml"))

    configs = {
        "imprvhub_mcp_rss_aggregator": {
            "server_id": "imprvhub_mcp_rss_aggregator",
            "recommended": True,
            "repo": "https://github.com/imprvhub/mcp-rss-aggregator",
            "capabilities": ["opml_import", "feed_category", "latest_articles", "source_category_filtering"],
            "mcp_config": {
                "mcpServers": {
                    "rssAggregator": {
                        "command": "node",
                        "args": [str(PROJECT_ROOT / "external" / "mcp-rss-aggregator" / "build" / "index.js")],
                        "env": {"FEEDS_PATH": opml_path},
                    }
                }
            },
        },
        "buhe_mcp_rss": {
            "server_id": "buhe_mcp_rss",
            "recommended": False,
            "repo": "https://github.com/buhe/mcp_rss",
            "requires": ["nodejs", "mysql"],
            "capabilities": ["opml_import", "rss_subscription_management", "article_update", "mcp_api"],
            "mcp_config": {
                "mcpServers": {
                    "mcp_rss": {
                        "command": "npx",
                        "args": ["mcp_rss"],
                        "env": {
                            "OPML_FILE_PATH": opml_path,
                            "DB_HOST": "localhost",
                            "DB_PORT": "3306",
                            "DB_USERNAME": "root",
                            "DB_PASSWORD": "123456",
                            "DB_DATABASE": "mcp_rss",
                            "RSS_UPDATE_INTERVAL": "30",
                        },
                    }
                }
            },
        },
        "rss_reader_mcp": {
            "server_id": "rss_reader_mcp",
            "recommended": False,
            "npm": "https://www.npmjs.com/package/rss-reader-mcp",
            "capabilities": ["rss_aggregation", "article_content_extraction"],
            "notes": "Use this later if full article extraction is needed.",
        },
        "veithly_rss_mcp": {
            "server_id": "veithly_rss_mcp",
            "recommended": False,
            "repo": "https://github.com/veithly/rss-mcp",
            "capabilities": ["universal_rss_atom_parsing", "rsshub_support"],
            "notes": "RSSHub feed does not mean official source. Mark RSSHub feeds as generated_by=rsshub if used.",
        },
    }
    if server not in configs:
        supported = ", ".join(sorted(configs))
        raise ValueError(f"Unsupported MCP server: {server}. Supported servers: {supported}")
    payload = configs[server]
    write_json(output_path, payload)
    return payload
