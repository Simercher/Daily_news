from __future__ import annotations

from typing import Literal

import typer

from .feed_fetcher import fetch_feed_items
from .mcp_adapter import mcp_setup_notes
from .mcp_config_generator import generate_mcp_config_hint
from .opml_importer import import_opml, merge_discovered
from .source_pack_importer import merge_source_packs
from .pipeline import bootstrap_candidates, build_active_feeds, dedup_raw_items, run_all, run_bootstrap, run_local_fetch

app = typer.Typer(help="RSS feed bootstrap, health check, MCP handoff, and raw item collection.")


@app.command("bootstrap-seeds")
def bootstrap_seeds(config_path: str = "configs/seed_sources.yaml") -> None:
    feeds = bootstrap_candidates(config_path)
    typer.echo(f"Imported/merged {len(feeds)} candidate feeds -> data/imported_feeds.json")


@app.command("import-source-packs")
def import_source_packs(*pack_paths: str, output_path: str = "configs/seed_sources.yaml") -> None:
    if not pack_paths:
        raise typer.BadParameter("Provide at least one source pack path.")
    merged = merge_source_packs(list(pack_paths), output_path=output_path)
    typer.echo(f"Merged {len(pack_paths)} source pack(s); seed registry now has {len(merged)} entries -> {output_path}")


@app.command("import-opml")
def import_opml_command(path: str) -> None:
    feeds = import_opml(path)
    merged = merge_discovered(feeds)
    typer.echo(f"Imported {len(feeds)} feeds; imported set now has {len(merged)} feeds")


@app.command("health-check")
def health_check(candidates_path: str = "data/imported_feeds.json") -> None:
    feeds = build_active_feeds(candidates_path=candidates_path)
    typer.echo(f"Accepted {len(feeds)} active feeds -> data/active_feeds.json and data/active_feeds.opml")


@app.command("bootstrap")
def bootstrap(config_path: str = "configs/seed_sources.yaml") -> None:
    feeds = run_bootstrap(config_path)
    typer.echo(f"Bootstrap complete: {len(feeds)} active feeds -> data/active_feeds.opml")


@app.command("fetch")
def fetch(
    mode: Literal["local", "mcp"] = "local",
    since_hours: int = 24,
    active_feeds_path: str = "data/active_feeds.json",
    server: str = "imprvhub_mcp_rss_aggregator",
) -> None:
    if mode == "mcp":
        generate_mcp_config_hint(server)
        raise typer.BadParameter("MCP fetch is adapter-only in this MVP. Use local mode or an external MCP tool.")
    items = fetch_feed_items(active_feeds_path=active_feeds_path, since_hours=since_hours)
    typer.echo(f"Fetched {len(items)} raw items -> data/news_items_raw.jsonl")


@app.command("fetch-local")
def fetch_local(since_hours: int = 24, active_feeds_path: str = "data/active_feeds.json") -> None:
    items = run_local_fetch(since_hours=since_hours, active_feeds_path=active_feeds_path)
    typer.echo(f"Fetched {len(items)} raw items -> data/news_items_raw.jsonl")


@app.command("dedup")
def dedup() -> None:
    items = dedup_raw_items()
    typer.echo(f"Deduplicated {len(items)} items -> data/news_items_deduped.jsonl")


@app.command("run-all")
def run_all_command(mode: Literal["local", "mcp"] = "local", since_hours: int = 24) -> None:
    stats = run_all(mode=mode, since_hours=since_hours)
    typer.echo(f"Daily RSS pipeline complete: {stats}")


@app.command("mcp-config")
def mcp_config(server: str = "imprvhub_mcp_rss_aggregator") -> None:
    generate_mcp_config_hint(server)
    typer.echo("Wrote MCP config hint -> data/logs/mcp_config_hint.json")


@app.command("mcp-notes")
def mcp_notes(opml_path: str = "data/active_feeds.opml") -> None:
    typer.echo(mcp_setup_notes(opml_path))


if __name__ == "__main__":
    app()
