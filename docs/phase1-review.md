# Phase 1 Review — 架构评审结论（2026-10-06）

对应原 Prompt §30 要求的 8 项输出。第 2–5 项的详细内容在各自文档中，这里只给结论与索引。

## 1. 对产品的理解

ETF Market Temperature 是一个**市场状态仪表**：用流动性最好的 ETF 作为“传感器”，把价格趋势、关注度、杠杆资金方向、相对强弱和广度，压缩成每个市场节点一个 0–100 的温度，并且每个温度都能被拆开解释。

它回答“现在在哪里热、热了多久、在升温还是降温、资金在往哪里集中”，**不回答“接下来该买什么”**。
它的独特性不在技术指标（这些人人都有），而在三件事：
1. **Taxonomy + Family**：把几千只 ETF 组织成一棵可解释的市场树，并消除同一 underlying 的重复投票；
2. **杠杆/反向 ETF 的成交额**作为散户投机与对冲情绪的直接读数；
3. **层级相对强弱**：自动展示风险偏好沿 “大盘 → 行业 → 子行业” 的集中或扩散。

## 2–5. 设计索引
- Taxonomy → `docs/taxonomy.md`、`data/taxonomy.yaml`
- Family 模型 → `docs/family-model.md`
- 首批 Universe → `data/etf_universe.yaml`（97 只 / 66 个 Family / 87 个节点；Tier 1: 36，Tier 2: 47，Tier 3: 14；**全部未核验**）
- 五因子 → `docs/temperature-model.md`

## 原设计中被直接修正的错误（不顺从，按原 Prompt 要求指出）
1. SOXX 与 SMH 指数不同，却被放进同一 Family → 违反原 Prompt §27。改为 Family = 指数身份，Node = 市场概念（D-004）。
2. Gold Miners 放在 Commodity 下；Gold 同时出现在 COMMODITY 与 PRECIOUS_METALS → 重复类别（D-006）。
3. Uranium 放在 Commodity 下，但美国没有流动的实物铀 ETF；URA 是股票主题（D-006）。
4. REAL_ESTATE 资产类与 GICS Real Estate sector 重复（D-006）。
5. Cybersecurity / AI Infrastructure 被放进 Technology 子树，与“Theme 与 Sector 分层”自相矛盾。
6. RS 链用 SOXX/QQQ，但 QQQ 不是 Technology sector；应为 SOXX/XLK/SPY。
7. Trend 与 Volume 直接合成会把恐慌下跌显示为“中性”（D-008，待确认）。
8. Bull Share 用原始 DV，未按杠杆倍数折算敞口，混合 3x 与 −1x 时失真。
9. 示例温度“Memory 95°”：目前没有可验证的纯 Memory ETF，不能产生这个数（D-011）。

## 6. 最大的 5 个风险

| # | 风险 | 后果 | 缓解 |
|---|---|---|---|
| R1 | **温度语义不清**：方向 vs 关注度混在一个数里；Treasury/VIX/美元的“热”与股票的“热”含义相反 | 用户误读，“热”被当成买入/卖出信号；产品失去可信度 | D-008 方向温度 + 独立 Activity；REFERENCE 模式；Risk-on/off 放到 SIGNAL 层 |
| R2 | **归一化与区间是任意的**：percentile 窗口、均值回归到 50、阈值未校准 | 温度看起来精确但没有稳定含义；不同节点的 80° 不可比 | 3–5 年历史回放；区间按经验分布校准；显示整数、不显示小数；输出 confidence |
| R3 | **元数据错误**：benchmark / 杠杆倍数 / Family 归属错一个，就会把错误信息当成情绪（例如把金矿股杠杆当成金价情绪） | 静默的错误温度 | 全部 `verified: false` 起步；核验前杠杆成员不进入计算；杠杆日收益 ≈ L × CORE 收益的自动校验；Family 成员变更带生效日期 |
| R4 | **数据源与成交量口径**：免费源非合并成交量、复权口径不一、reverse split、条款禁止商用 | Volume 与 Bull/Bear 因子系统性失真；商业化时法律风险 | 未复权价×合并成交量；主源+校验源；yfinance 只用于原型；上线前确认数据授权条款 |
| R5 | **覆盖与偏差**：只用美股上市 ETF 观察港股/中国（时区错位）；杠杆 ETF 市场结构性增长；样本期短（多数杠杆 ETF 历史 < 15 年、经历过倍数调整）；用户期望 Memory 等节点却无工具 | 某些节点的温度有系统偏差或根本不该显示；回测结论不稳 | NO_COVERAGE 状态；比例型指标去趋势；标注时区；Research Layer 必须给样本量与置信区间 |

另一个需要持续提醒的非技术风险：**合规与表述**。只要页面上出现“过热”“偏冷”配合资产名，就容易被理解为建议。V1 页面固定免责声明，SIGNAL/Research 层永远与温度分开。

## 7. 写代码前必须决定的问题（需要 Owner 回答）

| # | 问题 | 本稿建议 |
|---|---|---|
| **Q1** | 温度是“方向”还是“热度/激烈程度”？恐慌暴跌那天，Regional Banks 应该显示 15° 还是 85°？ | 方向温度 + 独立 Activity 读数（D-008） |
| **Q2** | 数据预算：每月愿意为数据付多少？是否计划未来商用（决定数据授权）？ | 原型阶段 Stooq/yfinance；V1 正式用 Tiingo 或 Polygon/Massive 单源 |
| **Q3** | V1 是否只用美股上市 ETF（港股/中国用 EWH/FXI/MCHI/KWEB 代理）？ | 是（D-009） |
| **Q4** | 只做日线 EOD？ | 是 |
| **Q5** | 归一化：252 日 percentile 还是 z-score；窗口 1 年还是 3 年？ | 两者都实现，用历史稳定性比较后定 |
| **Q6** | 区间阈值：沿用原 Prompt 固定阈值，还是按历史分布校准？ | 校准（原 Prompt §16 也要求用数据验证） |
| **Q7** | Memory 节点：等待合格 ETF，还是允许个股或单股杠杆 ETF 作为 PROXY？ | 先 NO_COVERAGE；Phase 1b 调研 2025–26 年新上市的存储主题 ETF |
| **Q8** | 首页节点清单（~15–20 个）是否认同 mvp.md 的版本？ | 见 mvp.md |

## 8. Repo 目录结构

```text
etf-market-temperature/
├── README.md                 # 项目是什么 / 完成了什么 / 正在做什么 / 下一步
├── DECISIONS.md              # 设计决策日志（D-xxx）
├── prompts/                  # Owner 的原始 Prompt 与后续重要 Prompt（逐字）
│   ├── MASTER_PROMPT.md
│   └── 2026-10-06_github_checkpoint.md
├── docs/                     # 设计文档
│   ├── taxonomy.md  family-model.md  temperature-model.md
│   ├── data-requirements.md  mvp.md  phase1-review.md
├── data/
│   ├── taxonomy.yaml         # 节点树（人工维护）
│   ├── etf_universe.yaml     # Family + ETF（人工维护，需核验）
│   ├── metadata/             # 自动生成的动态 metadata（Phase 2）
│   └── raw/                  # 原始行情下载（不入 git，gitignore）
├── src/etf_temperature/
│   ├── universe.py           # 读取与校验 taxonomy/universe ✅
│   ├── data/                 # 数据源适配器、质检（Phase 2）
│   ├── factors/              # trend.py volume.py bullbear.py rs.py breadth.py（Phase 2）
│   ├── engine.py             # 节点聚合、快照（Phase 2）
│   └── report.py             # 最简报告（Phase 2）
├── tests/                    # unittest（无第三方测试依赖）
├── config/                   # 区间阈值、窗口参数（Phase 2）
└── .env.example              # 数据源 API key 模板（真实 .env 不入 git）
```

CHANGELOG.md 按 Owner 2026-10-06 指示暂缓（原 Prompt §28 的该项被 Amendment A1 覆盖）。
