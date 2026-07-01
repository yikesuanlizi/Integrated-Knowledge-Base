# Agentic Knowledge OS

A full-stack Agentic RAG system — from document ingestion to intelligent Q&A.

## Features

- **Knowledge Ingestion**: Supports PDF / DOCX / TXT / MD with automatic chunking, entity extraction, and metadata inference
- **Knowledge Compilation**: Two-phase LLM compilation pipeline that generates structured Wiki cards
- **Retrieval Engine**: Vector recall + full-text search + BM25 reranking + Wikilink graph expansion
- **Agent Orchestration**: LangGraph 12-node pipeline with parallel multi-channel recall + evidence gating
- **Quality Governance**: Automated review policy + Linter + Freshness detection + activity logging
- **Interoperability**: MCP Server + JSONL/MD export & import

## Architecture

```
┌─────────────────────────────────────────────┐
│         FastAPI + SSE + MCP                 │
│  /api/ingest  /api/compile  /api/query      │
│  /api/wiki  /api/review  /api/eval          │
│  /api/export  /api/mcp  /api/health         │
├─────────────────────────────────────────────┤
│    LangGraph Agent Pipeline (12 nodes)       │
│  classify_intent → extract_query →          │
│  [recall_wiki ∥ recall_chunks ∥            │
│   recall_entities] → merge → expand_graph   │
│  → rerank → build_evidence →                │
│  generate_answer → validate_evidence →      │
│  correct_answer                            │
├─────────────────────────────────────────────┤
│   Retrieval: Milvus + ES + BM25 + Graph     │
├─────────────────────────────────────────────┤
│   Two-Phase LLM Compile + Wiki Cards        │
├─────────────────────────────────────────────┤
│   Ingestion: Docling + Chunking + Entities  │
└─────────────────────────────────────────────┘
```

## Quick Start

### 1. Start Infrastructure

```bash
docker-compose up -d
```

Starts PostgreSQL / Milvus / Elasticsearch / MinIO / etcd containers.

### 2. Install Python Dependencies

```bash
pip install -e .
```

### 3. Configure Environment Variables

The backend does not read a project `.env` file. Environment variables are only for API keys — model names and API endpoints are application configuration, not managed via env vars.

PowerShell (current session):

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
$env:GITEE_API_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

PowerShell (user-level persistent):

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "sk-...", "User")
[Environment]::SetEnvironmentVariable("GITEE_API_KEY", "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "User")
```

Docker Compose passes these system environment variables into the backend container. Do not maintain a `.env` file in the project directory.

### 4. RAG, OCR & Model Selection

- **Embedding requires only a text model**: Milvus stores text vectors for chunks / Wiki cards / metadata — no vision-language model needed.
- **OCR is an ingestion parsing capability, not an embedding capability**: Copyable text from PDF/DOCX/TXT/MD is parsed directly; scanned PDFs, image manuals, and screenshot evidence require OCR.
- **Main LLM uses the DeepSeek official API**: Used for compilation, answer generation, and evidence validation. Key: `DEEPSEEK_API_KEY`.
- **Embedding / Rerank / OCR / VL via ai.gitee platform**: Unified under `GITEE_API_KEY`.
- **No local models deployed**: Docker Compose only deploys Postgres / Milvus / ES / MinIO / etcd — no LLM, embedding, rerank, or VL models.
- **When image/chart understanding is needed**: Use ai.gitee's OCR/VL models to convert images to text evidence; vector ingestion still uses text embedding.

Recommended configuration:

| Component | Variable | Example |
|---|---|---|
| DeepSeek LLM | API Base | `https://api.deepseek.com` |
| DeepSeek LLM | Key env var | `DEEPSEEK_API_KEY` |
| DeepSeek LLM | Default model | `deepseek-v4-flash` |
| ai.gitee platform | API Base | `https://ai.gitee.com/v1` |
| ai.gitee platform | Key env var | `GITEE_API_KEY` |
| Text embedding | Model | `Qwen3-Embedding-8B` |
| Text embedding | Dimensions | `1024` |
| Rerank | Model | `Qwen3-Reranker-8B` |
| OCR | Model | `DeepSeek-OCR-2` |
| VL | Model | `MiniMax-M3` |

ai.gitee API conventions:

- Embedding: `/embeddings` with `X-Failover-Enabled: true`, default `dimensions=1024`.
- Rerank: `/rerank` with `X-Failover-Enabled: true`.
- OCR/VL: `/chat/completions`, message content supports `image_url` + `text`.

### 5. Start Backend

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Run Smoke Test

```bash
python scripts/smoke_test.py
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/health/` | GET | System health |
| `/api/ingest/file` | POST | Upload single file |
| `/api/ingest/path` | POST | Ingest directory |
| `/api/compile/` | POST | Trigger compilation |
| `/api/query/` | POST | Q&A (synchronous) |
| `/api/query/stream` | POST | Q&A (SSE streaming) |
| `/api/wiki/` | GET | List cards |
| `/api/wiki/{id}` | GET | Card detail |
| `/api/wiki/{id}/markdown` | GET | Markdown render |
| `/api/review/` | GET | Review queue |
| `/api/eval/health` | POST | Health evaluation |
| `/api/eval/citation` | POST | Citation evaluation |
| `/api/eval/retrieval` | POST | Retrieval evaluation |
| `/api/eval/evidence` | POST | Evidence evaluation |
| `/api/export/run` | POST | Export |
| `/api/mcp/tools` | GET | MCP tool list |
| `/api/mcp/call` | POST | MCP tool invocation |

## Directory Structure

```
├── app/
│   ├── api/                  # REST API routes
│   ├── clients/              # External service clients (LLM/ES/Milvus/MinIO)
│   ├── compiler/             # Two-phase LLM compilation + Wiki cards
│   ├── conf/                 # Configuration
│   ├── core/                 # Core (database, logging)
│   ├── eval/                 # Evaluation layer
│   ├── ingest/               # Ingestion (parsers/chunking/entities)
│   ├── models/               # ORM + Pydantic
│   ├── quality/              # Quality governance (policy/linter/freshness/log)
│   ├── retrieval/            # Retrieval (intent/features/repos/ranking)
│   ├── agent/                # LangGraph Agent
│   │   ├── state.py
│   │   ├── graph.py
│   │   └── nodes/            # 12 nodes
│   └── main.py               # FastAPI entry
├── frontend/                 # Vue 3 + Tailwind CSS
├── samples/                  # Sample documents
├── scripts/                  # Scripts (smoke_test, etc.)
├── tests/                    # Test suite
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── README.md
```

## Key Design

### Two-Phase Compilation

- **Phase 1**: Extract concept lists from each chunk (name / type / summary / source_text)
- **Phase 2**: Generate structured pages for each concept (title / summary / sections / key_facts / warnings / related_concepts)

### LangGraph Agent 12 Nodes

1. `classify_intent` - Intent classification
2. `extract_query` - Query expansion
3. `recall_wiki` - Wiki card recall
4. `recall_chunks` - Raw chunk recall
5. `recall_entities` - Entity full-text recall
6. `merge_results` - Merge & deduplicate
7. `expand_graph` - Wikilink N-hop expansion
8. `rerank` - Hybrid reranking
9. `build_evidence` - Evidence package construction
10. `generate_answer` - LLM answer generation
11. `validate_evidence` - Evidence sufficiency validation
12. `correct_answer` - Fallback when insufficient

### Quality Governance

- **Review Policy**: Automatically determines which cards need to be held (low confidence / safety keywords / missing references)
- **Linter**: Rule-based checks + LLM-enhanced quality assessment
- **Freshness**: Content hash + LLM-based staleness detection
- **Activity Log**: Traceable records for all operations

## License

MIT
