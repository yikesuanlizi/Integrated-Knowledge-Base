from __future__ import annotations

TABLE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS nl2sql_table_info (
        table_name TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        aliases TEXT[] NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nl2sql_column_info (
        column_id TEXT PRIMARY KEY,
        table_name TEXT NOT NULL,
        column_name TEXT NOT NULL,
        data_type TEXT NOT NULL,
        description TEXT NOT NULL,
        aliases TEXT[] NOT NULL DEFAULT '{}',
        sample_values TEXT[] NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nl2sql_metric_info (
        metric_id TEXT PRIMARY KEY,
        metric_name TEXT NOT NULL,
        description TEXT NOT NULL,
        expression TEXT NOT NULL,
        dependencies TEXT[] NOT NULL DEFAULT '{}',
        aliases TEXT[] NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nl2sql_value_info (
        value_id TEXT PRIMARY KEY,
        value_text TEXT NOT NULL,
        value_type TEXT NOT NULL,
        table_name TEXT NOT NULL,
        column_name TEXT NOT NULL,
        aliases TEXT[] NOT NULL DEFAULT '{}'
    )
    """,
]


TABLE_METADATA = [
    ("documents", "知识库文档元数据表，记录来源文件、导入状态、hash 和解析摘要。", ["文档", "资料", "来源文件", "手册"]),
    ("rag_chunks", "原始文档切块索引，保留 chunk 内容、来源、页码、章节路径和审核状态。", ["切块", "原文片段", "证据片段", "chunks"]),
    ("wiki_cards", "LLM 编译后的结构化 Wiki 卡片，包含卡片类型、标题、事实、来源和审核状态。", ["卡片", "wiki", "结构化知识", "知识卡片"]),
    ("wiki_claims", "Wiki 卡片中的原子事实和引用映射，用于证据门控与引用覆盖率评估。", ["事实", "claim", "引用", "证据"]),
    ("entities", "从文档和卡片中抽取的领域实体、别名、类型和值域。", ["实体", "别名", "部件", "ATA"]),
    ("review_items", "人工审核队列，记录待审、通过、驳回及同步到索引的状态。", ["审核", "队列", "review"]),
    ("activity_log", "摄入、编译、问答、审核和评测的操作日志。", ["日志", "操作记录", "审计"]),
]


COLUMN_METADATA = [
    ("documents.doc_id", "documents", "doc_id", "text", "知识库文档唯一标识。", ["文档ID", "资料ID"], []),
    ("documents.source_file", "documents", "source_file", "text", "文档来源文件路径或上传文件名。", ["文件", "来源", "source"], ["C909飞机用于机场计划的飞机特性手册（ACAP）.pdf"]),
    ("documents.content_hash", "documents", "content_hash", "text", "文档内容 hash，用于增量编译和新鲜度检查。", ["hash", "指纹", "增量"], []),
    ("rag_chunks.chunk_id", "rag_chunks", "chunk_id", "text", "原始文档切块唯一标识。", ["chunk", "片段ID"], []),
    ("rag_chunks.content", "rag_chunks", "content", "text", "原始文档切块正文，向量召回和引用回答的基础证据。", ["原文", "正文", "片段内容"], ["起落架轮迹", "道面等级号"]),
    ("rag_chunks.section_path", "rag_chunks", "section_path", "text", "文档章节路径，用于定位手册章节和构建引用。", ["章节", "目录", "section"], ["飞机特性手册/机场计划/道面"]),
    ("rag_chunks.status", "rag_chunks", "status", "text", "切块审核状态，严格审核模式下只有 approved 可进入问答。", ["审核状态", "状态"], ["approved", "review", "rejected"]),
    ("wiki_cards.card_id", "wiki_cards", "card_id", "text", "结构化 Wiki 卡片唯一标识。", ["卡片ID", "wiki ID"], []),
    ("wiki_cards.card_type", "wiki_cards", "card_type", "text", "Wiki 卡片类型，如 task、component、document、warning。", ["卡片类型", "类型"], ["task", "component", "document", "warning"]),
    ("wiki_cards.title", "wiki_cards", "title", "text", "Wiki 卡片标题，通常对应部件、任务或章节。", ["标题", "知识点"], ["起落架轮迹", "登机门", "平尾后部离地高度"]),
    ("wiki_cards.content", "wiki_cards", "content", "text", "结构化卡片正文，由编译流程从原文证据生成。", ["卡片内容", "结构化内容"], []),
    ("wiki_cards.status", "wiki_cards", "status", "text", "卡片审核状态，召回默认只使用 approved。", ["审核状态", "状态"], ["approved", "review", "rejected"]),
    ("wiki_cards.linked_chunks", "wiki_cards", "linked_chunks", "jsonb", "卡片关联的原文 chunk 列表，用于审核状态反写和证据追踪。", ["关联切块", "来源片段"], []),
    ("wiki_claims.claim_text", "wiki_claims", "claim_text", "text", "从卡片中抽取的可验证事实文本。", ["事实", "声明", "claim"], []),
    ("wiki_claims.source_refs", "wiki_claims", "source_refs", "jsonb", "支撑事实的来源引用列表。", ["引用", "来源", "证据"], []),
    ("entities.entity_text", "entities", "entity_text", "text", "领域实体原文，如部件名、ATA 章节、工具或警告词。", ["实体", "部件", "术语"], ["起落架轮迹", "道面等级号", "登机门"]),
    ("entities.entity_type", "entities", "entity_type", "text", "实体类型，如 component、system、ata、tool、warning。", ["实体类型", "类型"], ["component", "system", "ata"]),
    ("review_items.status", "review_items", "status", "text", "审核队列状态。", ["审核", "通过", "驳回"], ["pending", "approved", "rejected"]),
]


METRIC_METADATA = [
    ("approved_card_count", "审核通过卡片数", "可进入 Wiki 召回的 approved 卡片数量。", "COUNT(*) FILTER (WHERE status = 'approved') FROM wiki_cards", ["wiki_cards.status"], ["通过卡片", "可用卡片"]),
    ("pending_card_count", "待审核卡片数", "仍处于 review 状态、不能进入严格问答证据的卡片数量。", "COUNT(*) FILTER (WHERE status = 'review') FROM wiki_cards", ["wiki_cards.status"], ["待审卡片", "审核队列"]),
    ("approved_chunk_count", "审核通过切块数", "可进入原文切块召回的 approved chunk 数量。", "COUNT(*) FILTER (WHERE status = 'approved') FROM rag_chunks", ["rag_chunks.status"], ["可用切块", "原文证据"]),
    ("citation_coverage", "引用覆盖率", "回答或卡片中的 claim 被来源引用支撑的比例。", "supported_claims / NULLIF(total_claims, 0)", ["wiki_claims.source_refs"], ["引用率", "证据覆盖"]),
    ("retrieval_precision", "检索精度", "评测集中命中的有效证据占召回证据的比例。", "relevant_hits / NULLIF(total_hits, 0)", ["rag_chunks.chunk_id", "wiki_cards.card_id"], ["命中率", "召回质量"]),
    ("freshness_stale_count", "过期知识项数量", "source hash 变化后尚未 refresh 的文档、chunk 或卡片数量。", "COUNT(*) FILTER (WHERE freshness = 'stale')", ["documents.content_hash"], ["过期", "新鲜度"]),
]


VALUE_METADATA = [
    ("status:approved", "approved", "review_status", "wiki_cards", "status", ["审核通过", "可回答", "可召回"]),
    ("status:review", "review", "review_status", "wiki_cards", "status", ["待审核", "不可进入严格问答"]),
    ("status:rejected", "rejected", "review_status", "wiki_cards", "status", ["驳回", "禁用"]),
    ("chunk_status:approved", "approved", "review_status", "rag_chunks", "status", ["切块通过", "原文可用"]),
    ("chunk_status:review", "review", "review_status", "rag_chunks", "status", ["切块待审", "原文待审核"]),
    ("card_type:task", "task", "card_type", "wiki_cards", "card_type", ["步骤", "任务", "操作流程"]),
    ("card_type:component", "component", "card_type", "wiki_cards", "card_type", ["部件", "组件", "功能"]),
    ("card_type:document", "document", "card_type", "wiki_cards", "card_type", ["文档", "资料"]),
    ("card_type:warning", "warning", "card_type", "wiki_cards", "card_type", ["安全警告", "注意事项"]),
    ("domain:起落架轮迹", "起落架轮迹", "domain_entity", "entities", "entity_text", ["Landing Gear Wheel Track", "道面适应性"]),
    ("domain:道面等级号", "道面等级号", "domain_entity", "entities", "entity_text", ["PCN", "道面承载能力"]),
    ("domain:飞机等级号", "飞机等级号", "domain_entity", "entities", "entity_text", ["ACN", "机场计划"]),
    ("domain:登机门", "登机门", "domain_entity", "entities", "entity_text", ["I型登机门", "舱门"]),
    ("intent:procedure", "procedure", "query_intent", "activity_log", "metadata", ["步骤", "检查", "操作"]),
    ("intent:safety", "safety", "query_intent", "activity_log", "metadata", ["警告", "危险", "注意"]),
]
