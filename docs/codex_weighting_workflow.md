# Codex 信息权重工作流

本文档用中文梳理离线分析流水线，帮助你快速把微信聊天导出文件打上 `information_weight` 权重，并产出可视化结果。核心流程由四段组成：切分、标注、汇总、分析。每一段都可以通过 `src/offline/` 目录下的脚本复用。

## 1. 切分原始 CSV

- 目标：把大文件拆成便于 Codex 处理的小块，同时保留一定重叠保证上下文连续。
- 默认参数：每块 1000 行，块间重叠 20 行。

```bash
source venv/bin/activate
python src/offline/chunk_csv.py \
  AI生产力训练营__text_only.csv \
  data/chunks_1000_20 \
  --chunk-size 1000 \
  --overlap 20
```

脚本会校验参数并在目标目录下生成 `chunk_0000.csv`、`chunk_0001.csv` … 等文件，每个文件都保留原始表头。Chunk 大小与重叠可按需调整，只要同时在后续步骤保持一致。

## 2. Codex CLI 标注权重

### 2.1 Codex CLI 命令行速览

- 常用子命令：`codex exec`（非交互式执行任务）。
- 关键参数：
  - `--full-auto`：等价于 `--sandbox workspace-write -a on-failure`，自动批准安全指令。
  - `--cd DIR`：显式设定工作目录，本项目的 shell 脚本会传入仓库根目录。
  - `-`（单独作为参数）：告知 Codex 从标准输入读取完整提示词。
- 环境变量：
  - `TARGET_FILE`：我们在提示模板里使用该变量向 Codex 表示目标文件路径。
- 命令返回值：Codex 结束后会把最后一条消息写到 stdout，同时把详细思路、执行过程流式打印，便于调试。

### 2.2 提示词设计亮点

`prompts/information_weight_prompt.txt` 强调三件事：
1. **逐批编辑**：要求 Codex 每次处理不超过 ~300 行，并在局部完成后保存，以降低超长 diff 导致的失败风险。
2. **人工判断**：禁止使用正则或批量替换，鼓励逐行理解内容。
3. **幂等与补录**：如果文件已含 `information_weight`，让 Codex 自动跳过；若只加工了一部分，继续补齐剩余空白。

### 2.3 并行执行脚本

`src/offline/run_codex_weights.sh` 封装了上述调用流程：

```bash
# 一次性处理目录下所有 chunk（默认并发 16）
JOBS=16 src/offline/run_codex_weights.sh data/chunks_1000_20

# 只处理清单里的少量 chunk
python src/offline/find_unweighted_chunks.py \
  data/chunks_1000_20 \
  --manifest results/unweighted_chunks.txt
src/offline/run_codex_weights.sh --manifest results/unweighted_chunks.txt
```

脚本逻辑：
1. 读取待处理文件列表（目录或 manifest）。
2. 为每个文件导出 `TARGET_FILE`，用 `envsubst` 把提示词中的变量替换掉。
3. 通过 `codex exec --full-auto --cd <repo_root> -` 管道式传递提示词。
4. 并发度由环境变量 `JOBS` 控制，macOS 默认 Bash 不支持 `mapfile`，脚本已兼容常规 `read` 写法。

### 2.4 Manifest 循环补齐

`src/offline/find_unweighted_chunks.py` 会检查 chunk 是否存在 `information_weight` 列或是否有空值，所有异常都视作“待处理”。生成的 manifest 可以多次复用，直到再执行脚本时返回空文件为止。未来可将其封装进单一入口脚本，实现“循环三次或 manifest 为空即停止”的策略。

## 3. 汇总重构

完成所有标注后，把带重叠的 chunk 汇总回原始顺序，并对重叠区域求平均：

```bash
source venv/bin/activate
python src/offline/aggregate_chunks.py \
  --original AI生产力训练营__text_only.csv \
  --chunks data/chunks_1000_20 \
  --output results/weighted_messages.csv \
  --chunk-size 1000 \
  --overlap 20
```

输出文件 `results/weighted_messages.csv` 与原始 CSV 行数一致，只是多了一列 `information_weight`。若某些行没有任何 chunk 覆盖，权重会留空，方便后续检查。

## 4. 统计与可视化

信息权重到位后，可以先安装 Plotly（若尚未安装）：

```bash
source venv/bin/activate
uv pip install plotly
```

然后运行分析脚本：

```bash
python src/offline/analyze_weights.py \
  --input results/weighted_messages.csv \
  --summary-output results/sender_weight_summary.csv \
  --html-output results/information_weight_dashboard.html \
  --top-k 20 \
  --min-messages 5
```

- `sender_weight_summary.csv`：包含每位发送者的消息数、权重总和、平均/中位/最大/最小、标准差等统计指标。
- `information_weight_dashboard.html`：使用前两行 2×2 子图分别展示“平均权重 Top/Bottom 发送者”（带标准差误差棒）与“权重总和 Top/Bottom 发送者”，第三行额外给出按原始权重值聚合的分布柱状图。所有条形图均按要求排序，并标注消息数。

若希望直接得到高信息密度版本的聊天记录，可以添加阈值过滤参数：

```bash
python src/offline/analyze_weights.py \
  --input results/weighted_messages.csv \
  --summary-output results/sender_weight_summary.csv \
  --html-output results/information_weight_dashboard.html \
  --filter-threshold 0.25 \
  --filtered-output results/weighted_messages_filtered.csv \
  --original-csv AI生产力训练营__text_only.csv
```

脚本会在控制台输出与聚合文件以及原始聊天 CSV 的行数、文件大小对比（`--original-csv` 可选，省略则仅比较聚合文件），便于评估压缩效果。若未指定 `--filtered-output`，默认写入 `results/weighted_messages_filtered.csv`。

## 5. 常见问题与排查

| 场景 | 解决思路 |
| --- | --- |
| Codex 报 sandbox 限制 | 确认 `codex exec` 调用带了 `--full-auto`，或在提示词里减少对 shell 的需求。
| Manifest 一直不为空 | 说明某些 chunk 反复失败：检查 Codex 输出里的报错，大多是 CSV 格式被破坏；可先人工修复再重新运行脚本。
| Plotly HTML 中文字体缺失 | Plotly 默认引用系统字体，若需要特定字体，可在 `analyze_weights.py` 里修改 `font` 配置并附带字体文件。

## 6. 下一步

- 计划中的 `offline_pipeline.py` 会把“切分 → Codex 标注（循环重试）→ 汇总 → 分析”串成一个命令。届时可提供 `--max-iterations`、`--filter-threshold` 等参数。
- 若要集成更多指标（例如按日期、关键词聚合），推荐在 `src/offline/` 新建模块并复用 `weighted_messages.csv`。

让 Codex 承担繁琐的逐行判断，可以显著节省人工时间；配合 Plotly 输出的仪表盘，我们就能更清楚地识别高信息密度的讨论片段，为后续写作或知识整理提供支撑。
