# Crawler Resume/Recovery: Retomar Run Interrompido com Seguranca

Data: 2026-04-08  
Projeto: `E:/RagProject`

## Objetivo

Definir como retomar uma execucao quebrada sem reiniciar tudo, com garantias de:

1. Idempotencia (sem duplicar dados).
2. Reprocessamento somente do necessario.
3. Diagnostico claro do que faltou.

## Escopo

Inclui:

- Estado por URL dentro de um run especifico.
- Checkpoint de fila.
- Lease/timeout para itens "em processamento".
- Requeue seguro apos crash.

Nao inclui:

- Expansao incremental entre runs com novo escopo (ver `docs/crawler_incremental.md`).

## Modelo de Estado (Run-Level)

Tabela proposta:

`crawl_run_urls`

- `run_id` (PK parcial)
- `canonical_url` (PK parcial)
- `url`
- `depth`
- `source`
- `discovered_from`
- `status` (`pending`, `processing`, `done`, `failed`, `skipped`)
- `attempt_count`
- `last_error`
- `http_status`
- `content_hash`
- `leased_until`
- `lease_owner`
- `updated_at`
- `metadata`

## Maquina de Estados

Transicoes:

- `pending -> processing`
- `processing -> done`
- `processing -> failed`
- `processing -> pending` (quando lease expira)
- `pending -> skipped` (fora escopo, duplicada, guard rail)

Invariante:

- Uma URL de um run nao pode estar em mais de um estado ativo ao mesmo tempo.

## Fluxo de Resume

Ao iniciar com `--resume`:

1. Carregar run alvo (`latest` ou `run_id`).
2. Reclassificar `processing` com `leased_until < now` para `pending`.
3. Retomar loop consumindo somente `pending`.
4. Manter `done/failed/skipped` como historico.

## Estrategia de Lease

- Quando worker pega item:
  - seta `status=processing`
  - define `lease_owner`
  - define `leased_until=now + lease_ttl`
- Worker renova lease em operacoes longas.
- Em restart:
  - itens com lease vencido voltam para `pending`.

## Idempotencia de Escrita

1. `upsert_raw_document` por `(collection_name, canonical_url)`.
2. `replace_sections` e `replace_chunks` por URL (ja existe).
3. Checkpoint de status no run so apos commit de dados da URL.

Regra:

- Se crash ocorrer antes do commit final de status, URL volta para `pending` e e reprocessada com segurança.

## Politica de Tentativas

- `max_attempts_per_url` (ex.: 3).
- Se ultrapassar:
  - `status=failed`
  - registrar `last_error`.

## Relatorio de Recovery

Adicionar em `processed/discovery_report.json`:

- `resumed_from_run_id`
- `requeued_from_expired_lease_count`
- `pending_at_start`
- `done_before_resume`
- `done_after_resume`
- `failed_after_resume`

## CLI Proposta

- `--resume` (retoma ultimo run incompleto da colecao)
- `--resume-run-id <id>`
- `--lease-ttl-seconds <int>`
- `--max-attempts-per-url <int>`

## Cenarios de Teste

1. Crash durante fetch:
   - URL volta para `pending`.
2. Crash apos salvar documento e antes de marcar `done`:
   - reprocessamento nao duplica chunks.
3. Dois processos concorrentes com mesmo run:
   - lease evita conflito de trabalho na mesma URL.

## Criterios de Aceitacao

1. Resume nao reinicia run inteiro.
2. URLs `done` nao voltam para processamento normal.
3. Crash simulation termina com cobertura igual ao run sem crash.

## Riscos e Mitigacoes

- Risco: lease curto demais gera retrabalho.
  - Mitigacao: renovar lease por heartbeat.
- Risco: lease longo demais atrasa retomada.
  - Mitigacao: TTL configuravel.
- Risco: estado de run crescer muito.
  - Mitigacao: retention/purge por idade de run.

## Plano de Implementacao

Fase 1:

1. Tabela `crawl_run_urls` e status basico.
2. Resume simples sem lease (somente `pending/failed`).

Fase 2:

1. Lease + requeue por expiracao.
2. Testes de crash e concorrencia.

Fase 3:

1. Telemetria completa de recovery.
2. Politicas de retention de runs antigos.

