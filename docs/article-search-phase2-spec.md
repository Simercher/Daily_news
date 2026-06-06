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
- add embedding search / semantic retrieval / RAG-style vector retrieval in the same milestone
- require SQLite tests to emulate PostgreSQL FTS perfectly

These capabilities are explicitly deferred to the next phase after PostgreSQL FTS lands and stabilizes.

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

### Pre-Implementation Decisions
Before implementation, Phase 2 is explicitly defined as follows.

#### 1. Backward compatibility policy
Phase 2 should be **100% backward compatible at the user-visible query semantics level** for all currently supported Phase 1 query forms:
- space-separated terms as AND
- explicit `OR`
- negation with `-term` / `-"phrase"`
- quoted phrases
- existing CLI flags and output shape

This means PostgreSQL FTS may improve ranking and internal execution, but it must not silently change what existing valid Phase 1 queries mean.

#### 2. Authority model: parser vs PostgreSQL function
The **custom parser remains authoritative**.

Phase 2 should not hand the raw user string directly to PostgreSQL as the source of truth. Instead:
1. parse query with the existing application parser
2. produce the normalized internal query structure
3. compile that normalized structure into PostgreSQL FTS expressions / tsquery

PostgreSQL functions such as `websearch_to_tsquery` may still be used as implementation helpers where appropriate, but they must not override parser-defined semantics.

#### 3. Fallback strategy
Phase 2 should use a split execution strategy:
- **PostgreSQL**: primary path uses FTS (`tsvector`, `tsquery`, ranking, GIN index)
- **SQLite**: fallback path stays on the existing Phase 1 LIKE/CASE engine

The repository/search layer should choose the strategy based on backend capabilities while preserving the same top-level contract.

#### 4. Test split strategy
Testing should be split by responsibility:
- **backend-agnostic parser/output tests**: run everywhere
- **SQLite tests**: validate fallback correctness and stable contract behavior
- **PostgreSQL integration tests**: validate FTS retrieval, ranking, and backend-specific execution

SQLite is not required to mimic PostgreSQL ranking exactly. It is required to preserve the contract and fallback semantics.

### Rationale
This combination gives:
- stable user-facing semantics
- predictable migration from Phase 1 to Phase 2
- explicit ownership of query meaning in application code
- clean backend specialization without breaking tests

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
