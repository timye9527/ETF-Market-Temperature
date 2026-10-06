# ETF Market Temperature / ETF 市场温度计

用流动性最好的 ETF 作为“传感器”，把全球市场压缩成一棵可解释的市场树，每个节点（US Equity、Technology、Semiconductors、Gold、Treasury、Hong Kong…）一个 **0–100 的温度**，并能拆解成 Trend / Volume / Bull-Bear / Relative Strength / Breadth 五个因子。

> 温度描述市场**状态**，不是买卖信号、预测或投资建议。（TEMPERATURE = STATE，SIGNAL = INTERPRETATION，TRADE = DECISION）

## 当前已完成（Phase 1：架构与研究）
- ETF Taxonomy：`docs/taxonomy.md`、`data/taxonomy.yaml`（87 个节点，GICS 兼容，Theme 独立维度）
- ETF Family 模型：`docs/family-model.md`（避免 double counting；杠杆/反向 ETF 的情绪用法）
- V1 ETF Universe：`data/etf_universe.yaml`（97 只 / 66 个 Family；**尚未逐只核验**）
- 温度五因子设计：`docs/temperature-model.md`
- 数据需求与数据源研究：`docs/data-requirements.md`
- MVP 范围：`docs/mvp.md`
- 架构评审（风险、待决问题、目录结构）：`docs/phase1-review.md`
- 决策日志：`DECISIONS.md`
- 原始 Prompt：`prompts/MASTER_PROMPT.md`
- Universe 校验器 + 测试：`src/etf_temperature/universe.py`、`tests/`

## 正在进行（Phase 1b）
- 逐只对照基金官网核验 benchmark / 杠杆倍数 / Family 归属（`verified` 字段）
- 等待 Owner 决定待决问题 Q1–Q8（见 `docs/phase1-review.md` §7），尤其 Q1：温度是否有方向
- 选定数据源

## 下一步（Phase 2）
数据管道（EOD OHLCV）→ 五因子计算 → 节点聚合与每日快照 → 3 年历史回放与区间校准 → 最简报告页面。

## 快速使用
```bash
pip install -r requirements.txt
python3 src/etf_temperature/universe.py          # 校验 taxonomy + universe
python3 -m unittest discover -s tests            # 运行测试
```

## 目录
`prompts/` 原始 Prompt · `docs/` 设计文档 · `data/` taxonomy 与 universe · `src/` 代码 · `tests/` 测试 · `DECISIONS.md` 决策日志
