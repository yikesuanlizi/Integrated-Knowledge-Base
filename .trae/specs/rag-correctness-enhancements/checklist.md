# RAG 正确性增强 - Verification Checklist

## 历史边界强化
- [x] generate_answer.py的system prompt明确包含"历史仅用于指代消解，不是事实来源"声明
- [x] RetrievalTrace中history_as_evidence始终为False
- [x] 历史指代消解功能正常工作，不因为prompt改动而失效

## 数据结构
- [x] AgentState新增字段（answer_requirements、applicability_filters、evidence_roles、applicability_stats、applicability_conflict、missing_requirements、applicability_summary）都有正确默认值
- [x] RetrievalTrace正确序列化所有新增字段
- [x] 现有代码不因为新增字段而报错

## Answer Requirements抽取
- [x] 问题包含"步骤、怎么、如何"等词时，answer_requirements.procedure=True
- [x] 问题包含"注意、警告、危险"等词时，answer_requirements.warning=True
- [x] 问题包含"参数、压力、力矩、值"等词时，answer_requirements.parameter=True
- [x] 问题包含"适用于、机型、版本"等词时，answer_requirements.applicability=True
- [x] 问题包含"工具、设备、准备"等词时，answer_requirements.tooling=True
- [x] 机型正则抽取正确（A320、B737、C919等）
- [x] ATA章节抽取正确（"第29章"、"ATA 29"、"29-11"等格式）
- [x] 手册类型抽取正确（AMM、FIM、TSM、IPC、WDM等）
- [x] LLM失败时规则fallback正常工作

## Evidence Roles标记
- [x] block_type=warning/caution/note的chunk被标记为"warning"
- [x] 包含有序列表/步骤关键词的chunk被标记为"procedure"
- [x] 表格/参数关键词的chunk被标记为"parameter"
- [x] 工具/材料/设备关键词的chunk被标记为"tooling"
- [x] 一个chunk可以有多个role
- [x] 基于metadata的机型/ATA/手册类型信息正确收集

## 覆盖率与冲突校验
- [x] 所有required roles都有evidence时，sufficient=True
- [x] 缺少required roles时，sufficient=False，missing_requirements正确列出缺失项
- [x] planner_feedback中明确说明需要补充哪类证据
- [x] 查询指定机型但证据包含其他机型时，applicability_conflict=True
- [x] 查询指定机型且证据匹配时，applicability_conflict=False
- [x] 无applicability filter时不触发冲突检查
- [x] applicability_summary正确生成，供答案标注使用

## 自纠错闭环
- [x] missing_requirements非空时，correct_answer改写的query包含对应类别的关键词
- [x] applicability_conflict=True时，correct_answer改写的query强调指定机型/ATA
- [x] LLM改写失败时，fallback规则（直接拼接关键词）生效
- [x] 重新检索时保留answer_requirements和applicability_filters，不丢失
- [x] 清空上一轮检索结果但不影响下一轮的规划

## 答案适用范围标注
- [x] generate_answer prompt包含"答案末尾必须标注适用范围"的要求
- [x] 存在applicability_conflict时，prompt提示"明确说明来源差异"
- [x] 无冲突时，prompt根据applicability_summary提示标注范围

## 测试
- [x] 新增test_correctness_enhancements.py所有21个测试通过
- [x] tests/目录下所有82个相关测试通过，无回归
- [x] Mini Golden Set脚本可运行，12个核心场景全部通过，通过率100%
- [x] 测试不依赖外部服务（Milvus/ES/LLM），全部用mock

## 代码质量
- [x] 所有新增逻辑有适当的注释
- [x] 不破坏现有API接口
- [x] 类型注解正确
- [x] 异常处理完善，LLM调用失败有fallback

## 验证结果总结
- pytest：82 passed
- 新增单元测试：21/21 passed
- Mini Golden Set：12/12 passed（100%）
- 预先存在的失败（2个，与本次修改无关）：test_nl2sql_contract、test_rerank_and_cleanup
