import json

import pytest

from news_system.config.sources import SourceConfigError, load_sources
from news_system.jobs import _load_collectors
from news_system.cli import main


def write_cfg(tmp_path, text):
    path = tmp_path / "sources.yaml"
    path.write_text(text)
    return path


def test_valid_config_loads_and_normalizes(tmp_path):
    path = write_cfg(tmp_path, """
sources:
  - name: Test RSS
    source_type: RSS
    enabled: yes
    url: https://example.com/feed.xml
    trusted: yes
    priority: "5"
    language: EN
    category: World
    country: US
""")
    src = load_sources(path)[0]
    assert src.name == "Test RSS"
    assert src.source_type == "rss"
    assert src.enabled is True
    assert src.trusted is True
    assert src.priority == 5
    assert src.language == "en"
    assert src.category == "world"
    assert src.country == "us"
    assert src.domain == "example.com"


@pytest.mark.parametrize("body, message", [
    ("""sources:\n  - name: Bad\n    source_type: nope\n    url: https://example.com/rss.xml\n""", "invalid source_type"),
    ("""sources:\n  - name: Same\n    source_type: rss\n    url: https://a.example/rss.xml\n  - name: same\n    source_type: rss\n    url: https://b.example/rss.xml\n""", "duplicate source name"),
    ("""sources:\n  - name: Missing URL\n    source_type: rss\n""", "missing url"),
])
def test_invalid_configs_fail(tmp_path, body, message):
    path = write_cfg(tmp_path, body)
    with pytest.raises(SourceConfigError, match=message):
        load_sources(path)


def test_disabled_source_not_collected(tmp_path):
    path = write_cfg(tmp_path, """
sources:
  - name: Enabled
    source_type: rss
    enabled: true
    url: https://enabled.example/rss.xml
  - name: Disabled
    source_type: rss
    enabled: false
    url: https://disabled.example/rss.xml
""")
    collectors = _load_collectors("all", path)
    assert [c.source_name for c in collectors] == ["Enabled"]
    assert collectors[0].feed_url == "https://enabled.example/rss.xml"


def test_cli_sources_validate_and_list_smoke(tmp_path, capsys):
    path = write_cfg(tmp_path, """
sources:
  - name: Enabled
    source_type: rss
    enabled: true
    trusted: true
    priority: 1
    url: https://enabled.example/rss.xml
  - name: Disabled
    source_type: gdelt
    enabled: false
    base_url: https://api.gdeltproject.org/api/v2/doc/doc
    query: climate
""")
    main(["sources", "validate", "--config", str(path)])
    validate = json.loads(capsys.readouterr().out)
    assert validate == {"enabled_count": 1, "ok": True, "source_count": 2}

    main(["sources", "list", "--config", str(path)])
    listed = json.loads(capsys.readouterr().out)
    assert [s["name"] for s in listed] == ["Enabled", "Disabled"]
    assert listed[0]["trusted"] is True
    assert listed[1]["enabled"] is False
