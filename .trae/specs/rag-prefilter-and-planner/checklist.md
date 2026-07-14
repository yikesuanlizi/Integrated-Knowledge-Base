# RAG 前置过滤与Planner增强 - Verification Checklist

## pytest基线修复
- [ ] pytest.ini配置正确，testpaths=tests
- [ ] pytest --collect-only不收集scripts/smoke_test.py
- [ ] tests/test_nl2sql_contract.py 已修复或xfail标记
- [ ] tests/test_rerank_and_cleanup.py 已修复或xfail标记
- [ ] pytest tests/ 无unexpected failure

## Milvus/Chunks前置过滤
- [ ] _build_search_filters正确合并review gate和applicability_filters
- [ ] 有aircraft_model时filters包含{"status": "approved", "aircraft_model": "..."}
- [ ] 有manual_type时filters包含manual_type
- [ ] 有ata_chapter时filters包含ata_chapter
- [ ] 无applicability_filters时filters只有{"status": "approved"}（向后兼容）
- [ ] 带applicability过滤搜索0结果时降级为只用review gate过滤
- [ ] 降级时结果带filter_fallback=True标记
- [ ] recall_wiki中的Milvus fallback搜索同样支持filter
- [ ] Trace/retrieval_trace记录filters_applied和filter_conditions

## Wiki PG前置过滤
- [ ] list_pg_wiki_cards支持aircraft_model/manual_type/ata_chapter参数
- [ ] 如果wiki_cards表有metadata字段，SQL WHERE中追加条件
- [ ] 如果表无对应字段，在结果后做Python层面过滤
- [ ] 关键词构造时追加机型/手册词提高相关度
- [ ] 带过滤0结果时降级为不带过滤搜索
- [ ] 降级时Trace记录filter_fallback

## Planner规则baseline增强
- [ ] missing_requirements包含"warning"时：chunks通道第一位、rerank=safety_strict、strategy=procedure_evidence_first
- [ ] missing_requirements包含"procedure"时：chunks选中、strategy=procedure_evidence_first
- [ ] missing_requirements包含"parameter"时：chunks + structured_metadata选中
- [ ] applicability_conflict=True时：chunks选中、reason说明适用性冲突
- [ ] 首轮无feedback时baseline行为与之前一致（无回归）
- [ ] baseline返回值包含applicability_conflict、missing_requirements、filter_applicability字段
- [ ] LLM失败时规则调整仍然生效（不依赖LLM）

## Planner LLM prompt增强
- [ ] system_prompt新增规则6（响应missing_requirements）
- [ ] system_prompt新增规则7（响应applicability_conflict）
- [ ] user_prompt展示"缺失的证据类型"区域
- [ ] user_prompt展示"适用性冲突"区域
- [ ] user_prompt展示"指定的过滤条件"区域
- [ ] _sanitize_plan可选支持channel_top_k字段（不强制）
- [ ] prompt表述清晰，LLM容易理解

## ES/Entities过滤
- [ ] ES chunk search（如果被调用）传入applicability filters
- [ ] recall_entities调用ES时传入filters（如果实体索引有metadata字段）
- [ ] recall_structured_metadata不强制加filter
- [ ] recall_dispatch正确传递状态到各通道

## Trace和可解释性
- [ ] 各recall节点add_stage包含filters_applied、filter_conditions、filter_fallback
- [ ] plan_retrieval add_stage包含responded_to_missing、responded_to_applicability_conflict
- [ ] retrieval_trace记录filters_applied、filter_conditions、planner_adjustment

## 测试
- [ ] 新增Milvus filter构建测试（无filter、单filter、多filter）
- [ ] 新增filter 0结果降级测试
- [ ] 新增Planner baseline响应missing_requirements测试
- [ ] 新增Planner baseline响应applicability_conflict测试
- [ ] Mini Golden Set新增场景13-15（前置过滤、Planner调整、冲突rerank）
- [ ] 所有新增测试通过
- [ ] 之前的21个correctness增强测试仍然通过
- [ ] test_query_orchestrator.py所有测试通过
- [ ] Mini Golden Set通过率100%
- [ ] pytest tests/ 全绿（或预期xfail/skip）

## 向后兼容性
- [ ] 没有applicability_filters的旧问题行为不变
- [ ] Planner LLM返回旧格式（无channel_top_k）不报错
- [ ] Milvus/ES无对应metadata字段时不崩溃（优雅降级）
- [ ] 没有missing_requirements时Planner行为与之前一致

## 面试口径注意事项
- [ ] 可以说"召回阶段做机型/ATA/手册类型前置过滤"
- [ ] 不要说"版本/生效日期强过滤"（只做统计和提示）
- [ ] 可以说"Planner会根据上一轮缺失的证据类型动态调整通道和策略"
- [ ] 可以说"过滤0结果时有降级机制，不会因为过滤过严导致0召回"
