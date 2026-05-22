# Crawler Incremental: Expansao de Cobertura sem Reprocessar Tudo

Data: 2026-04-08  
Projeto: `E:/RagProject`

## Objetivo

Definir como o crawler deve executar em modo incremental para:

1. Expandir cobertura com nova configuracao (ex.: profundidade maior).
2. Evitar refetch/reprocessamento desnecessario de paginas ja estaveis.
3. Preservar consistencia do indice de retrieval.

## Escopo

Inclui:

- Descoberta incremental por fronteira de links.
- Reuso de estado historico por `collection + canonical_url`.
- Reprocessamento condicional por mudanca de `content_hash`.

Nao inclui (documentado separadamente):

- Retomada de run interrompido no meio (ver `docs/crawler_resume_recovery.md`).

## Definicoes

- `URL conhecida`: URL ja registrada em estado persistido da colecao.
- `URL expandida`: URL cujo TOC/link extraction ja foi executado ate um `depth` alvo.
- `URL materializada`: URL com `raw_document` salvo.
- `URL indexada`: URL com sections/chunks persistidos para retrieval.

## Requisitos Funcionais

1. Rodar com profundidade maior deve processar somente fronteira nova.
2. URL sem alteracao de conteudo nao deve regenerar sections/chunks/embeddings.
3. URL com conteudo alterado deve atualizar sections/chunks e embeddings.
4. Cobertura deve indicar claramente o que foi:
   - reaproveitado;
   - atualizado;
   - descoberto novo.

## Modelo de Estado (Cross-Run)

Proposta de tabela de estado por colecao:

`collection_url_state`

- `collection_name` (PK parcial)
- `canonical_url` (PK parcial)
- `first_seen_at`
- `last_seen_at`
- `last_success_at`
- `last_http_status`
- `last_content_hash`
- `doc_type`
- `quality_score`
- `max_discovered_depth`
- `max_expanded_depth`
- `is_indexed_for_retrieval`
- `last_run_id`
- `last_error`
- `attempt_count_total`

## Contrato de Expansao Incremental

Entrada:

- `target_max_depth`
- politicas de recrawl:
  - `recrawl_changed_only=true` (default)
  - `recrawl_all=false` (default)

Regra:

1. Se URL nunca foi vista: processar.
2. Se URL foi vista, mas `max_expanded_depth < target_max_depth`: expandir links desta URL.
3. Se URL foi materializada e hash nao mudou: nao regenerar chunks.
4. Se hash mudou: regenerar sections/chunks/embeddings desta URL.

## Algoritmo (Resumo)

1. Carregar `collection_url_state` da colecao.
2. Montar fronteira inicial:
   - seeds;
   - URLs elegiveis para expansao adicional (`max_expanded_depth < target`).
3. Para cada URL:
   - fetch snapshot;
   - calcular hash e classificacao;
   - atualizar estado cross-run;
   - expandir filhos se permitido por depth.
4. Persistir deltas:
   - novos documentos;
   - documentos alterados;
   - novos links.
5. Atualizar relatorio incremental.

## Politicas de Dedupe

- Chave de identidade: `canonical_url`.
- Chave de mudanca de conteudo: `content_hash`.
- Chave de idempotencia de chunk: `section_id + order_in_section` (hash deterministico).

## Relatorio Incremental (Novo)

Adicionar em `processed/coverage_report.json`:

- `reused_url_count`
- `updated_url_count`
- `new_url_count`
- `expanded_existing_url_count`
- `unchanged_content_count`
- `changed_content_count`

## CLI Proposta

- `--incremental` (liga modo incremental)
- `--target-max-depth <int>`
- `--recrawl-all` (forca recrawl completo)
- `--recrawl-pattern <substring>` (multiplos)

## Criterios de Aceitacao

1. Rodar com `max_depth=2` e depois `max_depth=4` aumenta cobertura sem duplicar processamento antigo.
2. Segunda execucao com mesmo depth e sem mudanca externa nao reindexa quase nada.
3. Mudanca de uma pagina gera update somente daquela pagina no indice.

## Riscos e Mitigacoes

- Risco: URL canonicalizada diferente entre runs.
  - Mitigacao: fixar canonicalization e criar teste de regressao.
- Risco: hash instavel por conteudo dinamico.
  - Mitigacao: normalizar HTML/markdown antes do hash.
- Risco: custo de expansao em corpora muito grandes.
  - Mitigacao: manter guard rails de runtime/failures/bytes.

## Plano de Implementacao

Fase 1 (base):

1. Criar `collection_url_state`.
2. Persistir estado por URL ao final de cada processamento.
3. Expor metricas de reuso/update/new.

Fase 2 (otimizacao):

1. Fronteira incremental real por `max_expanded_depth`.
2. Recrawl seletivo por padrao de URL.
3. Testes de performance comparando run full vs incremental.

