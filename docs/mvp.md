# MVP 定义（V1）

目标：**先让指标对 Owner 自己有用**。V1 是一个每天收盘后跑一次、可以完整解释每一个数的温度引擎 + 最简单的查看界面。

## IN SCOPE

### 数据
- `data/etf_universe.yaml` 中的 97 只美股上市 ETF（Tier 1 + Tier 2 共 83 只参与计算；Tier 3 只为自身节点出低置信度温度）。
- 日线 EOD OHLCV（复权 + 未复权）、5 年历史，单一主数据源 + 1 个校验源。
- Phase 1b：逐只核验 benchmark / daily objective / leverage，`verified: true` 后才进入计算（杠杆/反向必须）。

### 计算
- 五个 Factor：Trend、Directional Attention（Volume）、Bull/Bear、Relative Strength、Breadth（按 temperature-model.md）。
- 无方向 Activity 读数（与温度并排）。
- 节点级温度：所有 `scored: true` 且有覆盖的节点；等权；缺失因子剔除并重新归一；confidence + coverage。
- 每日快照存储；温度历史 1D/1W/1M/3M/6M/1Y；Velocity（1/5/20 日）。
- 用历史数据回放生成 ≥ 3 年的温度历史，用于校准区间（不是用于预测）。

### 展示（最小化）
- 一个静态页面或命令行报告：
  - 首页 ≈ 15–20 个节点：US Equity、Nasdaq-100、Small Cap、Technology、Semiconductors、Software、Financials、Regional Banks、Energy、Health Care、Biotech、Gold、Gold Miners、Silver、Treasury 20Y+、High Yield、Hong Kong、China、China Internet、Bitcoin；外加 Activity。
  - 点击节点 → Factor Breakdown（5 个因子 + 子指标原值）→ Family → ETF。
  - 5 日温度变化排行（Rotation 的最简版：表格，不做图）。
- 页面固定免责声明：温度描述市场状态，不是投资建议或买卖信号。

### 工程
- Python；数据与配置在 repo；单元测试覆盖 universe 校验与每个因子的计算；可从原始数据完整重算。

## OUT OF SCOPE（V1 明确不做）

| 不做 | 原因 / 何时做 |
|---|---|
| 买卖信号、目标价、预测、自动交易 | 原则：Temperature ≠ Signal ≠ Trade |
| Research Layer（温度 → 未来收益统计） | Phase 3，且只在研究页展示 |
| Memory 节点温度 | 无经过验证的纯 Memory ETF（D-011），保持 NO_COVERAGE |
| 港股/A 股本地上市 ETF、多交易日历、多币种 | V2（D-009） |
| 盘中/实时数据 | EOD 足够描述“状态”；实时成本高 |
| ETF Discovery 引擎、AI 自动分类 | Phase 3；且任何分类变更须人工确认 |
| 持仓层 Breadth（成分股 breadth） | V2 |
| Rotation Map 可视化、Capital Flow（creation/redemption） | V2 |
| 权重优化、机器学习 | 等有 ≥ 3 年温度历史与清晰评价标准后再议 |
| 用户系统、付费、订阅、Alerts | 先证明指标对自己有价值（原 Prompt §24） |
| 移动端、复杂前端框架 | V2 |
| CHANGELOG、版本 Tag、灾备体系 | Owner 2026-10-06 指示暂缓 |

## 完成标准（Definition of Done）
1. 97 只 ETF 全部核验（或明确标记排除），`verified` 字段与 source_url 齐全。
2. 一条命令完成：下载 → 质检 → 计算 → 生成当日报告。
3. 任意一个节点的温度可以逐层拆到原始数据并人工复算一致。
4. 3 年历史回放的温度分布已画出，区间阈值已校准并写入配置与 DECISIONS。
5. Owner 连续使用 2–4 周，并记录“这个温度对我有没有用”的反馈。

## 阶段计划
- **Phase 1（本次）**：世界观 + 数据结构 + 设计文档 ✅
- **Phase 1b**：ETF 核验；决定 Q1–Q8；选定数据源
- **Phase 2**：数据管道 + 因子计算 + 历史回放 + 区间校准 + 最简报告
- **Phase 3**：Rotation、Risk Regime（SIGNAL 层）、Research Layer、Discovery
