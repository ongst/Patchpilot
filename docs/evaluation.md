# 评测协议

评测集由 6 个 Python 和 6 个原生 npm 任务组成。每个任务包含：

- 一个最小缺陷仓库；
- 面向 Agent 的 Issue；
- Agent 不可见的隐藏测试；
- 明确的测试命令。

## 流程

1. 使用 `python evaluation/materialize.py evaluation/generated` 生成 Agent 可见仓库。
2. 分别运行单次模型补丁基线和 PatchPilot 工作流。
3. 补丁完成后，将隐藏测试复制到工作区并执行。
4. 将每个任务记录为 JSON：`patch_applied`、`public_tests_passed`、`hidden_tests_passed`、`tokens`、`duration_seconds`。
5. 使用 `python evaluation/score.py results.json` 汇总指标。

评测时固定模型名称、Prompt 版本、温度、最大工具轮次和最大重试次数。失败样本必须保留运行轨迹，不得只报告成功案例。

