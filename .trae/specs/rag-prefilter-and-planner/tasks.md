# RAG 前置过滤与Planner增强 - The Implementation Plan

## [x] Task 1: 修复pytest配置与基线
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 在项目根目录创建pytest.ini（或检查是否已有pyproject.toml配置），设置testpaths=tests，确保scripts/目录下的文件不被收集
  - 检查tests/test_nl2sql_contract.py和tests/test_rerank_and_cleanup.py的失败原因：
    - 如果是简单可修复的bug，修复
    - 如果是预期的过期测试（如与已修改功能不匹配），用pytest.mark.xfail标记并说明原因
    - 如果是环境依赖问题，用pytest.mark.skip标记
  - 确保pytest tests/运行时无unexpected failure
- **Acceptance Criteria Addressed**: AC-7, AC-8
- **Test Requirements**:
  - `programmatic` TR-1.1: pytest --collect-only只收集tests/目录下文件
  - `programmatic` TR-1.2: pytest tests/ 所有测试通过（允许预期xfail/skip）
  - `programmatic` TR-1.3: pytest tests/test_correctness_enhancements.py 全部通过
- **Notes**: 先做这个，后续开发有稳定测试基线

## [x] Task 2: 构建统一的applicability filter并接入recall_chunks
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 在recall_chunks.py中新增_build_search_filters(state)函数：
    - 基础filter来自_review_filters()（status=approved）
    - 如果state.applicability_filters.aircraft_model非空，添加aircraft_model字段到filters
    - 如果state.applicability_filters.manual_type非空，添加manual_type字段到filters
    - 如果state.applicability_filters.ata_chapter非空，添加ata_chapter字段到filters
  - 修改_run和_run_async：
    - 先用带applicability的filters搜索
    - 如果返回0结果，降级为只用_review_filters()搜索（去掉applicability过滤），在结果里加_filter_fallback=True标记
    - 返回结果时附带metadata：filters_applied、filter_conditions、filter_fallback
  - Trace中记录filters_applied和filter_conditions
  - 同步修改recall_wiki.py中的Milvus fallback搜索（_fallback_chunk_results）
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-2.1: 有aircraft_model时Milvus filters包含aircraft_model
  - `programmatic` TR-2.2: 无applicability_filters时filters只有status=approved
  - `programmatic` TR-2.3: 带过滤搜索0结果时降级为不带applicability的搜索
  - `programmatic` TR-2.4: 运行pytest tests/ 无回归
- **Notes**: Milvus的_build_filter_expr已支持string等值过滤，直接传dict即可

## [x] Task 3: recall_wiki支持applicability过滤
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 修改list_pg_wiki_cards（wiki_pg_service.py）函数，增加可选参数：aircraft_model=None, manual_type=None, ata_chapter=None
  - 在SQL WHERE子句中追加对应条件（如果参数非空）：
    - aircraft_model: 可以用ILIKE或精确匹配，看wiki_cards表实际字段名（先DESC表确认字段）
    - manual_type、ata_chapter同理
  - 如果表中没有这些metadata字段，则在查询结果后做Python层面过滤（遍历结果，检查metadata中是否包含对应值）
  - 修改recall_wiki.py的_run_recall_wiki和_run_recall_wiki_async：
    - 调用_search_pg_cards时传入applicability_filters
    - 如果带过滤0结果，降级为不带过滤搜索（关键词追加机型/手册/ATA词）
  - 在关键词构造时（_wiki_query_candidates），如果有applicability_filters，可以在关键词后追加机型/手册词提高相关度
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-3.1: 有aircraft_model时Wiki查询带过滤条件
  - `programmatic` TR-3.2: 过滤0结果时降级查询
  - `programmatic` TR-3.3: 运行pytest tests/ 无回归
- **Notes**: 如果wiki_cards表确实没有metadata字段，先在结果后过滤，后续再补字段；不要改表结构，第一版用关键词增强+后过滤也可以

## [x] Task 4: Planner规则baseline感知missing_requirements和applicability
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 修改plan_retrieval.py的_build_baseline_plan函数：
    - 读取state.planner_feedback中的missing_requirements和applicability_conflict
    - 规则调整baseline：
      - 如果missing_requirements包含"warning"或state.applicability_conflict：
        - 确保"chunks"在selected_channels中且放第一位
        - rerank_profile设为"safety_strict"
        - strategy设为"procedure_evidence_first"
      - 如果missing_requirements包含"procedure"：
        - 确保"chunks"在selected_channels中
        - strategy设为"procedure_evidence_first"
      - 如果missing_requirements包含"parameter"：
        - 选中"chunks"和"structured_metadata"
      - 如果state.applicability_conflict为True：
        - 确保"chunks"被选中
        - 在reason中说明"适用性冲突，优先原文证据"
    - 返回的baseline中加入：
      - "applicability_conflict": state.applicability_conflict
      - "missing_requirements": list(missing_requirements)
      - "filter_applicability": bool(state.applicability_filters.get("aircraft_model") or state.applicability_filters.get("manual_type"))
  - 这个规则调整不依赖LLM，LLM失败时也生效
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-4.1: missing_requirements=["warning"]时baseline选中chunks，rerank=safety_strict
  - `programmatic` TR-4.2: applicability_conflict=True时baseline选中chunks
  - `programmatic` TR-4.3: missing_requirements=["parameter"]时baseline选中chunks+structured_metadata
  - `programmatic` TR-4.4: 首轮无feedback时baseline与之前一致（无回归）
  - `programmatic` TR-4.5: 运行pytest tests/ 无回归
- **Notes**: 这是不依赖LLM的规则兜底，保证即使LLM Planner失败也能响应反馈

## [x] Task 5: Planner LLM prompt增强感知missing_requirements
- **Priority**: medium
- **Depends On**: Task 4
- **Description**:
  - 修改_build_planner_prompt的system_prompt：
    - 增加一条规则："6. 如果planner_feedback中标记了missing_requirements（如缺少warning、procedure、parameter、tooling），你必须确保选中能召回这类证据的通道（chunks通道几乎必选），并调整rerank_profile为safety_strict（涉及安全/警告时）或procedure_first（涉及步骤时）"
    - 增加一条规则："7. 如果存在applicability_conflict（跨机型/版本冲突），你必须优先chunks通道，并在规划理由中说明需要强调指定机型过滤"
  - 在user_prompt中明确展示：
    - "## 缺失的证据类型"（列出missing_requirements及其中文解释）
    - "## 适用性冲突"（是否存在冲突、指定机型vs证据机型）
    - "## 指定的过滤条件"（applicability_filters）
  - 扩展_sanitize_plan支持channel_top_k可选字段（dict: channel_name → top_k），但第一版不强求LLM输出这个，有则用，无则用默认top_k
  - 在LLM plan的reason中期望看到对missing_requirements或applicability_conflict的响应
- **Acceptance Criteria Addressed**: AC-4, AC-6
- **Test Requirements**:
  - `programmatic` TR-5.1: prompt包含missing_requirements展示区域
  - `programmatic` TR-5.2: prompt包含applicability_conflict展示区域
  - `human-judgement` TR-5.3: 检查prompt表述清晰，LLM容易理解应该如何调整
  - `programmatic` TR-5.4: 运行pytest tests/ 无回归
- **Notes**: LLM输出可以选做channel_top_k配置，第一版不强制；核心是prompt里让LLM看到反馈并能调整通道和rerank

## [x] Task 6: recall_entities和ES过滤简单支持
- **Priority**: medium
- **Depends On**: Task 5
- **Description**:
  - 查看recall_entities.py和ES repo，ES repo.search已经支持filters参数
  - 修改recall_entities（如果它调用ES search）传入applicability filters
  - 对于实体索引，如果metadata字段存在就加filter，否则跳过（实体可能没有机型字段）
  - recall_structured_metadata（NL2SQL通道）不强制加filter，因为它查的是schema/column信息，不是业务数据
  - 确保recall_dispatch正确传递filters到各通道
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-6.1: ES chunk search调用时带applicability filters
  - `programmatic` TR-6.2: 运行pytest tests/ 无回归
- **Notes**: 实体和NL2SQL可以简单处理，核心过滤在Milvus chunks和Wiki PG

## [x] Task 7: Trace和add_stage增强
- **Priority**: medium
- **Depends On**: Task 6
- **Description**:
  - 在各recall节点的add_stage中添加：
    - filters_applied: bool
    - filter_conditions: dict
    - filter_fallback: bool（是否降级）
  - 在plan_retrieval的add_stage中添加：
    - responded_to_missing: list[str]（Planner响应了哪些缺失项）
    - responded_to_applicability_conflict: bool
  - 在state.retrieval_trace中记录filters_applied、filter_conditions、planner_adjustment
- **Acceptance Criteria Addressed**: FR-10
- **Test Requirements**:
  - `programmatic` TR-7.1: Trace包含filters_applied字段
  - `programmatic` TR-7.2: Trace包含planner对missing_requirements的响应
  - `programmatic` TR-7.3: 运行pytest tests/ 无回归

## [x] Task 8: 新增单元测试和更新Mini Golden Set
- **Priority**: high
- **Depends On**: Task 7
- **Description**:
  - 在tests/test_correctness_enhancements.py中新增测试：
    - Milvus filter构建（无filter、有aircraft_model、有多个filter）
    - filter 0结果降级逻辑
    - Planner baseline响应missing_requirements
    - Planner baseline响应applicability_conflict
    - Planner prompt包含feedback信息
  - 更新tests/mini_golden_set.py增加场景：
    - 场景13：指定机型时Milvus带filter
    - 场景14：missing_requirements时baseline调整通道
    - 场景15：applicability_conflict时baseline调整rerank
  - 运行所有测试确保通过
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-5, AC-9
- **Test Requirements**:
  - `programmatic` TR-8.1: 新增测试全部通过
  - `programmatic` TR-8.2: Mini Golden Set更新后通过率≥90%（14/15或15/15）
  - `programmatic` TR-8.3: pytest tests/ 全部通过

## [x] Task 9: 全量验证
- **Priority**: high
- **Depends On**: Task 8
- **Description**:
  - 运行pytest tests/ -v 确认全绿
  - 运行python -m tests.mini_golden_set 确认所有场景通过
  - 运行pytest tests/test_query_orchestrator.py -v 确认编排层无回归
  - 运行pytest tests/test_correctness_enhancements.py -v 确认正确性增强测试全过
- **Acceptance Criteria Addressed**: AC-8, AC-9
- **Test Requirements**:
  - `programmatic` TR-9.1: pytest tests/ 无unexpected failure
  - `programmatic` TR-9.2: Mini Golden Set通过率100%
  - `programmatic` TR-9.3: test_query_orchestrator全部通过
