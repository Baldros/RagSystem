# Migracao de Schema: Offsets, Incremental e Recovery

Data: 2026-04-08  
Projeto: `E:/RagProject`

## Objetivo

Definir migracao incremental de banco para suportar:

1. Offsets e estrategia de chunk no schema (sem depender apenas de `metadata`).
2. Estado cross-run para incremental.
3. Estado run-level para resume/recovery.

## Principios

1. Migracao aditiva (sem quebra de leitura/escrita antiga).
2. Backfill progressivo.
3. Rollout por feature flags.

## Estado Atual

Tabelas principais:

- `raw_documents`
- `sections`
- `chunks`
- `discovered_nodes`
- `crawl_runs`

Atualmente, campos novos estao em `metadata` JSON:

- `doc_type`, `quality_score`, `navigation_score`
- `section_path`, `parent_section_id`
- `start_char`, `end_char`, `chunk_strategy`

## Schema Alvo (Faseado)

## Fase A: Colunas Estruturadas em Tabelas Existentes

### `raw_documents`

Adicionar:

- `doc_type text null`
- `quality_score real null`
- `navigation_score real null`
- `indexed_for_retrieval boolean null`

Indices sugeridos:

- `(collection_name, doc_type)`
- `(collection_name, indexed_for_retrieval)`

### `sections`

Adicionar:

- `parent_section_id text null`
- `section_path jsonb null`
- `section_slug_path jsonb null`

Indice sugerido:

- `(collection_name, canonical_url, parent_section_id)`

### `chunks`

Adicionar:

- `start_char integer null`
- `end_char integer null`
- `chunk_strategy text null`
- `is_navigation boolean null`

Indices sugeridos:

- `(collection_name, canonical_url, start_char)`
- `(collection_name, is_navigation)`

## Fase B: Estado Cross-Run (Incremental)

Nova tabela:

`collection_url_state`

- `collection_name text not null`
- `canonical_url text not null`
- `first_seen_at timestamptz not null`
- `last_seen_at timestamptz not null`
- `last_success_at timestamptz null`
- `last_http_status integer null`
- `last_content_hash text null`
- `doc_type text null`
- `quality_score real null`
- `max_discovered_depth integer not null default 0`
- `max_expanded_depth integer not null default 0`
- `is_indexed_for_retrieval boolean not null default false`
- `last_run_id text null`
- `last_error text null`
- `attempt_count_total integer not null default 0`
- `metadata jsonb not null default '{}'::jsonb`
- PK `(collection_name, canonical_url)`

## Fase C: Estado Run-Level (Resume/Recovery)

Nova tabela:

`crawl_run_urls`

- `run_id text not null`
- `collection_name text not null`
- `canonical_url text not null`
- `url text not null`
- `depth integer not null`
- `source text not null`
- `discovered_from text null`
- `status text not null`
- `attempt_count integer not null default 0`
- `last_error text null`
- `http_status integer null`
- `content_hash text null`
- `leased_until timestamptz null`
- `lease_owner text null`
- `metadata jsonb not null default '{}'::jsonb`
- `updated_at timestamptz not null`
- PK `(run_id, canonical_url)`
- FK `(run_id) -> crawl_runs(run_id)`

Indices sugeridos:

- `(run_id, status)`
- `(run_id, leased_until)`
- `(collection_name, status, updated_at desc)`

## Backfill

Ordem:

1. Criar colunas/tabelas (nullable + defaults).
2. Backfill em lotes pequenos (ex.: 5k registros por batch) extraindo de `metadata`.
3. Validar contagens.
4. Ativar escrita dupla (coluna + metadata).
5. Migrar leitura para colunas.
6. Tornar colunas `not null` quando seguro.

Exemplo de backfill parcial:

```sql
update raw_documents
set
  doc_type = coalesce(doc_type, metadata->>'doc_type'),
  quality_score = coalesce(quality_score, nullif(metadata->>'quality_score', '')::real),
  navigation_score = coalesce(navigation_score, nullif(metadata->>'navigation_score', '')::real),
  indexed_for_retrieval = coalesce(indexed_for_retrieval, (metadata->>'indexed_for_retrieval')::boolean)
where metadata ? 'doc_type'
  and (doc_type is null or quality_score is null or navigation_score is null or indexed_for_retrieval is null);
```

## Compatibilidade Aplicacao

Durante migracao:

- Escrita dupla:
  - manter `metadata` preenchido;
  - preencher colunas novas.
- Leitura:
  - preferir coluna;
  - fallback para `metadata`.

## Rollout Tecnico

1. Deploy SQL aditivo.
2. Deploy app com escrita dupla.
3. Rodar backfill.
4. Deploy app com leitura preferencial de colunas.
5. Opcional: remover dependencia de campos equivalentes no `metadata`.

## Rollback

Se houver problema:

1. Voltar app para leitura via `metadata`.
2. Manter colunas novas sem uso (nao destrutivo).
3. Reexecutar backfill apos correcao.

## Criterios de Aceitacao

1. Nenhuma regressao de retrieval apos migracao.
2. Percentual de linhas com colunas novas preenchidas > 99.9%.
3. Resume/recovery e incremental conseguem operar sem depender de parse caro de JSON metadata.

## Artefatos SQL Recomendados

- `sql/002_add_structured_columns.sql`
- `sql/003_add_collection_url_state.sql`
- `sql/004_add_crawl_run_urls.sql`
- `sql/005_backfill_structured_columns.sql`

