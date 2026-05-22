# Avaliacao Tecnica: Crawler, Processo e Segmentacao

Data: 2026-04-08  
Projeto: `E:/RagProject`

## Escopo avaliado

Revisei os pontos que voce pediu:

1. Processo de crawling (descoberta, fetch, cobertura e limite de paginas).
2. Tratamento de dados (separacao TOC vs conteudo real, segmentacao em topicos/subtopicos, e armazenamento em camadas para RAG).

Arquivos principais revisados:

- `src/rag_project/discovery/service.py`
- `src/rag_project/fetching/http_client.py`
- `src/rag_project/pipeline/jobs.py`
- `src/rag_project/extraction/content_extractor.py`
- `src/rag_project/processing/sectionizer.py`
- `src/rag_project/processing/chunker.py`
- `src/rag_project/config.py`
- `sql/001_init.sql`
- artefatos em `data/ansys-fluent*`

## Diagnostico

### 1) O crawler hoje faz trabalho duplicado (descobre e depois busca de novo)

- Na descoberta, cada URL passa por `extract_toc_entries()` (`discovery/service.py:68`) que abre/renderiza pagina via Selenium (`fetching/http_client.py:102-104`, `106+`).
- Na etapa de processamento, a mesma URL volta para `get(record.url)` (`pipeline/jobs.py:105`), abrindo/renderizando novamente.
- O cache de resposta (`http_client.py:89`) so funciona para `get()`, mas `extract_toc_entries()` nao grava no cache de resposta.

Impacto: alto custo de navegador/rede e tempo de execucao maior que o necessario.

### 2) A descoberta esta limitada por paginas E por profundidade

- A descoberta para quando `len(records) == max_pages` (`discovery/service.py:40`).
- Em corpus largo (TOC gigante), a fila BFS fica cheia de links de nivel 1 antes de chegar em nivel 2+.
- Existe tambem um teto fixo de expansao de profundidade (`if depth > 2: continue` em `discovery/service.py:64-65`).
- Evidencia em `data/ansys-fluent`:
  - `inventory_count=300`
  - `seed=1`, `toc=299`
  - `max_depth=1`

Impacto: cobertura estrutural incompleta por duas vias:

- truncamento por quantidade (`max_pages`);
- truncamento por regra fixa de profundidade (`depth > 2`).

### 3) Cobertura reportada pode parecer boa, mas mede inventario interno (nao cobertura real da documentacao)

- `coverage_report` compara `inventory` vs `documents` (`reporting/coverage.py`).
- Se o inventario ja veio enviesado por TOC/menu, pode dar cobertura alta sem cobrir conteudo real.
- Exemplo `ansys-fluent-smoke`: `coverage_ratio=1.0` com apenas 5 URLs.

Impacto: falso senso de completude.

### 4) Mistura de TOC com conteudo real ocorre no pipeline de extracao/sectionizacao

Evidencias fortes:

- Em `data/ansys-fluent-smoke/processed/sections.jsonl`, a URL seed virou uma secao unica `heading="Document"` com lista gigante de menu (`__Collapse__all`, milhares de itens de TOC).
- Em `data/ansys-fluent`:
  - `sections_count=426`
  - `heading_Document=264`
  - `toc_like_docs=46` (detectando "Collapse all" no texto)

Causas tecnicas:

- TOC collector tem fallback agressivo para `document.body` quando encontra poucos links em containers (`http_client.py:341`).
- `ContentExtractor` usa `trafilatura` e fallback para texto inteiro (`content_extractor.py`), sem classificar pagina como "navegacao" vs "conteudo".
- `sectionizer` cria secao unica "Document" quando nao ha headings markdown (`sectionizer.py:21-35`), e esse bloco gigantesco segue para chunking.

Impacto: chunks ruidosos, pior retrieval, e estrutura semantica fraca para RAG.

### 5) Segmentacao atual e funcional, mas insuficiente para hierarquia "humana"

- `split_markdown_into_sections` depende de headings markdown (`sectionizer.py:9+`).
- Quando markdown vem "flattened", perde topico/subtopico real.
- `chunker` corta por janela de caracteres (`chunker.py`), sem fronteira semantica/sentenca.
- Metadados de hierarquia no chunk sao minimos (`metadata={"heading": ...}`), sem caminho completo de topico.

Impacto: perda de contexto de navegacao e baixa rastreabilidade topico -> subtopico -> trecho.

## Propostas de melhoria (priorizadas)

## P0 (maior impacto imediato)

### P0.1 Unificar descoberta + fetch (single-pass por URL)

Objetivo: cada URL ser aberta/renderizada uma unica vez.

Sugestao:

- Trocar o contrato da descoberta para retornar tambem snapshot minimo da pagina (html renderizado, status, headers, url final).
- Na descoberta:
  1. `response = http_client.get(url)`
  2. extrair TOC a partir do mesmo DOM/render ja carregado (sem nova navegacao)
  3. guardar `response` para etapa de processamento
- No processamento: reutilizar snapshot (ou cache persistido) em vez de novo `get()`.

Observacao importante:

- Em documentacoes com TOC dinamico, extrair TOC so por parser estatico de HTML pode reduzir recall.
- Portanto, manter a extracao por DOM renderizado e reaproveitar esse mesmo render (single-pass), em vez de renderizar duas vezes.

Resultado esperado: reducao grande de tempo e custo de crawling.

### P0.2 Modo "buscar maximo" sem `max_pages` fixo

Objetivo: atender seu requisito de sempre buscar o maximo de paginas validas.

Sugestao:

- Permitir `--max-pages 0` como "sem limite de paginas".
- Introduzir guard rails operacionais:
  - `--max-runtime-minutes`
  - `--max-failures`
  - `--max-total-bytes` (opcional)
- Tornar o default orientado a completude: sem limite de paginas + limite de tempo seguro.

Nota de implementacao:

- Hoje, `len(records) < max_pages` faz `--max-pages 0` resultar em zero URLs processadas.
- Para suportar "sem limite", tratar `max_pages <= 0` como `None` (ou `infinito`) e ajustar o loop/CLI.

Resultado esperado: maior cobertura real sem travar execucao indefinidamente.

### P0.3 Filtro de pagina de navegacao (TOC-only) antes de indexar

Objetivo: parar de misturar menu com conteudo.

Heuristica simples (ja suficiente para 1a versao):

- Se `link_density` alto + baixa densidade de paragrafos + termos de navegacao (ex.: `collapse all`) -> classificar `doc_type="navigation"`.
- `doc_type="navigation"`:
  - manter em `discovered_nodes` para grafo/hierarquia
  - nao mandar para `sections/chunks` de retrieval, ou mandar com flag `is_navigation=true` e peso menor.

Resultado esperado: queda forte de ruido no indice.

### P0.4 Contrato de responsabilidade: usuario define escopo, sistema garante execucao

Objetivo: nao delegar toda a estrategia ao sistema e tornar o comportamento previsivel.

Proposta de contrato:

- Usuario define explicitamente:
  - profundidade alvo (`--max-depth`), ou modo "todos os niveis".
  - limite de paginas (`--max-pages`) e guard rails operacionais.
  - escopo de URL (dominio/prefixo includo e exclusoes).
- Sistema deve garantir:
  - percorrer todos os links aceitos dentro do escopo configurado.
  - registrar para cada URL nao processada um motivo objetivo (`fora_escopo`, `erro_fetch`, `bloqueio_robots`, `duplicada`, `guard_rail`).
  - reportar cobertura por nivel de profundidade para auditoria.

Resultado esperado: controle real pelo usuario + rastreabilidade tecnica do que foi (ou nao foi) coberto.

## P1 (melhora estrutural da qualidade de RAG)

### P1.1 Melhorar escopo de dominio/caminho para nao fugir da doc alvo

Hoje:

- `same_domain` esta correto para seguranca basica.
- `include_url_patterns` para URLs com `returnurl` usa apenas 3 segmentos (`config.py:129-141`), o que pode incluir area ampla demais.

Sugestao:

- Normalizar `returnurl` e extrair prefixo real da doc (ex.: `/Views/Secured/corp/v261/en/flu_ug/`).
- Validar URLs por `path_prefix` canonico + dominio.
- Registrar motivo de aceitacao/rejeicao no metadata.

Resultado esperado: mais completude da documentacao alvo e menos poluicao de links laterais.

### P1.2 Usar `max_workers` de fato no pipeline (performance)

Hoje:

- `max_workers` existe na configuracao (`config.py`), mas o processamento em `crawl_to_filesystem` e sequencial.

Sugestao:

- Aplicar paralelismo controlado no processamento de documentos (com limites de concorrencia e retry).
- Garantir que escrita de artefatos continue deterministica (ordenacao por URL/canonical antes de persistir).

Resultado esperado: reducao de tempo de parede em corpus grandes, sem mudar a qualidade semantica.

### P1.3 Sectionizer hierarquico de verdade (topic/subtopic)

Objetivo: refletir a estrutura "humana" que voce descreveu.

Sugestao:

- Extrair secoes por arvore de heading HTML (`h1..h6`) preservando path:
  - `section_path`: `["Part I", "1.2 Program Capabilities", ...]`
  - `section_slug_path`
  - `parent_section_id`
- Quando nao houver heading confiavel:
  - segmentar por blocos semanticos (paragrafos/listas/tabelas) antes de chunking.

Resultado esperado: dados muito melhores para RAG navegavel por topicos.

### P1.4 Chunking semantico (nao so janela de caracteres)

Sugestao:

- Chunk por sentencas/paragrafos com alvo de tokens.
- Aplicar overlap por unidade semantica.
- Salvar offsets (`start_char`, `end_char`) e `chunk_strategy`.

Resultado esperado: chunks mais coerentes, melhor matching lexical/vetorial.

## P2 (governanca e confiabilidade)

### P2.1 Cobertura em dois niveis: descoberta e conteudo

Adicionar metricas separadas:

- `discovered_url_count`
- `content_url_count` (URLs classificadas como conteudo)
- `indexed_content_url_count`
- `navigation_url_count`
- distribuicao por profundidade e por origem (`seed/sitemap/toc/content-link`)

Resultado esperado: cobertura passa a representar realidade da documentacao.

Complemento de garantia minima de navegacao:

- Para cada URL raiz (`seed`), os links diretos do TOC de primeiro nivel devem estar:
  - processados; ou
  - rejeitados com motivo registrado.
- O relatorio deve expor explicitamente:
  - `seed_toc_level1_total`
  - `seed_toc_level1_processed`
  - `seed_toc_level1_rejected_by_reason`

Isso garante ao menos a cobertura dos topicos principais, mesmo quando a profundidade escolhida pelo usuario e limitada.

### P2.2 Camadas de armazenamento explicitas

Voce ja iniciou esse caminho. Recomendo formalizar:

1. `layer_discovery`: grafo de navegacao (nodes/edges, source, toc_level, toc_order).
2. `layer_documents`: html bruto + markdown/text limpo + `doc_type` + score de qualidade.
3. `layer_sections`: secoes hierarquicas com `parent_section_id`, `section_path`.
4. `layer_chunks`: chunks semanticos com metadados completos para retrieval.

No banco, considerar novas colunas:

- `raw_documents.doc_type`, `raw_documents.quality_score`
- `sections.parent_section_id`, `sections.section_path`
- `chunks.start_char`, `chunks.end_char`, `chunks.is_navigation`

## Plano de implementacao sugerido

1. P0.1 (single-pass) + P0.3 (filtro TOC-only) primeiro.
2. P0.2 (modo sem limite de paginas com guard rails).
3. Revisar criterio de profundidade (`depth > 2`) conforme objetivo de cobertura.
4. P1.1 (path scope preciso para doc alvo).
5. P1.2 (paralelismo com `max_workers`) + P1.3/P1.4 (section/chunk semanticos).
6. P2 (metricas e schema incremental).

## Risco e trade-off

- Single-pass exige ajuste de contrato entre discovery e pipeline, mas e a maior alavanca de performance.
- "Sem limite de paginas" precisa de guard rails para evitar loops/casos anormais.
- "Sem limite de paginas" sem revisar o teto de profundidade ainda pode manter cobertura incompleta.
- Classificacao nav vs conteudo pode gerar falso positivo no inicio, por isso recomendo logar score e auditar amostras antes de tornar bloqueante.

## Como reproduzir as evidencias rapidamente

Exemplos (PowerShell):

```powershell
$inv = Get-Content 'data\ansys-fluent\raw\inventory.jsonl' | % { $_ | ConvertFrom-Json }
"inventory_count=$($inv.Count)"
$inv | Group-Object source | % { "{0}={1}" -f $_.Name, $_.Count }
"max_depth=$(($inv | Measure-Object depth -Maximum).Maximum)"

$sec = Get-Content 'data\ansys-fluent\processed\sections.jsonl' | % { $_ | ConvertFrom-Json }
"sections_count=$($sec.Count)"
"heading_Document=$(($sec | ? { $_.heading -eq 'Document' }).Count)"
"toc_like_docs=$(($sec | ? { $_.text -match '(?i)collapse\s+all' }).Count)"
```

## Conclusao

Seu diagnostico estava correto:

- ha sobrecarga de scraping por trabalho duplicado;
- ha truncamento de cobertura por `max_pages` e por teto fixo de profundidade (`depth > 2`);
- ha mistura relevante de TOC com conteudo;
- a segmentacao atual nao preserva hierarquia no nivel ideal para RAG de documentacao.

Com as mudancas P0/P1 acima, o pipeline tende a ficar mais rapido, mais limpo e com estrutura bem mais adequada para retrieval por topico/subtopico.
