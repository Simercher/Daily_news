# `news_system.jobs` Package Refactor Implementation Plan

> **Status (2026-06-04):** Implemented and verified. The `news_system.jobs` package was split into `shared.py`, `collect.py`, `events.py`, and `breaking.py`; `__init__.py` was reduced to a compatibility layer; package-level import compatibility was preserved; and validation passed with `187 passed, 1 warning` on the full pytest suite. A post-review compatibility fix was applied so package-level `collect_job` preserves positional-call behavior while still honoring monkeypatched `news_system.jobs._load_collectors` in tests.

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 將 `src/news_system/jobs/__init__.py` 從單一大型業務模組，重構為語意清楚、可維護的多檔案 package，同時保持既有 CLI、script、tests 的匯入介面相容。

**Architecture:** 保留 `news_system.jobs` 作為公開匯出層，但把實作拆到 `collect.py`、`events.py`、`breaking.py`、`shared.py` 之類的子模組。`__init__.py` 只負責 re-export 公開 API 與少數仍需對測試公開的 helper，確保 `from news_system.jobs import ...` 既有呼叫點不必同步大改。

**Tech Stack:** Python 3.13、SQLAlchemy、pytest、現有 `news_system` collectors / processors / repositories。

---

## Current State Snapshot

### Current implementation file
- `src/news_system/jobs/__init__.py`
  - 目前承載：
    - collectors 建立與 source config 套用
    - collection job orchestration
    - event persistence
    - daily event build flow
    - breaking watch flow
    - 多個 helper：`_to_model`、`_collector_for_source`、`_load_collectors`、`_apply_source_metadata`、`_source_key`、`_is_trusted_source`、`_event_category`、`_breaking_score`、`_apply_breaking_rules`、`_persist_events`

### Known import dependents
- `src/news_system/cli.py`
  - `from news_system.jobs import collect_job, daily_event_job, breaking_watch_job`
- `scripts/collect_rss_quick.py`
  - `from news_system.jobs import collect_job`

### Known test dependents
- `tests/test_collect_job.py`
- `tests/test_data_layer_mvp.py`
- `tests/test_newsapi_gdelt_collectors.py`
- `tests/test_source_credibility.py`
- `tests/test_sources_config.py`
- `tests/test_step4_daily_events.py`
- `tests/test_step5_breaking_events.py`

### Refactor constraints
1. **Do not break public imports** used by CLI/scripts/tests.
2. **Do not change runtime behavior** of collect / daily / breaking jobs in the same refactor unless a bug is discovered.
3. **Keep PostgreSQL-safe tests**; avoid introducing any destructive cleanup changes.
4. Prefer **mechanical extraction first**, behavior change later.

---

## Target Package Shape

```text
src/news_system/jobs/
  __init__.py
  collect.py
  events.py
  breaking.py
  shared.py
```

### Proposed responsibilities

#### `shared.py`
Cross-cutting helpers shared across jobs.
- `_to_model`
- `_source_key`
- `_is_trusted_source`
- `_event_category`
- `_persist_events`

#### `collect.py`
Collection-side source loading and article ingestion.
- `_collector_for_source`
- `_load_collectors`
- `_apply_source_metadata`
- `collect_job`

#### `events.py`
Daily event-building path.
- `daily_event_job`

#### `breaking.py`
Breaking-watch scoring and rule application.
- `BREAKING_CATEGORIES`
- `EXTREME_BREAKING_CATEGORIES`
- `_breaking_score`
- `_apply_breaking_rules`
- `breaking_watch_job`

#### `__init__.py`
Public compatibility layer only.
- Re-export:
  - `collect_job`
  - `daily_event_job`
  - `breaking_watch_job`
  - `_collector_for_source`
  - `_load_collectors`
  - `_apply_source_metadata`
- If tests still import additional private helpers later, re-export only those actually needed.

---

## Task 1: Freeze the current public surface with compatibility tests

**Objective:** 在動手拆檔前，先用測試鎖住目前外部可依賴的匯入面。

**Files:**
- Create: `tests/test_jobs_public_api.py`
- Reference: `src/news_system/jobs/__init__.py`

**Step 1: Write failing/guard test**

新增測試，至少覆蓋：
- `from news_system.jobs import collect_job, daily_event_job, breaking_watch_job`
- `from news_system.jobs import _load_collectors, _collector_for_source, _apply_source_metadata`
- 驗證這些 symbol 可匯入且 callable

範例：

```python
from news_system.jobs import (
    collect_job,
    daily_event_job,
    breaking_watch_job,
    _load_collectors,
    _collector_for_source,
    _apply_source_metadata,
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
```

**Step 2: Run test to verify baseline**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest tests/test_jobs_public_api.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_jobs_public_api.py
git commit -m "test: lock jobs package public api"
```

---

## Task 2: Extract shared helpers to `shared.py`

**Objective:** 先把最不具爭議的共用 helper 抽出，降低後續模組間重複 import 的混亂。

**Files:**
- Create: `src/news_system/jobs/shared.py`
- Modify: `src/news_system/jobs/__init__.py`
- Test: `tests/test_jobs_public_api.py`

**Step 1: Create `shared.py`**

把下列內容搬入：
- `_to_model`
- `_source_key`
- `_is_trusted_source`
- `_event_category`
- `_persist_events`

**Step 2: Keep behavior identical**

- 原函式內容先原封不動移動
- 只修正 import 路徑
- 不要順手改命名、不改演算法、不改參數

**Step 3: Update `__init__.py` to import from `shared.py`**

在 `__init__.py` 中暫時保留 job entrypoints，但改為：
- 從 `.shared` import helper
- 現有函式仍可使用這些 helper

**Step 4: Run narrow tests**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest \
  tests/test_jobs_public_api.py \
  tests/test_source_credibility.py \
  tests/test_step4_daily_events.py \
  tests/test_step5_breaking_events.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/news_system/jobs/shared.py src/news_system/jobs/__init__.py tests/test_jobs_public_api.py
git commit -m "refactor: extract shared jobs helpers"
```

---

## Task 3: Extract collection flow to `collect.py`

**Objective:** 把 source loading / metadata / collection orchestration 集中到獨立模組。

**Files:**
- Create: `src/news_system/jobs/collect.py`
- Modify: `src/news_system/jobs/__init__.py`
- Test: `tests/test_collect_job.py`
- Test: `tests/test_newsapi_gdelt_collectors.py`
- Test: `tests/test_sources_config.py`

**Step 1: Move collection-specific symbols**

搬移：
- `_collector_for_source`
- `_load_collectors`
- `_apply_source_metadata`
- `collect_job`

**Step 2: Import shared helpers from `.shared`**

`collect.py` 應依賴：
- `_to_model` from `.shared`

**Step 3: Make `__init__.py` a compatibility layer**

```python
from .collect import collect_job, _collector_for_source, _load_collectors, _apply_source_metadata
```

**Step 4: Run targeted tests**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest \
  tests/test_collect_job.py \
  tests/test_newsapi_gdelt_collectors.py \
  tests/test_sources_config.py \
  tests/test_jobs_public_api.py -v
```

Expected: PASS

**Step 5: Smoke the script import path**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/collect_rss_quick.py --help
```

Expected: usage output; no import error

**Step 6: Commit**

```bash
git add src/news_system/jobs/collect.py src/news_system/jobs/__init__.py
git commit -m "refactor: extract collection job module"
```

---

## Task 4: Extract event persistence and daily event flow to `events.py`

**Objective:** 將 daily event build 相關責任集中，讓 `breaking.py` 之後只專注在 breaking 判斷。

**Files:**
- Create: `src/news_system/jobs/events.py`
- Modify: `src/news_system/jobs/__init__.py`
- Test: `tests/test_step4_daily_events.py`
- Test: `tests/test_data_layer_mvp.py`

**Step 1: Move `daily_event_job` into `events.py`**

`events.py` 依賴：
- `_persist_events` from `.shared`
- 現有 processors/repositories imports

**Step 2: Avoid circular imports**

- `events.py` 不要從 `news_system.jobs` import helper
- 一律改成從 sibling modules import，例如 `.shared`

**Step 3: Re-export from `__init__.py`**

```python
from .events import daily_event_job
```

**Step 4: Run targeted tests**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest \
  tests/test_step4_daily_events.py \
  tests/test_data_layer_mvp.py \
  tests/test_jobs_public_api.py -v
```

Expected: PASS

**Step 5: Verify CLI import path**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run python -m news_system.cli build-events --help
```

Expected: help output; no import error

**Step 6: Commit**

```bash
git add src/news_system/jobs/events.py src/news_system/jobs/__init__.py
git commit -m "refactor: extract daily event job module"
```

---

## Task 5: Extract breaking flow to `breaking.py`

**Objective:** 將 breaking watch 規則、score、job entrypoint 集中到專屬模組。

**Files:**
- Create: `src/news_system/jobs/breaking.py`
- Modify: `src/news_system/jobs/__init__.py`
- Test: `tests/test_step5_breaking_events.py`
- Test: `tests/test_data_layer_mvp.py`

**Step 1: Move breaking-specific symbols**

搬移：
- `BREAKING_CATEGORIES`
- `EXTREME_BREAKING_CATEGORIES`
- `_breaking_score`
- `_apply_breaking_rules`
- `breaking_watch_job`

**Step 2: Import shared helpers from `.shared`**

`breaking.py` 依賴：
- `_source_key`
- `_is_trusted_source`
- `_event_category`
- `_persist_events`

**Step 3: Re-export from `__init__.py`**

```python
from .breaking import breaking_watch_job
```

**Step 4: Run targeted tests**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest \
  tests/test_step5_breaking_events.py \
  tests/test_data_layer_mvp.py \
  tests/test_jobs_public_api.py -v
```

Expected: PASS

**Step 5: Verify CLI import path**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run python -m news_system.cli watch-breaking --help
```

Expected: help output; no import error

**Step 6: Commit**

```bash
git add src/news_system/jobs/breaking.py src/news_system/jobs/__init__.py
git commit -m "refactor: extract breaking watch job module"
```

---

## Task 6: Shrink `__init__.py` to a pure compatibility layer

**Objective:** 最終讓 `__init__.py` 不再承載主要商業邏輯，只作 package 出口。

**Files:**
- Modify: `src/news_system/jobs/__init__.py`
- Test: `tests/test_jobs_public_api.py`

**Step 1: Reduce `__init__.py` to re-exports**

目標內容大致如下：

```python
from .breaking import breaking_watch_job
from .collect import _apply_source_metadata, _collector_for_source, _load_collectors, collect_job
from .events import daily_event_job

__all__ = [
    "collect_job",
    "daily_event_job",
    "breaking_watch_job",
    "_collector_for_source",
    "_load_collectors",
    "_apply_source_metadata",
]
```

**Step 2: Keep `__all__` explicit**

避免後續 private helper 不小心被 package-level export。

**Step 3: Run targeted tests**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest tests/test_jobs_public_api.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add src/news_system/jobs/__init__.py
git commit -m "refactor: make jobs init a compatibility layer"
```

---

## Task 7: Run integration verification across all known dependents

**Objective:** 在不做行為變更的前提下，確認所有已知依賴點仍然正常。

**Files:**
- No code changes expected

**Step 1: Run full targeted suite for jobs dependents**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest \
  tests/test_collect_job.py \
  tests/test_newsapi_gdelt_collectors.py \
  tests/test_source_credibility.py \
  tests/test_sources_config.py \
  tests/test_step4_daily_events.py \
  tests/test_step5_breaking_events.py \
  tests/test_data_layer_mvp.py \
  tests/test_jobs_public_api.py -v
```

Expected: PASS

**Step 2: Run CLI import smoke tests**

Run:
```bash
UV_PROJECT_ENVIRONMENT=.venv uv run python -m news_system.cli collect --help
UV_PROJECT_ENVIRONMENT=.venv uv run python -m news_system.cli build-events --help
UV_PROJECT_ENVIRONMENT=.venv uv run python -m news_system.cli watch-breaking --help
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/collect_rss_quick.py --help
```

Expected: all commands print help / usage successfully

**Step 3: Optional broader confidence run**

如果時間與成本允許：

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest -q
```

**Step 4: Commit**

```bash
git add -A
git commit -m "test: verify jobs package refactor compatibility"
```

---

## Review Checklist

- [ ] `src/news_system/jobs/__init__.py` 是否已從業務邏輯檔縮成相容層
- [ ] `collect_job` / `daily_event_job` / `breaking_watch_job` package-level import 是否維持不變
- [ ] tests 直接 import 的 private helpers 是否仍可匯入
- [ ] 有沒有引入 circular import
- [ ] `scripts/collect_rss_quick.py` 是否仍能正常顯示 help / import
- [ ] `python -m news_system.cli ... --help` 是否正常
- [ ] 沒有順手改變 scoring / persistence / source loading 行為

---

## Risks and Mitigations

### Risk 1: Circular imports between split modules
**Mitigation:** 所有共享 helper 集中放 `.shared`，子模組只從 sibling import，不從 `news_system.jobs` package root 回頭 import。

### Risk 2: Tests rely on private helper locations implicitly
**Mitigation:** 在 `__init__.py` 保留必要 re-exports，先相容、後清理。

### Risk 3: Accidental behavior change during extraction
**Mitigation:** 採用機械式搬移；每一階段只做一種 responsibility extraction，並立即跑對應窄測試。

### Risk 4: Over-refactor
**Mitigation:** 本輪只做 module boundary cleanup，不改 API 設計、不改執行流程、不改 repository 結構。

---

## Definition of Done

完成條件：
1. `src/news_system/jobs/__init__.py` 只剩 re-export / `__all__`。
2. `collect.py` / `events.py` / `breaking.py` / `shared.py` 完成拆分。
3. CLI、script、tests 既有匯入方式不需修改或只需極小改動。
4. 目標測試與 CLI smoke commands 全部通過。
5. 重構沒有伴隨功能行為變更。

---

## Suggested Execution Order

1. Task 1 — 先鎖 API 面
2. Task 2 — 抽 shared helpers
3. Task 3 — 抽 collect flow
4. Task 4 — 抽 daily events
5. Task 5 — 抽 breaking flow
6. Task 6 — 收斂 `__init__.py`
7. Task 7 — 全面驗證

這個順序的好處是：每一步都能保持 repo 可執行、可回滾、可 review。