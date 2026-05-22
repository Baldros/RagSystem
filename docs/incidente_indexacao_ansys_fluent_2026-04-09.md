# Incidente: Falha na Etapa [3/3] de Indexacao (`ansys-fluent`)

Data do incidente: 2026-04-09  
Projeto: `E:/RagProject`  
Colecao: `ansys-fluent`

## Resumo executivo

O pipeline concluiu descoberta e processamento de paginas, mas falhou na etapa final de indexacao em PostgreSQL (`[3/3]`) ao tentar ler `processed/chunks.jsonl`.

O erro observado no traceback foi `PermissionError: [Errno 13] Permission denied`, mas a investigacao mostrou que o problema real e de I/O no arquivo `chunks.jsonl` (leitura inconsistente/corrompida em trecho intermediario), nao falta de permissao de usuario.

Em paralelo, houve log de `HTTP 429 Too Many Requests` para a API da Hugging Face. Esse `429` nao foi a causa primaria da queda da indexacao.

## Linha do tempo

1. `2026-04-09 10:53:37`  
   Descoberta concluida com sucesso:
   - `discovered 4778 candidate URLs`
   - `3187612 skipped`
   - `stop=completed`
2. Processamento de paginas concluido:
   - `Processing pages: 100%`
   - `4778/4778`
3. Carregamento do modelo de embeddings concluido:
   - `sentence-transformers/all-MiniLM-L6-v2`
   - pesos carregados
4. `2026-04-09 12:19:21`  
   Log de API externa:
   - `GET https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2`
   - resposta `HTTP 429 Too Many Requests`
5. Inicio da etapa `[3/3] indexing processed corpus into PostgreSQL`.
6. Falha ao ler `chunks.jsonl`:
   - traceback aponta para `read_jsonl(paths.chunks_jsonl)` em `src/rag_project/pipeline/jobs.py`.

## Evidencias coletadas

### Arquivos gerados (colecao `ansys-fluent`)

- `data/ansys-fluent/raw/documents.jsonl`: presente e legivel
- `data/ansys-fluent/processed/sections.jsonl`: presente e legivel
- `data/ansys-fluent/processed/chunks.jsonl`: presente, tamanho alto (~516 MB), leitura falha no meio

### Consistencia dos links (integridade da descoberta)

Validacao realizada sobre os artefatos locais:

- `inventory_rows`: `4778`
- `inventory_unique_canonical`: `4778`
- `discovered_nodes_rows`: `4778`
- `documents_rows`: `4778`
- `missing_in_documents_from_inventory`: `0`
- `discovery_report.stopped_reason`: `completed`

Conclusao: o conjunto de links esta integro para reaquisição/reprocessamento.

Observacao operacional:
- total de links canonical no inventario: `4778`
- paginas-base sem fragmento de ancora (`#...`): `634`

## Diagnostico tecnico

## 1) Erro em `chunks.jsonl` (causa principal da falha)

Sinais observados:

- Leitura sequencial de `chunks.jsonl` interrompida com `PermissionError`.
- Tentativa de leitura via PowerShell retornou:
  - `Erro nos dados (verificacao ciclica de redundancia)`.

Interpretacao:

- O sintoma de "permission denied" nao indica necessariamente ACL incorreta.
- Em Windows, falhas de I/O/lock em arquivo podem emergir como `PermissionError`.
- O conjunto de evidencias aponta para arquivo `chunks.jsonl` com trecho inconsistente/corrompido e/ou lock por processo externo.

## 2) `429` da API Hugging Face (causa secundaria, nao bloqueante imediata)

O projeto usa `SentenceTransformer(model_name, device=...)` em:
- `src/rag_project/embeddings/sentence_transformer_provider.py`

Mesmo com inferencia local (CPU/GPU), a biblioteca pode consultar o Hub para metadata do modelo (`/api/models/...`) quando inicializa/resolve cache.

Portanto:

- Sim, houve chamada de rede para Hugging Face.
- O `429` corresponde a rate-limit da API do Hub (nao envio do corpus para inferencia remota).
- A queda da etapa `[3/3]` ocorreu por leitura de `chunks.jsonl`, nao pelo `429`.

## Comportamento atual do pipeline (relevante para custo/tempo)

O fluxo atual efetua duas passagens HTTP:

1. Descoberta:
   - navega para descobrir links/TOC (`DiscoveryService.discover` + `http_client.get`/`extract_toc_entries`)
2. Processamento:
   - navega novamente para coletar conteudo por URL (`process_record` chama `http_client.get(record.url)`)

Depois disso, a etapa `[3/3]` apenas le os JSONL locais e indexa no banco.

## Impacto

- Indexacao em PostgreSQL nao concluida.
- Embeddings/chunks nao persistidos na tabela final.
- Perda de tempo operacional na tentativa de finalizar a run.
- Risco de retrabalho alto se reexecutar tudo do zero (etapa [2/3] e custosa).

## Recuperacao recomendada

1. Nao refazer descoberta (links estao integros).
2. Regenerar `chunks.jsonl` a partir de `sections.jsonl` (sem novo crawl/fetch).
3. Rodar apenas a indexacao (`scripts/index_corpus.py`).
4. Opcional: operar embeddings em modo estritamente offline/local para evitar dependencias do Hub.

## Acoes preventivas sugeridas

1. Escrita atomica de `chunks.jsonl`:
   - escrever em arquivo temporario e mover ao final.
2. Verificacao de integridade apos escrita:
   - contagem de linhas + leitura de ponta a ponta.
3. Retry de leitura para erros transientes de lock no Windows.
4. Opcao de modo offline para embeddings:
   - evitar consulta de metadata remota quando o modelo ja esta em cache local.
5. Separar etapa de "geracao de chunks" em script dedicado de recovery.

## Status final desta investigacao

- Links/descoberta: integros.
- `documents.jsonl` e `sections.jsonl`: integros.
- `chunks.jsonl`: com falha de leitura em runtime.
- `429` Hugging Face: confirmado, mas nao causa primaria da falha final.

