# Avaliacao Tecnica: Profundidade por Arvore de Topicos

Data: 2026-04-08  
Projeto: `E:/RagProject`

## Objetivo deste parecer

Responder a pergunta: "Como descobrir a profundidade maxima de links/topicos da documentacao sem depender de um numero fixo dado pelo usuario?"

Ponto central: para crawler de documentacao, o alvo deve ser **arvore de topicos (TOC/nav)**, nao grafo de links gerais da pagina.

## Resumo Executivo

Seu raciocinio por camadas esta correto.  
No modelo certo, a descoberta e um BFS na arvore de topicos:

1. seed (camada 0)
2. filhos TOC (camada 1)
3. netos TOC (camada 2)
4. ... ate fila vazia (EOF topologico), ou ate guard rail.

Hoje o sistema ja segue essa base, mas ainda falta um "modo auto" explicito e algumas protecoes para robustez de extracao de TOC.

## Como o sistema faz hoje

## 1) Descoberta por BFS (camadas)

`DiscoveryService.discover()` usa fila (`deque`) com `depth` incremental por aresta pai->filho TOC.  
Cada filho entra com `depth + 1`.  
Isso implementa descoberta em camadas.

## 2) Profundidade atual

A profundidade no inventario e "distancia no grafo de descoberta", nao "nivel visual do HTML".  
`toc_level` existe, mas e metrica separada por pagina/anchor.

## 3) Limites e parada

Hoje a descoberta para por:

- `max_depth` (ou ilimitado se negativo),
- `max_pages` (ou ilimitado se <= 0),
- `max_runtime_minutes`,
- `max_failures`,
- `max_total_bytes`,
- ou fila vazia (`stopped_reason = completed`).

## 4) Escopo orientado a doc

A validacao de URL combina:

- dominio permitido,
- prefixo de caminho efetivo (incluindo `returnurl`),
- include/exclude patterns.

Isso ajuda a manter foco na documentacao alvo.

## 5) Evidencia de comportamento (artefatos existentes)

No corpus `data/ansys-fluent` atual (run legado):

- `inventory_count=300`
- `max_depth=1`
- `source_seed=1`
- `source_toc=299`

Ou seja: houve grande expansao de camada 1, sem chegar em camadas mais profundas naquele run.

## O que esta correto na abordagem atual

1. Modelo de descoberta por camadas (BFS) esta correto para topicos.
2. Profundidade mede relacao pai->filho de descoberta, o que e auditavel.
3. Guard rails ja existem para evitar run infinito.
4. Razoes de skip/rejeicao foram introduzidas e melhoram rastreabilidade.

## Gaps tecnicos relevantes

## 1) Falta "modo auto" explicito de profundidade

Ja existe suporte tecnico a profundidade ilimitada (`max_depth < 0`), mas nao ha semantica de produto clara tipo `--max-depth auto`.

## 2) Robustez da extracao de TOC

Com cache aquecido, `extract_toc_entries()` tende a usar parser por seletor no HTML renderizado.  
Se seletor falhar, pode retornar 0 filhos e reduzir exploracao profunda.

## 3) Ambiguidade de arestas de topico

Nem todo link em nav/sidebar representa "filho topico real".  
Itens como `index`, `prev/next`, `breadcrumbs`, "related links" podem inflar ou distorcer camada.

## 4) Custo redundante em menus repetidos

Documentacoes com sidebar repetida em todas as paginas podem gerar muitas arestas duplicadas na fila (mesmo com dedupe por URL no pop).

## 5) Profundidade descoberta depende do primeiro pai visto

Com dedupe por URL canonica, a URL fica com a profundidade do primeiro caminho encontrado, nao necessariamente do menor caminho global em todos os pais possiveis.

## Parecer tecnico

A base conceitual esta boa e alinhada com o que voce descreveu.  
Nao e "complicado demais" implementar descoberta automatica de profundidade de topicos, desde que o contrato seja:

1. modo auto = explorar BFS de TOC ate fronteira vazia;
2. respeitar guard rails operacionais;
3. relatar se finalizou por "arvore esgotada" ou por guard rail.

## Propostas de melhoria (focadas na abordagem correta)

## P0: Produto/Contrato

1. Introduzir `--max-depth auto` (alias para ilimitado).
2. Expor no relatorio:
   - `max_depth_discovered`
   - `frontier_exhausted` (true/false)
   - `stopped_reason`
3. Diferenciar claramente:
   - `topic_depth` (BFS TOC)
   - `toc_level` (nivel estrutural no bloco nav local)

## P1: Robustez de extracao de topicos

Pipeline de extracao por fallback progressivo:

1. TOC por seletor no HTML renderizado (rapido, preciso quando seletor acerta).
2. Se 0 filhos, tentar extractor DOM completo (com base_url de iframe quando disponivel).
3. Se ainda 0, marcar pagina com `toc_extraction_empty=true` para auditoria.

## P2: Qualidade de aresta (filho topico vs link auxiliar)

Classificar arestas com `edge_type`:

- `topic`
- `navigation_aux` (prev/next/index/breadcrumb)
- `external_or_noise`

E usar somente `topic` para profundidade oficial de topicos.

## P3: Eficiência

1. Hash/fingerprint do bloco TOC por pagina e cache de adjacencia.
2. Se fingerprint igual ao do pai/siblings, reduzir reexpansoes redundantes.
3. Dedupe antecipado no enqueue para encolher fila.

## Algoritmo recomendado (auto-depth por topicos)

```text
queue <- seeds (depth=0)
seen <- {}
max_depth_discovered <- 0

while queue not empty:
  pop node
  if node already seen: continue
  if outside scope: skip(reason)
  fetch node
  children <- extract_topic_children(node)  # nao links gerais
  mark node seen
  max_depth_discovered <- max(max_depth_discovered, node.depth)

  for child in children:
    enqueue(child, depth=node.depth+1)

stop_reason <- "completed" if queue exhausted else "guard_rail_*"
frontier_exhausted <- (stop_reason == "completed")
```

## Metricas recomendadas

Adicionar no report:

- `max_depth_discovered`
- `frontier_exhausted`
- `toc_pages_with_zero_children`
- `topic_edge_count`
- `aux_navigation_edge_count`
- `topic_depth_distribution`
- `toc_extraction_strategy_distribution` (`selector_html`, `dom_runtime`, etc.)

## Criterios de aceitacao

1. Em corpus com arvore conhecida, `max_depth_discovered` bate com valor esperado.
2. Com `--max-depth auto`, run termina por `completed` quando arvore esgota.
3. Em caso de guard rail, `frontier_exhausted=false` e relatorio mostra claramente o bloqueio.
4. Profundidade oficial usa apenas arestas `edge_type=topic`.

## Ordem sugerida de implementacao

1. Formalizar `--max-depth auto` + novos campos de relatorio.
2. Implementar fallback robusto de extracao de TOC.
3. Introduzir classificacao de aresta (`topic` vs `aux`).
4. Otimizar com fingerprint/cache de adjacencia.

## Conclusao

A forma certa e exatamente a que voce descreveu: exploracao em camadas ate "EOF da arvore".  
Para crawler de documentacao, a chave e manter o grafo em torno de **topicos** (TOC), nao links gerais.  
Com as melhorias acima, o sistema ganha profundidade automatica confiavel, mais previsibilidade e menos ruido.

