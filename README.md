# RAG Project

Projeto base para construir um storage vetorial de documentação técnica a partir de uma URL raiz. O sistema automatiza a descoberta, extração, estruturação e indexação de corpora de documentação para uso em aplicações de RAG (Retrieval-Augmented Generation).

A interface principal do sistema é direta e CLI-first:

```bash
# Constrói o storage (Crawl + Embeddings + Index)
python scripts/build_vector_store.py --root-url "https://docs.python.org/3.11/"

# Consulta a coleção gerada
python scripts/query_rag.py --collection python-docs-3-11 --query "how do I create a virtual environment?"
```

## O que o Sistema Entrega

- **Descoberta Inteligente**: Navega por Sitemaps e Table of Contents (TOC) para identificar a estrutura da documentação.
- **Extração Robusta**: Usa `trafilatura` e `BeautifulSoup` para extrair apenas o conteúdo principal, removendo ruídos (nav, footer, ads).
- **Hierarquia Preservada**: Mapeia a árvore de navegação original (`DiscoveredNode`), permitindo saber a posição exata de cada chunk na documentação.
- **Busca Híbrida**: Combina busca textual (FTS) e vetorial (`pgvector`) usando **Reciprocal Rank Fusion (RRF)**.
- **Modos de Execução**: Suporta execução visual ou `headless` (via Selenium), além de permitir o processamento apenas para o sistema de arquivos (`--filesystem-only`).

---

## Interface Principal

### 1. Construir o Storage Vetorial

O script principal é o `scripts/build_vector_store.py`.

```bash
python scripts/build_vector_store.py --root-url "https://docs.python.org/3.11/"
```

**Argumentos Principais:**

- `--root-url` (Obrigatório): Ponto inicial da documentação.
- `--collection`: Nome lógico da coleção. Se omitido, o sistema gera um slug baseado na URL (ex: `docs-python-org-3-11`).
- `--max-pages`: Limite de páginas a processar (default: 300).
- `--max-depth`: Profundidade máxima de expansão de links de TOC (default: 2, negativo = ilimitado).
- `--max-runtime-minutes`: Guard rail de tempo para interromper descoberta (0 desativa).
- `--max-failures`: Guard rail de falhas acumuladas de fetch/TOC (0 desativa).
- `--max-total-bytes`: Guard rail de volume total de HTML coletado (0 desativa).
- `--max-workers`: Número de workers para processamento paralelo de páginas.
- `--include-pattern` / `--exclude-pattern`: Ajustes explícitos de escopo de URL (aceitação/rejeição).
- `--headless`: Executa o browser em modo invisível (default: False).
- `--device`: Força o device de embeddings (`auto`, `cpu` ou `cuda`).
- `--db-dsn`: String de conexão PostgreSQL (sobrescreve o default).
- `--filesystem-only`: Gera artefatos locais em `data/` sem exigir banco de dados ou gerar embeddings.
- `--index-navigation-pages`: Indexa páginas classificadas como navegação (por padrão elas são mantidas fora do índice de retrieval).

**Feedback e Verbosidade:**

- `--no-progress`: Desativa as barras de progresso (tqdm).
- `--quiet`: Mostra apenas avisos e erros.
- `--no-debug`: Desativa logs de estágio, mantendo a saída limpa.

### 2. Consultar uma Coleção

O script `scripts/query_rag.py` realiza a busca híbrida.

```bash
python scripts/query_rag.py --collection python-docs-3-11 --query "como criar venv?" --top-k 5
```

**Argumentos Principais:**

- `--query` (Obrigatório): Texto da pergunta/busca.
- `--collection` (Obrigatório): Nome da coleção no banco.
- `--top-k`: Quantidade de resultados finais após o RRF (default: 8).
- `--preview-chars`: Quantidade de caracteres de texto a exibir por resultado (default: 600).
- `--verbose`: Exibe metadados técnicos (IDs, níveis de TOC, ordem de navegação).

---

## Estrutura do Banco de Dados

O sistema utiliza **PostgreSQL 16+** com a extensão `pgvector`. O schema é multitenant por `collection_name`:

- `discovered_nodes`: Estrutura da árvore de navegação (TOC).
- `raw_documents`: Conteúdo HTML e Markdown original.
- `sections`: Divisões lógicas por headings (h1-h6).
- `chunks`: Fragmentos de texto com embeddings (384 dimensões por padrão) e `tsvector` para busca textual.
- `retrieval_traces`: Registro de auditoria de todas as buscas realizadas.

---

## Artefatos Locais (`data/`)

Mesmo indexando no banco, o sistema gera artefatos em `data/<collection>/` para auditoria:

- `raw/inventory.jsonl`: Lista de URLs descobertas.
- `raw/skipped_urls.jsonl`: URLs rejeitadas/não processadas com motivo objetivo (`outside_scope`, `duplicate`, `guard_rail_*`, etc.).
- `raw/discovered_nodes.jsonl`: Árvore de navegação extraída.
- `raw/documents.jsonl`: Conteúdo bruto extraído.
- `processed/sections.jsonl` e `chunks.jsonl`: Dados estruturados (incluindo metadados hierárquicos e offsets de chunk).
- `processed/discovery_report.json`: Resumo operacional da descoberta (motivo de parada, bytes, falhas, limites).
- `processed/coverage_report.json`: Cobertura por descoberta/conteúdo/indexação + distribuição por profundidade/origem.

---

## Ambiente e Instalação

Recomendado: **Python 3.11**.

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure o PostgreSQL com a extensão `vector`:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. (Opcional) Configure a variável de ambiente `RAG_DATABASE_DSN` ou use o default:
   `postgresql://postgres:postgres@localhost:5432/rag_project`

---

## Utilitários Internos

Para depuração ou manutenção, os scripts de baixo nível continuam disponíveis:

- `scripts/init_db.py`: Reinicializa o schema do banco.
- `scripts/crawl_docs.py`: Executa apenas a etapa de descoberta e fetch.
- `scripts/index_corpus.py`: Indexa arquivos locais já existentes no banco.
- `scripts/run_eval.py`: Roda bateria de testes de retrieval.

---

## Observações Técnicas

- **Embedding Model**: Default para `sentence-transformers/all-MiniLM-L6-v2`.
- **Ansys Integration**: O sistema possui lógica especial para lidar com URLs protegidas ou com parâmetros de redirecionamento comuns em documentações técnicas complexas.
- **RRF**: A fusão de resultados prioriza documentos que aparecem bem rankeados tanto na busca semântica quanto na textual.
