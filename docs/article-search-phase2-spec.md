# Article Search Phase 2 Specification

## Goal
Evolve `article-search-v2` from the current portable Phase 1 boolean-lite search into a PostgreSQL-native retrieval layer with stronger ranking, better query semantics, and cleaner future support for grouped duplicates and richer retrieval features.

## Relationship to Phase 1
Phase 1 is already responsible for:
- `AND` / `OR` / `NOT` / phrase query parsing
- SQLite-compatible LIKE/CASE execution
- simple transparent scoring
- JSON `query_plan`, `score`, `matched_fields`, `matched_terms`

Phase 2 should preserve the same top-level CLI contract where practical while replacing the execution engine in PostgreSQL.

## Non-Goals
Phase 2 should not:
- redesign duplicate detection itself
- add semantic/vector search in the same milestone
- require SQLite tests to emulate PostgreSQL FTS perfectly

## Target User Outcomes
Phase 2 should improve:
- relevance ranking for multi-term article investigation
- phrase handling and boolean search fidelity
- performance over larger article volumes
- future support for source-aware/grouped result presentation

## Proposed Architecture
### 1. Keep a parsed-query layer
Continue using a parser-normalized internal query object so the CLI/API contract remains stable.

### 2. Add PostgreSQL FTS documents
Build a weighted tsvector over:
- A-weight: `title`
- B-weight: `description`
- C-weight: `content_snippet`

Proposed conceptual expression:

```sql
setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
setweight(to_tsvector('simple', coalesce(content_snippet, '')), 'C')
```

### 3. Query translation layer
Translate the existing parsed search query into PostgreSQL `tsquery`.
Primary target:
- `websearch_to_tsquery('simple', <query>)`

Fallbacks when necessary:
- `phraseto_tsquery`
- `plainto_tsquery`
- explicit tsquery composition for negation-heavy or parser-specific edge cases

### 4. Ranking
Use `ts_rank_cd(search_vector, tsquery)` as the primary score.
Then sort by:
1. `ts_rank_cd(...) DESC`
2. `published_at DESC`
3. `id DESC`

### 5. Keep Phase 1 fallback
Maintain the current Phase 1 LIKE/CASE execution path for:
- SQLite tests
- fallback behavior where PostgreSQL FTS is unavailable

This implies a strategy selection layer, not a hard swap.

## Data Model Changes
### Option A: generated column or persisted column
Add a searchable tsvector column on `articles`, for example `search_vector`.

Possible strategies:
1. generated/stored column if supported by deployment constraints
2. normal column maintained by application writes
3. normal column maintained by DB trigger

Preferred direction: DB-managed update path if it stays simple and observable.

### Indexing
Add a GIN index on the search vector.

Example conceptually:

```sql
CREATE INDEX ix_articles_search_vector ON articles USING GIN (search_vector);
```

## Query Semantics
### Required semantics to preserve
- `AND`
- `OR`
- `NOT`
- quoted phrases
- `source`, `category`, `lookback_hours`, `include_duplicates`

### Desired semantic improvement over Phase 1
- better phrase fidelity
- more sensible ranking for partial vs strong field matches
- less manual score maintenance in Python

### Caution
The current Phase 1 parser semantics are simplified. Phase 2 must explicitly decide whether to:
1. preserve that simplified model exactly for compatibility, or
2. promote the query language to a more faithful boolean model

Recommendation:
- preserve existing user-visible behavior first
- expand semantics only behind tests and explicit docs

## Output Contract
Preserve these top-level output fields:
- `cmd`
- `query`
- `lookback_hours`
- `limit`
- `source`
- `category`
- `include_duplicates`
- `query_plan`
- `count`
- `articles`

Per article preserve:
- `score`
- `matched_fields`
- `matched_terms`
- `content_snippet`

### Metadata policy
Even if ranking becomes PostgreSQL-native, continue returning explainability metadata.
If exact field-term provenance becomes expensive to compute in SQL, allow a hybrid approach:
- PostgreSQL provides retrieval/ranking
- Python derives `matched_fields`/`matched_terms` for the final limited result set

## Duplicate Presentation Hooks
Duplicate redesign is out of scope for this milestone, but Phase 2 should avoid blocking future result grouping.
Design preference:
- keep `SearchResult` extensible for future fields such as:
  - `group_id`
  - `duplicate_count`
  - `representative_article_id`

## Files Likely to Change
- `src/news_system/storage/repositories.py`
- `src/news_system/search/query_parser.py` (only if semantics are adjusted)
- `src/news_system/search/types.py`
- `src/news_system/serializers.py`
- `src/news_system/cli.py`
- migration files for article search vector/index
- PostgreSQL integration tests

## Testing Strategy
### Unit tests
Keep parser unit tests and output-shape tests.

### Integration tests
Add PostgreSQL-backed integration tests for:
- ranking quality
- phrase handling
- negation handling
- source/category filters combined with FTS
- duplicate include/exclude compatibility

### Fallback tests
Ensure SQLite still uses the Phase 1 fallback path and remains green.

## Acceptance Criteria
Phase 2 is complete when:
- PostgreSQL path uses indexed FTS retrieval
- CLI/API contract remains stable
- relevance ranking is materially better than Phase 1 on multi-term queries
- SQLite fallback remains working in tests
- parser behavior is documented and verified

## Suggested Implementation Order
1. Add migration/design for `search_vector` and GIN index.
2. Implement PostgreSQL strategy selection in repository search.
3. Translate parsed query to tsquery.
4. Rank with `ts_rank_cd`.
5. Preserve JSON explainability metadata.
6. Add PostgreSQL integration tests.
7. Benchmark correctness and ranking on real article samples.

## Open Questions
- Should Phase 2 continue exact Phase 1 boolean-lite semantics or adopt truer boolean precedence?
- Should `websearch_to_tsquery` be the main path, or should the custom parser remain authoritative and compile to tsquery manually?
- Should search vector updates live in application code or the database layer?
- How should grouped duplicate presentation interact with ranking in later work?
