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
4. 将每个任务记录为 JSON，至少包含 `task_id`、`approach`、`patch_applied`、`public_tests_passed`、`hidden_tests_passed`、`attempts`、`tokens`、`duration_seconds`、`changed_file_count`。
5. 使用 `python evaluation/score.py results.json` 汇总指标。

评测时固定模型名称、Prompt 版本、温度、最大工具轮次和最大重试次数。失败样本必须保留运行轨迹，不得只报告成功案例。

## 首批评测结果

### 固定条件

- 任务：同一份 12 题 manifest（6 Python + 6 JavaScript）与初始代码；
- 模型：`deepseek-flash`，`temperature=0`，相同超时与补丁上限；
- 评分：同一套隐藏测试，在隔离 Docker 容器中运行；
- 唯一变量：修复方式（`single_prompt` 一次调用 vs `patchpilot` 工具工作流）。

### 结果

| 指标 | patchpilot | single_prompt |
| --- | --- | --- |
| 补丁可应用率 | 58.3% (7/12) | 91.7% (11/12) |
| 隐藏测试通过率 | 50.0% (6/12) | 91.7% (11/12) |
| 无回归率 | 58.3% (7/12) | 100% (12/12) |
| 平均 Token | 5522 | 926 |
| 平均耗时 | 69.74s | 20.45s |
| 平均改动文件数 | 0.75 | 0.92 |

### 失败类型

- `patchpilot`：4 个 JavaScript 任务生成 corrupt patch（hunk 行数写错）、`py-parse-bool` 补丁无效、`py-dedupe-order` 补丁应用但修复错误；
- `single_prompt`：仅 `py-parse-bool` 补丁无效（两种方案都败在同一题）。

### 限制与结论边界

- 样本极小（12 题）且任务简单，不能外推为通用代码修复能力；
- 两种方案的提示词存在差异：`patchpilot` 要求「附带回归测试」，`single_prompt` 要求「最小补丁」，这会降低 `single_prompt` 的补丁复杂度、从而减少 corrupt patch 失败——该差异超出了「工具工作流 vs 单次调用」的范畴，结论需谨慎解读；
- 结论仅在本评测集上成立。

