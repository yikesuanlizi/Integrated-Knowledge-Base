# RAG 正确性增强 - Product Requirement Document

## Overview
- **Summary**: 在已有的12节点Agentic RAG Pipeline基础上，增强四个核心正确性特性：历史对话边界强化、Evidence覆盖率检查、适用性识别与答案边界提示、Mini Golden Set验证。这些改动聚焦航空维修高可靠场景的核心风险——答错问题、混淆机型/版本、幻觉、历史混入事实链。
- **Purpose**: 让代码真正支撑"工业级RAG"的说法，不是demo级别的向量检索，而是具备证据约束、适用性校验、闭环验证的问答系统。
- **Target Users**: 面试官（面试展示）、系统开发维护人员、最终问答用户（准确性提升）。

## Goals
1. **历史边界强化**：明确历史对话只用于指代消解，绝对不进入证据链，从Prompt层和Trace层双重保障
2. **Evidence覆盖率检查**：查询阶段抽取answer requirements，证据阶段标记evidence roles，校验阶段检查覆盖率，缺失时触发重新检索
3. **适用性识别与边界提示**：识别问题中的机型/ATA/手册类型，统计证据的适用范围，跨机型/版本冲突时标记风险，答案必须标注适用范围
4. **Mini Golden Set验证**：用10-20个标注样例验证上述三个特性确实生效

## Non-Goals (Out of Scope)
- 完整的召回阶段metadata强过滤（ES/Milvus filter表达式）——留待后续P1阶段
- 预算感知Planner升级（动态top_k、分阶段检索）
- 混合意图分类（规则+LLM）
- 表格/步骤/警告等结构化内容单独存储
- Claim-level citation（句子级引用）
- 完整Golden Set（50-100题）和消融实验框架
- 多存储一致性与幂等（outbox、索引重建）
- Chunk质量评分

## Background & Context
当前系统已实现：
- 12节点LangGraph Pipeline：context_builder → classify_intent → extract_query → plan_retrieval → recall_dispatch → merge_results → expand_graph → rerank → build_evidence → generate_answer → validate_evidence → correct_answer
- 摄入链路：Docling优先解析、航空元数据推断、raw/search/embedding三份内容、结构感知切块、自动审核、多存储落地
- context_builder已标记`history_as_evidence=False`，但Prompt层未明确强调，前端无透明提示
- validate_evidence只检查证据数量，不检查证据类型覆盖率
- 元数据在摄入阶段已推断，但查询阶段未用于适用性校验
- 已有基础评测API `/api/eval`和评测面板，但无针对本批增强的验证集

## Functional Requirements
- **FR-1**: generate_answer的system prompt必须明确声明"历史对话仅用于理解指代，不是事实来源，答案必须完全基于evidence pack"
- **FR-2**: extract_query必须从问题中抽取answer_requirements，第一版支持5类：procedure（步骤）、warning（警告）、parameter（参数）、applicability（适用性）、tooling（工具/准备）
- **FR-3**: build_evidence必须为每个evidence item标记evidence_roles（基于block_type、内容关键词、metadata）
- **FR-4**: validate_evidence必须对比answer_requirements和evidence_roles，缺失项写入planner_feedback.missing_requirements
- **FR-5**: correct_answer在下一轮query改写时必须优先补召缺失的requirement类型
- **FR-6**: extract_query必须从问题中抽取applicability_filters（aircraft_model、manual_type、ata_chapter）
- **FR-7**: build_evidence必须统计所有证据的适用范围（机型、手册类型、版本分布）
- **FR-8**: validate_evidence在证据跨机型/版本冲突时标记风险，设置insufficient=True
- **FR-9**: generate_answer必须在答案末尾标注适用范围；存在冲突时必须明确说明来源差异，不得强行合并
- **FR-10**: Trace中必须记录answer_requirements、evidence_roles覆盖情况、适用性统计、历史使用情况
- **FR-11**: 提供Mini Golden Set（10-20题）和对应的验证脚本，验证上述特性生效

## Non-Functional Requirements
- **NFR-1**: 所有改动向后兼容，不破坏现有功能和测试
- **NFR-2**: 新增逻辑不显著增加单次查询延迟（<500ms overhead）
- **NFR-3**: LLM调用失败时必须有规则fallback，不得导致整个pipeline崩溃
- **NFR-4**: 所有新增状态字段必须在AgentState和RetrievalTrace中定义，类型清晰

## Constraints
- **Technical**: Python 3.11+, LangGraph 0.x, 现有代码结构不做大重构，只在现有节点内增强
- **Business**: 改动量可控，优先补齐代码闭环，不做大规模架构变更
- **Dependencies**: 复用现有llm_client、现有节点结构、现有测试框架pytest

## Assumptions
- 现有摄入阶段的元数据推断（机型、ATA、手册类型、block_type）是准确的，可以作为适用性和evidence role判断的基础
- 第一版evidence_roles用规则+关键词+metadata判断，不引入额外LLM调用
- Mini Golden Set只覆盖核心场景，不追求全覆盖

## Acceptance Criteria

### AC-1: 历史对话不混入证据链
- **Given**: 用户进行多轮对话，第二轮用指代（如"它"、"这个"）提问
- **When**: Pipeline执行到generate_answer
- **Then**: system prompt明确告知LLM"历史仅用于指代消解，不是事实来源"；最终答案中如果出现历史内容，必须在evidence pack中能找到对应证据；RetrievalTrace中history_as_evidence=False
- **Verification**: `programmatic` + `human-judgment`

### AC-2: Answer Requirements抽取
- **Given**: 用户问"液压泵拆卸步骤和注意事项是什么？需要什么工具？"
- **When**: extract_query执行
- **Then**: answer_requirements包含{"procedure": True, "warning": True, "tooling": True}
- **Verification**: `programmatic`

### AC-3: Evidence Roles标记
- **Given**: 召回到block_type=warning的chunk、有序列表步骤、工具清单段落
- **When**: build_evidence执行
- **Then**: 对应evidence item的evidence_roles分别包含"warning"、"procedure"、"tooling"
- **Verification**: `programmatic`

### AC-4: 覆盖率不足触发补检索
- **Given**: 用户要求步骤+警告，但只召回到步骤类证据
- **When**: validate_evidence执行
- **Then**: sufficient=False；planner_feedback.missing_requirements包含"warning"；correct_answer下一轮query改写会补充警告相关关键词
- **Verification**: `programmatic`

### AC-5: 适用性识别
- **Given**: 用户问"A320液压泵拆卸步骤"
- **When**: extract_query执行
- **Then**: applicability_filters.aircraft_model包含"A320"
- **Verification**: `programmatic`

### AC-6: 跨机型冲突标记
- **Given**: 召回到的证据同时包含A320和B737的内容，且问题明确指定A320
- **When**: validate_evidence执行
- **Then**: sufficient=False；标记applicability_conflict=True；提示存在跨机型证据
- **Verification**: `programmatic`

### AC-7: 答案标注适用范围
- **Given**: 召回到的证据全部来自A320 AMM 29章
- **When**: generate_answer输出答案
- **Then**: 答案末尾明确标注"适用范围：A320，AMM 29章"
- **Verification**: `programmatic` + `human-judgment`

### AC-8: Mini Golden Set验证通过
- **Given**: Mini Golden Set的10-20个标注问题
- **When**: 运行验证脚本
- **Then**: 核心场景（历史指代、步骤+警告覆盖、跨机型冲突）的验证通过率≥80%
- **Verification**: `programmatic`

### AC-9: 现有测试全部通过
- **Given**: 所有改动完成
- **When**: 运行pytest
- **Then**: 现有测试用例全部通过，无回归
- **Verification**: `programmatic`

## Open Questions
- [ ] evidence_roles的具体规则（关键词列表、block_type映射）需要在实现时细化
- [ ] Mini Golden Set的具体题目选择需要基于现有samples目录内容
