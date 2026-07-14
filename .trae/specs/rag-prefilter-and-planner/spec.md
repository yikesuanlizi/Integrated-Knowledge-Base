# RAG 前置过滤与Planner增强 - Product Requirement Document

## Overview
- **Summary**: 在P0正确性增强（answer_requirements、evidence_roles、覆盖率检查、适用性识别、历史边界）完成后，将后验正确性治理升级为前置控制：1) 把applicability_filters下推到Milvus/ES/Wiki/PG召回层做metadata prefilter；2) 让Retrieval Planner感知missing_requirements和适用性冲突，在第二轮及以后动态调整通道/top_k/策略；3) 修复pytest全量测试基线（排除scripts误收集、修复或标记旧失败）。
- **Purpose**: 从"召回后才发现跨机型/缺证据"升级为"召回时就过滤，Planner根据反馈动态调整策略"，真正实现Agentic检索闭环。解决航空维修场景最核心的风险——跨机型错答。
- **Target Users**: 面试展示（体现工业化深度）、问答用户（准确性提升）。

## Goals
1. **召回前置过滤**：applicability_filters（aircraft_model、manual_type、ata_chapter）传递到各召回通道，Milvus/ES查询时加上metadata filter，Wiki卡片查询也做关键词过滤
2. **Planner闭环增强**：第二轮及以后，Planer看到planner_feedback中的missing_requirements和applicability_conflict，主动调整通道选择、top_k、rerank_profile和策略
3. **测试基线全绿**：pytest正确配置只收集tests/目录，修复或跳过已知旧失败，确保全量测试可稳定通过
4. **Trace可解释**：记录filter是否应用、过滤条件是什么、Planner是否基于反馈调整

## Non-Goals (Out of Scope)
- ES/ Milvus的expr/filter语法复杂优化（先支持简单等值过滤）
- 版本（revision/effective_date）强过滤——只做统计和提示，不做前置过滤
- 混合意图分类（规则+LLM）升级
- Chunk质量评分进入rerank
- 表格/步骤/警告结构化特殊处理
- Claim-level citation
- 多存储一致性/outbox模式
- 完整Golden Set扩展（当前Mini Golden Set 12题足够）

## Background & Context
已完成的P0正确性增强：
- extract_query抽取answer_requirements（procedure/warning/parameter/applicability/tooling）和applicability_filters（aircraft_model/manual_type/ata_chapter）
- build_evidence标记evidence_roles，统计applicability_stats
- validate_evidence检查覆盖率和机型冲突，写入missing_requirements和applicability_conflict到planner_feedback
- correct_answer改写query时追加缺失关键词和机型词
- generate_answer prompt强制标注适用范围和冲突提示
- 历史边界Prompt强化，history_as_evidence=False
- 21个单元测试+12个Mini Golden Set场景全部通过

当前不足：
- applicability_filters只在validate_evidence做后验检查，没有在召回时过滤
- Milvus已有_review_filters()（status=approved），但没有机型/ATA/手册类型过滤
- Wiki PG查询list_pg_wiki_cards只支持keyword和status，不支持机型/手册类型过滤
- Planner只看intent/query_features/entities，不看planner_feedback里的missing_requirements和applicability_conflict
- 第二轮Planner仍基于baseline，没有根据第一轮不足动态调整
- pytest配置缺失，scripts/smoke_test.py被误收集，有2个旧失败

## Functional Requirements
- **FR-1**: 构建统一的applicability metadata filter，合并review gate和applicability_filters
- **FR-2**: recall_chunks（Milvus）查询时传入包含机型/手册类型/ATA的filter expr
- **FR-3**: recall_wiki（PG）查询时，在关键词中追加机型/手册/ATA信息，或在结果上做metadata过滤
- **FR-4**: recall_entities查询时，同样支持applicability过滤
- **FR-5**: recall_structured_metadata在适用时也带上applicability filter
- **FR-6**: plan_retrieval在prompt中明确传入missing_requirements、applicability_conflict、applicability_filters信息
- **FR-7**: Planner输出增加channel_top_k配置（可选），允许不同通道设置不同top_k（如缺warning时chunks top_k增大）
- **FR-8**: 当applicability_conflict=True时，Planner必须强制启用chunks通道，并带上机型过滤策略
- **FR-9**: 当missing_requirements包含warning时，Planner提高chunks通道优先级/top_k，rerank_profile设为safety_strict
- **FR-10**: 检索Trace中记录filters_applied、filter_conditions、planner_adjustment信息
- **FR-11**: pytest配置（pytest.ini或pyproject.toml）只收集tests/目录，排除scripts/
- **FR-12**: 修复或标记（xfail/skip）2个旧失败测试，确保pytest tests/全绿

## Non-Functional Requirements
- **NFR-1**: 没有applicability_filters时，保持原有行为（向后兼容）
- **NFR-2**: 过滤条件导致0结果时，允许降级为不带过滤的召回，但Trace必须记录filter_fallback=True
- **NFR-3**: LLM Planner失败时，规则baseline必须同样能基于missing_requirements调整
- **NFR-4**: 所有改动不破坏现有测试

## Constraints
- **Technical**: Python 3.11+，现有MilvusRepository的search接口需要确认filter expr格式；Wiki PG用mybatis plus/service，尽量在service层用basemapper方法过滤
- **Business**: 不做大重构，改动量可控
- **Dependencies**: 复用现有llm_client、MilvusRepository、wiki_pg_service

## Assumptions
- Milvus collection的schema包含aircraft_model、manual_type、ata_chapter字段（从摄入代码看_ingest_service.py写入Milvus时有这些字段）
- Wiki卡片在PG中存储了对应的metadata字段（aircraft_model、manual_type、ata_chapter）
- ES/Entity索引的filter实现如果较复杂，第一版可以只做Milvus+Wiki+PG的过滤，ES/Entity做简单后过滤或暂不做强过滤
- 第一版filter只做精确匹配，不做范围/模糊匹配

## Acceptance Criteria

### AC-1: Milvus查询带机型过滤
- **Given**: 用户问"A320液压泵拆卸步骤"，applicability_filters.aircraft_model="A320"
- **When**: recall_chunks执行
- **Then**: Milvus search调用时filters包含{"status": "approved", "aircraft_model": "A320"}；Trace记录filters_applied=True
- **Verification**: `programmatic`

### AC-2: 无过滤条件时保持原行为
- **Given**: 用户问"什么是液压泵"，无applicability_filters
- **When**: recall_chunks执行
- **Then**: Milvus filters只有{"status": "approved"}，与改动前行为一致
- **Verification**: `programmatic`

### AC-3: 过滤0结果时降级
- **Given**: 指定机型过滤后Milvus返回0结果
- **When**: recall_chunks执行
- **Then**: 降级为不带applicability的过滤重新查询，返回结果；Trace记录filter_fallback=True
- **Verification**: `programmatic`

### AC-4: Planner看到missing_requirements
- **Given**: 第二轮迭代，planner_feedback.missing_requirements=["warning"]
- **When**: plan_retrieval执行
- **Then**: Planner prompt中包含缺失证据类型信息；输出plan中chunks通道被选中，rerank_profile可能调整为safety_strict
- **Verification**: `programmatic` + `human-judgment`

### AC-5: Planner规则baseline也能响应missing_requirements
- **Given**: LLM调用失败，使用baseline plan；missing_requirements=["warning"]
- **When**: plan_retrieval执行
- **Then**: baseline自动选择chunks通道，rerank_profile设为safety_strict（规则调整，不依赖LLM）
- **Verification**: `programmatic`

### AC-6: Planner感知适用性冲突
- **Given**: applicability_conflict=True，applicability_filters.aircraft_model="A320"
- **When**: plan_retrieval执行（第二轮）
- **Then**: Planner prompt包含冲突信息；输出plan强制带上机型过滤策略，chunks通道优先
- **Verification**: `programmatic` + `human-judgment`

### AC-7: pytest配置正确
- **Given**: pytest配置更新
- **When**: 运行pytest --collect-only
- **Then**: 只收集tests/目录下的测试文件，不收集scripts/smoke_test.py
- **Verification**: `programmatic`

### AC-8: 全量pytest通过
- **Given**: 修复或标记旧失败
- **When**: 运行pytest tests/
- **Then**: 所有测试通过（或预期xfail/skip），无unexpected failure
- **Verification**: `programmatic`

### AC-9: 现有功能无回归
- **Given**: 所有改动完成
- **When**: 运行pytest tests/test_correctness_enhancements.py tests/test_query_orchestrator.py tests/test_context_builder.py
- **Then**: 所有之前通过的测试仍然通过
- **Verification**: `programmatic`

### AC-10: Wiki PG查询支持机型过滤
- **Given**: applicability_filters.aircraft_model="A320"
- **When**: recall_wiki执行
- **Then**: Wiki查询结果中只包含（或优先包含）A320相关卡片；或在结果后做metadata过滤
- **Verification**: `programmatic`

## Open Questions
- [ ] MilvusRepository.search的filters参数具体支持什么格式？需要看MilvusRepository代码确认（是dict还是expr string）
- [ ] Wiki卡片表是否有aircraft_model/manual_type/ata_chapter字段？需要查PG schema确认
- [ ] recall_entities和ES索引的过滤是否在第一版实现，还是只做Milvus+Wiki？
