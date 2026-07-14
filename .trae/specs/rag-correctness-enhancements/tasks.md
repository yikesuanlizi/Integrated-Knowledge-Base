# RAG 正确性增强 - The Implementation Plan (Decomposed and Prioritized Task List)

## [x] Task 1: 历史边界Prompt强化与Trace补充
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在generate_answer.py的system prompt中明确添加："对话历史conversation_context仅用于理解用户指代（如'它'、'这个'指代什么），不是事实来源。你的答案必须完全基于evidence_pack中的内容，禁止使用conversation_context中的信息作为事实证据。"
  - 在RetrievalTrace的conversation_context中添加字段：history_prompt_enforced=True
  - 在AgentState中确保history_as_evidence始终为False，不被覆盖
- **Acceptance Criteria Addressed**: AC-1, AC-9, AC-10
- **Test Requirements**:
  - `programmatic` TR-1.1: 修改generate_answer.py的system prompt，验证包含历史边界声明
  - `programmatic` TR-1.2: 运行pytest tests/，确保所有现有测试通过
  - `human-judgement` TR-1.3: 检查Prompt表述清晰，没有歧义
- **Notes**: 改动量极小，先做这个验证流程没问题

## [x] Task 2: AgentState和Trace新增字段定义
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 在state.py的AgentState中添加：
    - `answer_requirements: dict` - {"procedure": bool, "warning": bool, "parameter": bool, "applicability": bool, "tooling": bool}
    - `applicability_filters: dict` - {"aircraft_model": str|None, "manual_type": str|None, "ata_chapter": str|None}
    - `evidence_roles: dict[str, list[str]]` - chunk_id → roles列表
    - `applicability_stats: dict` - 证据的机型/手册/版本统计
    - `applicability_conflict: bool` - 是否存在跨机型/版本冲突
    - `missing_requirements: list[str]` - 缺失的requirement类型
  - 在trace.py的RetrievalTrace中添加对应字段，确保可序列化
- **Acceptance Criteria Addressed**: AC-10, NFR-4
- **Test Requirements**:
  - `programmatic` TR-2.1: 验证AgentState新增字段有默认值，不破坏现有初始化
  - `programmatic` TR-2.2: 验证RetrievalTrace可以序列化新增字段
  - `programmatic` TR-2.3: 运行pytest tests/，确保所有现有测试通过
- **Notes**: 基础数据结构，为后续任务铺路

## [x] Task 3: extract_query抽取answer_requirements和applicability_filters
- **Priority**: high
- **Depends On**: Task 2
- **Description**: 
  - 在extract_query.py中实现规则抽取，不引入额外LLM调用：
    - answer_requirements关键词：
      - procedure: 步骤、怎么、如何、拆卸、安装、流程、procedure、step、how
      - warning: 注意、警告、危险、小心、注意事项、warning、caution、danger、note
      - parameter: 参数、压力、温度、力矩、值、规格、限制、parameter、value、torque、limit、spec
      - applicability: 适用于、哪些机型、哪个版本、applicable、model、version、revision
      - tooling: 工具、设备、需要什么、准备、材料、tool、equipment、material、prepare
    - applicability_filters抽取：复用parsers.py中的机型/ATA/手册类型正则
  - LLM调用时（如果extract_query有用到LLM），在prompt中要求返回这两个字段；LLM失败时fallback到规则
  - 将结果写入state.answer_requirements和state.applicability_filters
- **Acceptance Criteria Addressed**: AC-2, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 测试问题"液压泵拆卸步骤和注意事项是什么？需要什么工具？" → answer_requirements.procedure=True, warning=True, tooling=True
  - `programmatic` TR-3.2: 测试问题"A320液压泵拆卸步骤" → applicability_filters.aircraft_model="A320"
  - `programmatic` TR-3.3: 测试问题"AMM 29章液压泵压力参数是多少？" → applicability_filters.manual_type包含"AMM", ata_chapter="29", answer_requirements.parameter=True
  - `programmatic` TR-3.4: 运行pytest tests/，确保所有现有测试通过
- **Notes**: 第一版完全用规则，简单可靠

## [x] Task 4: build_evidence标记evidence_roles和统计applicability
- **Priority**: high
- **Depends On**: Task 3
- **Description**: 
  - 在build_evidence.py中遍历所有evidence items，为每个chunk/card标记evidence_roles：
    - 基于block_type：warning/caution/note → "warning"；步骤类/有序列表 → "procedure"；表格 → "parameter"
    - 基于内容关键词：复用Task 3的关键词列表
    - 基于metadata：ata_chapter、manual_type、aircraft_model信息
  - 统计所有evidence的applicability分布：
    - 统计aircraft_model集合
    - 统计manual_type集合
    - 统计ata_chapter集合
  - 将结果写入state.evidence_roles和state.applicability_stats
- **Acceptance Criteria Addressed**: AC-3, AC-7
- **Test Requirements**:
  - `programmatic` TR-4.1: 构造包含warning块的chunk，验证evidence_roles包含"warning"
  - `programmatic` TR-4.2: 构造有序列表步骤chunk，验证evidence_roles包含"procedure"
  - `programmatic` TR-4.3: 验证applicability_stats正确统计多个chunk的机型分布
  - `programmatic` TR-4.4: 运行pytest tests/，确保所有现有测试通过
- **Notes**: 完全基于metadata和关键词规则，不需要LLM

## [x] Task 5: validate_evidence检查覆盖率和适用性冲突
- **Priority**: high
- **Depends On**: Task 4
- **Description**: 
  - 扩展validate_evidence.py：
    1. 收集所有evidence的roles集合：covered_roles = {role for roles in state.evidence_roles.values() for role in roles}
    2. 对比state.answer_requirements中为True的项，找出missing_requirements = [req for req, needed in state.answer_requirements.items() if needed and req not in covered_roles]
    3. 如果missing_requirements非空：sufficient=False，planner_feedback中明确写"需要补充{missing_requirements}类证据"
    4. 检查applicability冲突：如果state.applicability_filters.aircraft_model指定了机型，但state.applicability_stats.aircraft_models包含其他机型 → applicability_conflict=True，sufficient=False，planner_feedback中提示跨机型冲突
    5. 如果applicability不冲突，生成applicability_summary用于后续答案生成
  - 将missing_requirements和applicability_conflict写入state
- **Acceptance Criteria Addressed**: AC-4, AC-6
- **Test Requirements**:
  - `programmatic` TR-5.1: 需要procedure+warning但只有procedure → missing_requirements=["warning"], sufficient=False
  - `programmatic` TR-5.2: 查询A320但证据包含B737 → applicability_conflict=True, sufficient=False
  - `programmatic` TR-5.3: 所有requirement都覆盖且无冲突 → sufficient=True
  - `programmatic` TR-5.4: 运行pytest tests/，确保所有现有测试通过
- **Notes**: 这是形成Agentic闭环的关键节点——校验不通过→correct_answer改写query→补检索

## [x] Task 6: correct_answer补全缺失requirements的query改写
- **Priority**: high
- **Depends On**: Task 5
- **Description**: 
  - 修改correct_answer.py的query改写prompt：
    - 如果有missing_requirements，明确要求LLM补充相关关键词（如缺少warning则在改写后的query中加入"注意事项 警告 warning caution"）
    - 如果有applicability_conflict，明确要求LLM在改写后的query中强调指定机型/ATA，过滤无关内容
  - LLM失败时的fallback：直接在原query后面拼接" {missing_requirements中文关键词}"
  - 清空上一轮检索结果时，保留applicability_filters和answer_requirements
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-6.1: 模拟missing_requirements=["warning"]，验证改写后的query包含警告相关关键词
  - `programmatic` TR-6.2: 模拟applicability_conflict，验证改写后的query强调指定机型
  - `programmatic` TR-6.3: LLM失败时fallback规则生效
  - `programmatic` TR-6.4: 运行pytest tests/，确保所有现有测试通过
- **Notes**: 闭环的最后一环——反思→改写→重新检索

## [x] Task 7: generate_answer标注适用范围
- **Priority**: high
- **Depends On**: Task 5
- **Description**: 
  - 修改generate_answer.py：
    - 在evidence pack中加入applicability_summary（从state.applicability_stats来）
    - 在system prompt中要求："在答案末尾，必须根据applicability_summary标注本回答的适用范围（机型、手册类型、ATA章节）。如果存在不同来源的内容，请分别标注适用范围，不要混为一谈。"
    - 如果state.applicability_conflict为True，在prompt中明确告知："注意：证据中存在跨机型/版本冲突，请在答案中明确说明不同来源的适用范围差异。"
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-7.1: 验证generate_answer的prompt包含适用范围标注要求
  - `programmatic` TR-7.2: applicability_conflict=True时prompt包含冲突提示
  - `human-judgement` TR-7.3: 检查Prompt表述清晰，LLM容易理解
  - `programmatic` TR-7.4: 运行pytest tests/，确保所有现有测试通过
- **Notes**: 用户可见的最终输出

## [x] Task 8: 新增单元测试覆盖核心逻辑
- **Priority**: high
- **Depends On**: Task 7
- **Description**: 
  - 新增tests/test_correctness_enhancements.py，测试：
    - answer_requirements规则抽取
    - evidence_roles标记
    - 覆盖率检查逻辑
    - 适用性冲突检测
    - correct_answer fallback改写
  - 确保测试独立，不依赖外部服务（用monkeypatch mock LLM）
- **Acceptance Criteria Addressed**: AC-2, AC-3, AC-4, AC-5, AC-6
- **Test Requirements**:
  - `programmatic` TR-8.1: 所有新增测试通过
  - `programmatic` TR-8.2: pytest tests/全部通过（包括旧测试）
- **Notes**: 保证代码质量

## [x] Task 9: Mini Golden Set验证
- **Priority**: medium
- **Depends On**: Task 8
- **Description**: 
  - 在tests/目录下创建mini_golden_set.py，包含10-20个测试场景：
    - 场景1：历史指代消解（"它怎么拆？"）→ 验证历史不进证据
    - 场景2：步骤+警告查询 → 验证两个requirement都覆盖
    - 场景3：指定机型查询 → 验证适用性识别
    - 场景4：跨机型冲突 → 验证冲突标记
    - 场景5：参数查询 → 验证parameter requirement
    - 场景6：工具查询 → 验证tooling requirement
  - 每个场景标注期望的answer_requirements、是否应该sufficient、是否有冲突
  - 提供运行脚本：python -m tests.mini_golden_set
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-9.1: Mini Golden Set脚本可运行
  - `programmatic` TR-9.2: 核心场景验证通过率≥80%
  - `human-judgement` TR-9.3: 测试场景合理，覆盖主要功能点
- **Notes**: 用简单mock数据验证节点逻辑，不需要真实Milvus/ES连接
