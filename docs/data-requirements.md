# Data Requirements（v0.1）

## 1. 每个 Factor 需要什么

| Factor | 必需字段 | 频率 | 历史长度 | 适用 ETF |
|---|---|---|---|---|
| A Trend | 复权收盘价 adj_close | 日 | ≥ 252 交易日（推荐 3–5 年用于校准） | CORE / THEMATIC |
| B Volume | 未复权收盘价 close、成交股数 volume → DV | 日 | ≥ 252 日 | CORE + ALTERNATIVE_CORE |
| C Bull/Bear | close、volume、leverage、direction（metadata） | 日 | ≥ 252 日 | LEVERAGED_* / INVERSE（verified） |
| D Relative Strength | adj_close（节点与基准节点的 CORE） | 日 | ≥ 252 日 | CORE |
| E Breadth | adj_close、high、low（20 日新高/新低） | 日 | ≥ 200 日 | 子节点 CORE |
| Liquidity Tier | ADV$、AUM、bid/ask spread、inception_date | 周/月 | 当前值 | 全部 |
| Taxonomy 核验 | benchmark、daily objective、leverage、issuer | 事件驱动 | 当前 + 变更历史 | 全部 |

### 关键数据规则
1. **Dollar Volume 必须用未复权价格 × 原始成交股数**。复权价是为了收益率连续性，乘到成交量上会把历史 DV 算错（尤其是分红多的债券 ETF 和频繁 reverse split 的杠杆 ETF）。
2. **成交量必须是全市场合并成交量（consolidated volume）**。部分免费 API 只给单一交易所（如只给 IEX）的成交量，这种数据**不能**用于 Volume / Bull-Bear 因子。
3. **公司行为（split / reverse split）**必须单独记录；收到数据后做一致性检查：份额成交量跳变但 DV 连续 → 正常；DV 跳变 → 数据问题。
4. **交易日历**：V1 只用美国交易日历（全部是美股上市 ETF，D-009）。节假日不插值。
5. **缺失与过期**：任何一个节点的输入超过 1 个交易日未更新 → 该节点温度标记 STALE，不静默使用旧值。
6. **不可变原始数据**：原始下载保存为按日期分区的文件，计算结果可从原始数据完整重算（D-010）。

## 2. Metadata（静态 vs 动态）

| 字段 | 类型 | 来源 | 存放 |
|---|---|---|---|
| ticker, name, issuer, family, role, direction, leverage, tier | 静态（人工维护） | 基金官网 fact sheet / prospectus | `data/etf_universe.yaml` |
| benchmark, identity_basis, node | 静态（人工维护） | 同上 | `data/etf_universe.yaml` |
| verified, source_url, verified_on | 核验记录 | 人工 | `data/etf_universe.yaml`（Phase 1b 补齐） |
| exchange, inception_date, expense_ratio | 半静态 | 数据源 / 官网 | `data/metadata/etf_static.csv`（自动） |
| AUM, shares_outstanding, NAV | 日更 | 发行商网站每日文件 | `data/metadata/daily/`（自动，Phase 2） |
| avg_volume, avg_dollar_volume, median spread | 计算/月更 | 由 OHLCV 计算；spread 来自官网（30 日中位数） | 计算产物 |

数字型、会变化的字段**不手填进 YAML**，避免过期数字被当成事实。

## 3. 可用数据源（待 Phase 1b 实测确认）

> 以下是研究候选，**价格、额度、条款均需在选用前到官网确认**，这里不写具体价格以免过期。

| 数据源 | 用途 | 优点 | 风险/注意 |
|---|---|---|---|
| **Tiingo** | 日线 OHLCV（含复权与未复权）、拆分/分红 | 价格低、EOD 数据质量好、有官方 API | 免费额度有限；需确认 ETF 全覆盖 |
| **Polygon.io**（2025 年起品牌为 Massive，需确认） | 日线/分钟线，合并成交量 | 机构级、合并成交量、公司行为接口完整 | 付费；免费层延迟/限速 |
| **EODHD** | 全球 EOD（含港股 .HK） | V2 扩展港股时一站式 | 需验证成交量口径 |
| **Stooq** | 免费日线 CSV | 免费、无 key，适合做交叉校验 | 无官方 SLA；复权口径需验证 |
| **yfinance (Yahoo)** | 原型阶段快速取数 | 免费、方便 | **非官方接口，条款不允许商业使用、经常失效 → 只能用于本地研究原型，不得进入生产/付费产品** |
| **Alpha Vantage / FMP** | 备选 EOD、ETF profile | 有 ETF holdings/profile 接口 | 免费额度很小 |
| **Alpaca 免费数据** | — | — | 免费层只有 IEX 单一交易所成交量 → **不适合**本项目的成交额因子 |
| **发行商官网**（iShares、SSGA、Vanguard、Invesco、Direxion、ProShares、VanEck…） | benchmark、daily objective、AUM、shares outstanding、30 日中位 spread | 一手来源、权威 | 每家格式不同，需要逐家写解析器；V1 人工核验即可 |
| **SEC EDGAR**（prospectus 497、N-CEN、N-PORT） | benchmark 与杠杆目标的法律文件、清盘/改名事件 | 免费、权威、可追溯 | 解析成本高；用于核验与 Discovery（Phase 3） |

### V1 推荐组合（待 Q2 确认预算）
- 研究原型：Stooq + yfinance 交叉校验（仅本地，不上线）。
- 正式 V1：Tiingo（或 Polygon/Massive）作为单一主源；Stooq 作为每日抽样交叉校验。
- Metadata 核验：发行商官网 fact sheet（人工），记录 source_url。

## 4. 数据量估算
97 只 ETF × 5 年 × 252 日 ≈ 12 万行日线，体量很小；单机 SQLite/Parquet 足够。V1 不需要数据库服务器。

## 5. 数据质量检查（V1 必做）
- 每日：缺失、重复日期、价格 ≤ 0、成交量为 0（杠杆 ETF 除外的 Tier 1 出现 0 成交直接告警）、单日 |收益| > 25%（非杠杆）告警。
- 主源与校验源收盘价差异 > 0.5% 告警。
- 杠杆 ETF 日收益 ≈ leverage × CORE 日收益的偏离检查（偏离长期过大说明 Family 归属或杠杆倍数录入错误——这是对 metadata 的自动核验）。
