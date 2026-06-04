from __future__ import annotations

from news_system.jobs import (
    _apply_source_metadata,
    _collector_for_source,
    _load_collectors,
    breaking_watch_job,
    collect_job,
    daily_event_job,
)


def test_jobs_package_public_api_is_stable():
    for obj in (
        collect_job,
        daily_event_job,
        breaking_watch_job,
        _load_collectors,
        _collector_for_source,
        _apply_source_metadata,
    ):
        assert callable(obj)


def test_jobs_collect_job_uses_package_level_load_collectors(monkeypatch):
    seen = {}

    def fake_load_collectors(source, config_path):
        seen["call"] = (source, config_path)
        return []

    monkeypatch.setattr("news_system.jobs._load_collectors", fake_load_collectors)
    result = collect_job(None, "rss", 24, None, "custom.yaml")

    assert seen["call"] == ("rss", "custom.yaml")
    assert result["fetched"] == 0
    assert result["inserted"] == 0
