# Agentic Knowledge OS

从文档摄入到智能问答的完整 Agentic RAG 系统。

## 特性

- **知识摄入**：支持 PDF / DOCX / TXT / MD，自动分块、实体抽取、元数据推断
- **知识编译**：两阶段 LLM 编译，生成结构化 Wiki 卡片
- **检索引擎**：向量召回 + 全文检索 + BM25 重排 + Wikilink 图扩展
- **Agent 编排**：LangGraph 12 节点 pipeline，三路并行召回 + 证据门控
- **质量治理**：自动审核策略 + Linter + Freshness 检测 + 活动日志
- **互操作**：MCP Server + JSONL/MD 导出导入

## 架构

```
┌─────────────────────────────────────────────┐
│         FastAPI + SSE + MCP                 │
│  /api/ingest  /api/compile  /api/query      │
│  /api/wiki  /api/review  /api/eval          │
│  /api/export  /api/mcp  /api/health         │
├─────────────────────────────────────────────┤
│    LangGraph Agent Pipeline (12 节点)        │
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

## 快速开始

### 1. 启动基础设施

```bash
# 进入项目根目录（即 docker-compose.yml 所在目录）
docker-compose up -d
```

启动 PostgreSQL / Milvus / Elasticsearch / MinIO / etcd 容器。

### 2. 安装 Python 依赖

```bash
pip install -e .
```

### 3. 配置系统环境变量

后端不读取项目 `.env` 文件。环境变量只放密钥，模型名和 API 地址是应用配置，不通过环境变量维护。

PowerShell 当前会话示例：

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
$env:GITEE_API_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

PowerShell 用户级系统环境变量示例：

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "sk-...", "User")
[Environment]::SetEnvironmentVariable("GITEE_API_KEY", "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "User")
```

Docker Compose 启动 backend 时会把这些系统环境变量透传进容器；不要在项目目录里维护 `.env` 文件。

### 4. RAG、OCR 与模型选择

- **Embedding 只需要文本模型**：Milvus 存的是 chunk / Wiki card / 元数据文本向量，不需要视觉语言模型。
- **OCR 是摄入解析能力，不是 embedding 能力**：PDF/DOCX/TXT/MD 的可复制文本直接解析；扫描 PDF、图片手册、截图证据才需要 OCR。
- **主 LLM 保留 DeepSeek 官方接口**：用于编译、问答生成、证据校验，密钥使用 `DEEPSEEK_API_KEY`。
- **Embedding / Rerank / OCR / VL 走 ai.gitee 聚合平台**：统一使用 `GITEE_API_KEY`。
- **不部署本地模型**：Docker Compose 只部署 Postgres / Milvus / ES / MinIO / etcd，不部署 LLM、embedding、rerank 或 VL 模型。
- **需要图片理解或图表理解时**：使用 ai.gitee 的 OCR/VL 模型把图片转成文本证据；向量入库仍然走文本 embedding。

推荐配置：

| 场景 | 变量 | 示例 |
|---|---|---|
| DeepSeek 官方 LLM | API Base | `https://api.deepseek.com` |
| DeepSeek 官方 LLM | 密钥环境变量 | `DEEPSEEK_API_KEY` |
| DeepSeek 官方 LLM | 默认模型 | `deepseek-v4-flash` |
| ai.gitee 聚合平台 | API Base | `https://ai.gitee.com/v1` |
| ai.gitee 聚合平台 | 密钥环境变量 | `GITEE_API_KEY` |
| 文本向量 | 模型 | `Qwen3-Embedding-8B` |
| 文本向量 | 维度 | `1024` |
| Rerank | 模型 | `Qwen3-Reranker-8B` |
| OCR | 模型 | `DeepSeek-OCR-2` |
| VL | 模型 | `MiniMax-M3` |

ai.gitee 请求约定：

- embedding 使用 `/embeddings`，附带 `X-Failover-Enabled: true`，默认 `dimensions=1024`。
- rerank 使用 `/rerank`，附带 `X-Failover-Enabled: true`。
- OCR/VL 使用 `/chat/completions`，消息内容支持 `image_url` + `text`。

### 5. 启动后端

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. 运行冒烟测试

```bash
python scripts/smoke_test.py
```

## API 端点

| 端点 | 方法 | 描述 |
|---|---|---|
| `/api/health/` | GET | 系统健康 |
| `/api/ingest/file` | POST | 上传单个文件 |
| `/api/ingest/path` | POST | 摄入目录 |
| `/api/compile/` | POST | 触发编译 |
| `/api/query/` | POST | 智能问答（同步） |
| `/api/query/stream` | POST | 智能问答（SSE） |
| `/api/wiki/` | GET | 列出卡片 |
| `/api/wiki/{id}` | GET | 卡片详情 |
| `/api/wiki/{id}/markdown` | GET | Markdown 渲染 |
| `/api/review/` | GET | 审核队列 |
| `/api/eval/health` | POST | 健康评估 |
| `/api/eval/citation` | POST | 引用评估 |
| `/api/eval/retrieval` | POST | 检索评估 |
| `/api/eval/evidence` | POST | 证据评估 |
| `/api/export/run` | POST | 导出 |
| `/api/mcp/tools` | GET | MCP 工具列表 |
| `/api/mcp/call` | POST | MCP 工具调用 |

## 目录结构

```
.
├── app/
│   ├── api/                  # REST API 路由
│   ├── clients/              # 外部服务客户端（LLM/ES/Milvus/MinIO）
│   ├── compiler/             # 两阶段 LLM 编译 + Wiki 卡片
│   ├── conf/                 # 配置
│   ├── core/                 # 核心（数据库、日志）
│   ├── eval/                 # 评测层
│   ├── ingest/               # 摄入（parsers/chunking/entities）
│   ├── models/               # ORM + Pydantic
│   ├── quality/              # 质量治理（policy/linter/freshness/log）
│   ├── retrieval/            # 检索（intent/features/repos/ranking）
│   ├── agent/                # LangGraph Agent
│   │   ├── state.py
│   │   ├── graph.py
│   │   └── nodes/            # 12 个节点
│   └── main.py               # FastAPI 入口
├── samples/                  # 示例文档
├── scripts/                  # 脚本（smoke_test 等）
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── README.md
```

## 关键设计

### 两阶段编译

- **Phase 1**：从每个 chunk 提取概念列表（name / type / summary / source_text）
- **Phase 2**：为每个概念生成结构化页面（title / summary / sections / key_facts / warnings / related_concepts）

### LangGraph Agent 12 节点

1. `classify_intent` - 意图分类
2. `extract_query` - 查询扩展
3. `recall_wiki` - 召回 Wiki 卡片
4. `recall_chunks` - 召回原始 chunk
5. `recall_entities` - 实体全文召回
6. `merge_results` - 合并去重
7. `expand_graph` - Wikilink N-hop 扩展
8. `rerank` - 混合重排
9. `build_evidence` - 构造证据包
10. `generate_answer` - LLM 生成答案
11. `validate_evidence` - 证据充分性验证
12. `correct_answer` - 不充分时降级

### 质量治理

- **Review Policy**：自动决定哪些卡片需要 hold（低置信度 / 安全关键词 / 引用缺失）
- **Linter**：规则化检查 + LLM 增强质量评估
- **Freshness**：基于内容哈希 + LLM 检测过时
- **Activity Log**：所有操作的可追溯记录

## License

MIT
