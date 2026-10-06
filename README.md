# ETF Market Temperature / ETF 市场温度计

**网站：https://timye9527.github.io/ETF-Market-Temperature/** （每个交易日美股收盘后自动更新）

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

## 当前版本：V2（2026-10-06）
- **温度 = 相对自身趋势的冷热**：先用 6 个月与 1 年回归找到趋势，再看偏离；稳定上涨显示“强上升 + 中性”，加速冲顶才会“极热”。温度是自身 5 年百分位，极热/极冷各约占 5% 的日子。
- **五个维度**：偏离趋势 30%、动量加速 20%、拥挤度 20%（成交额 + 杠杆块）、广度 15%、相对强弱偏离 15%；极端需“确认清单”≥3 条持续 3 日。
- **周期资格**：自动 5 项检验，Owner 在 `data/eligibility.yaml` 复核；参考动作只对合格节点给出。
- **ETF 选取**：候选 213 只，每类按成交额取 Top 20，加节点覆盖与杠杆块；约 60 只大市值股只用于广度与回填。
- **网站**：总览（温度板按产业链、趋势×温度四象限）、资金轮动、市场树、ETF 池、研究（按周期资格分组）、方法、节点详情（参考动作、确认清单、周期资格、杠杆块、ETF 映射、映射股票）。
- 设计：`docs/framework-v2.md`；决策：`DECISIONS.md` D-024 起。

## 待办
- Owner 复核周期资格（`data/eligibility.yaml`）
- 逐只核验 ETF 元数据（目前依赖杠杆自动校验）
- ETF 持仓文件抓取与 ETF 重叠度矩阵
- 港股本地 ETF（下一版之后）

## 以前的待办（Phase 1b）
- 逐只对照基金官网核验 benchmark / 杠杆倍数 / Family 归属（`verified` 字段）
- 等待 Owner 决定待决问题 Q1–Q8（见 `docs/phase1-review.md` §7），尤其 Q1：温度是否有方向
- 选定数据源

## 下一步
- 第一次用真实数据运行（GitHub Actions），检查每个节点的温度是否合理
- 用 3–5 年真实历史校准温度区间（Q6）
- 人工核验 97 只 ETF；Memory 节点寻找合格 ETF

## 快速使用
```bash
pip install -r requirements.txt
python3 src/etf_temperature/universe.py          # 校验 taxonomy + universe
python3 -m unittest discover -s tests            # 运行测试
PYTHONPATH=src python3 -m etf_temperature.build --source demo   # 生成网站数据
```

## 目录
`prompts/` 原始 Prompt · `docs/` 设计文档 · `data/` taxonomy 与 universe · `src/` 代码 · `tests/` 测试 · `DECISIONS.md` 决策日志
