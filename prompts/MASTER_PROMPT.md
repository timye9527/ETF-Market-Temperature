# MASTER PROMPT — ETF Market Temperature

> 项目所有者（Owner）于 2026-10-06 启动项目时给出的原始 Prompt，**文字内容逐字保存**（仅把原文中逐词换行的列表合并为单行、补了小节标题格式，未改动任何措辞）。
> 这是本项目的最高需求说明。任何 AI Agent 接手时，以此为准。
> 修改原则：不改原文。需求变化时，在文末 "Amendments" 追加，并在 `DECISIONS.md` 记录。
> 对原始设计的修正意见见 `docs/phase1-review.md` 与 `DECISIONS.md`，修正以 Decision 形式生效，不改动本文件原文。

---

ETF Market Temperature / ETF 市场温度计
你现在是这个项目的首席产品架构师、ETF 市场研究员、量化研究员和全栈工程师。
你的任务不是立即开发一个复杂的网站，而是首先帮助我建立一套长期可扩展的 ETF 市场分类、ETF Family、市场情绪与温度指标体系，然后再逐步实现数据、算法、前端与商业化产品。
整个项目必须遵循：
先定义市场世界观 → 再定义数据 → 再定义算法 → 再开发产品。
不要一开始堆几十个技术指标，也不要一开始写大量前端代码。

## 1. 项目目标

我们希望建立一个：
ETF Market Temperature / ETF 市场温度计
通过全球主要 ETF 的：

* 价格趋势
* Momentum
* 成交量
* Dollar Volume
* 历史成交活跃度
* Bull / Bear ETF 关系
* Leveraged / Inverse ETF 行为
* Relative Strength
* 市场 Breadth
* 不同资产之间的 Risk-on / Risk-off 关系

把复杂金融市场压缩成：
0–100 的 Market Temperature。
例如：
US Equity：76°
Nasdaq：83°
Technology：88°
Semiconductor：92°
Memory：95°
Financials：54°
Energy：62°
Gold：71°
Treasury：33°
Hong Kong：44°
这个指标描述的是：
当前市场有多热 / 多冷、资金风险偏好在哪里、哪些资产正在升温或降温。
它不是：

* 自动交易系统
* 买卖信号
* 涨跌预测器
* 荐股系统

Temperature 描述 STATE，而不是直接产生 TRADE。

## 2. 产品核心问题

这个系统最终应该帮助用户回答五个问题：

1. 整个市场现在冷还是热？
2. 哪些资产正在升温？
3. 哪些板块已经非常拥挤？
4. 资金正在从哪里流向哪里？
5. 当前风险偏好属于 Risk-on 还是 Risk-off？

系统应该把复杂数据转换成一个普通投资者可以快速理解的界面。

## 3. ETF 不是列表，而是 Taxonomy

禁止建立一个简单的：
ticker → temperature
列表。
必须建立：

```text
Market
 └── Asset Class
      └── Region
           └── Sector / Theme
                └── ETF Family
                     ├── Core ETF
                     ├── Alternative Core ETF
                     ├── Leveraged Bull ETF
                     ├── Leveraged Bear ETF
                     ├── Inverse ETF
                     └── Satellite ETF
```

任何新 ETF 出现以后，都应该能够通过规则自动找到它在体系里的位置。

## 4. 第一层分类：Asset Class

第一版至少支持：

```text
EQUITY
BOND
COMMODITY
PRECIOUS_METALS
CURRENCY
CRYPTO
VOLATILITY
REAL_ESTATE
CASH_LIKE
```

未来允许扩展，但不能随意创造重复类别。

## 5. Equity 第二层：Market / Geography

例如：

```text
US
HONG_KONG
CHINA
JAPAN
EUROPE
INDIA
EMERGING_MARKETS
GLOBAL
```

之后允许继续增加：
Taiwan
Korea
Brazil
Vietnam
etc.
但必须保持一致的数据结构。

## 6. Equity 第三层：Size / Style / Sector

Broad Market
例如：
US Total Market
S&P 500
Nasdaq-100
Dow
Russell 2000

Style
例如：
Growth
Value
Dividend
Low Volatility
High Beta
Quality

Sector
优先使用成熟金融市场已有的标准行业框架。
美国市场 Sector 层应首先兼容主流 GICS / Sector 分类体系：

* Information Technology
* Communication Services
* Consumer Discretionary
* Consumer Staples
* Financials
* Health Care
* Industrials
* Energy
* Materials
* Utilities
* Real Estate

不要自行发明一个完全不同的一级行业系统。

## 7. 第四层：Industry / Theme

Sector 以下允许增加投资者真正关心的子行业。
例如：
Technology → Semiconductor → Memory / Storage
Technology → Software → Cybersecurity
Technology → Cloud
Technology → AI Infrastructure
Financials → Banks → Regional Banks
Energy → Oil & Gas
Energy → Uranium
Health Care → Biotechnology
Industrials → Aerospace & Defense
Consumer → Retail
Commodity → Gold → Gold Miners
Commodity → Silver
Commodity → Oil
Commodity → Copper
Commodity → Uranium
这里需要区分：
Sector
和
Theme
不能把 AI、Cybersecurity、Robotics 等主题投资，与标准 Sector 混为同一级。

## 8. ETF Family

这是整个项目最重要的数据结构之一。
例如：

```yaml
family_id: NASDAQ100_US

name: Nasdaq 100

asset_class: EQUITY
region: US
category: BROAD_INDEX

benchmark:
  Nasdaq-100 Index

members:

  core:
    - QQQ

  alternative_core:
    - QQQM

  leveraged_bull:
    - TQQQ

  inverse:
    - PSQ

  leveraged_bear:
    - SQQQ
```

Semiconductor：

```yaml
family_id: SEMICONDUCTOR_US

name: US Semiconductor

asset_class: EQUITY
region: US
sector: TECHNOLOGY
industry: SEMICONDUCTOR

members:

  core:
    - SOXX
    - SMH

  leveraged_bull:
    - SOXL

  leveraged_bear:
    - SOXS
```

重点：
同一个 Family 的 ETF 不应被当成多个独立市场投票。
例如：
SOXX 上涨
SOXL 上涨
SOXS 下跌
不能理解为：
3 个 ETF 同时看多 Semiconductor。
这实际上主要是同一个 underlying factor 的不同表达。

## 9. ETF Role

每只 ETF 必须定义 role。
至少支持：

```text
CORE
ALTERNATIVE_CORE
LEVERAGED_BULL
INVERSE
LEVERAGED_BEAR
SATELLITE
THEMATIC
PROXY
```

同时记录：

```text
leverage_factor
direction
benchmark
issuer
expense_ratio
AUM
average_volume
average_dollar_volume
inception_date
```

## 10. Liquidity Filter

不能把所有 ETF 同等处理。
系统重点研究：
真正有市场代表性的 ETF。
至少考虑：

* AUM
* Average Daily Volume
* Average Daily Dollar Volume
* Bid / Ask spread
* ETF 上市时间
* Benchmark relevance

第一版应该设计：

```text
Tier 1
Tier 2
Tier 3
Ignore
```

例如：
Tier 1：市场最核心、流动性极强、具有明确价格发现作用。
Tier 2：行业 / Theme 有较强代表性。
Tier 3：用于补充观察。
Ignore：成交量极低、重复度极高、没有信息增量。
必须避免：
为了数量而收录大量没有意义的 ETF。

## 11. ETF Family 内的权重

同一个 Family 不能简单平均。
例如 Semiconductor：
SOXX
SMH
SOXL
SOXS
应该区分：
Underlying / Core information
和：
Trading Sentiment information。
Core ETF 更适合判断：
趋势、价格、Breadth、长期市场状态
Leveraged / Inverse ETF 更适合判断：
短期情绪、投机程度、风险偏好、Bull / Bear positioning
因此两类数据应该进入不同 Factor。

## 12. Market Temperature Framework

第一版 Temperature 建议拆成五个独立 Factor。
不要立即确定最终权重。
首先建立可解释、可测试的模块。

Factor A — Trend
回答：当前资产趋势有多强？
候选指标：
Price vs MA20 / MA50 / MA125 / MA200
1D / 5D / 20D / 60D Momentum
52-week position
要求：所有指标最终 normalize 到：0–100。

Factor B — Volume / Attention
回答：市场现在有多关注这个资产？
重点不是绝对成交量。
应该使用：Current Dollar Volume vs Historical Dollar Volume Distribution
例如：

```text
Dollar Volume Percentile
20D
60D
252D
```

以及：Volume Z-score
重点优先使用：Dollar Volume，而不是单纯 share volume。因为不同 ETF 单价差别巨大。

## 13. Factor C — Leveraged Bull / Bear Sentiment

这是本产品的重要特色。
针对存在：Bull ETF、Bear ETF 的 Family。
例如：
TQQQ / SQQQ
SOXL / SOXS
TNA / TZA
FAS / FAZ
NUGT / DUST
构造：

```text
Bull Dollar Volume
Bear Dollar Volume

Bull Share
=
Bull DV /
(Bull DV + Bear DV)
```

同时研究：
Bull / Bear Volume Ratio
Bull / Bear Dollar Volume Ratio
Bull Activity Percentile
Bear Activity Percentile
但必须注意：
极高 Bear Volume 不一定代表市场一定继续下跌。
它首先代表：Bearish / Hedging Attention 上升。
同样：极高 Leveraged Bull Volume 首先代表：Speculative Risk Appetite 上升。
不要直接转换为涨跌预测。

## 14. Factor D — Relative Strength

回答：资金正在偏好什么？
必须建立层级 benchmark。
例如：SOXX vs QQQ，QQQ vs SPY
形成：Semiconductor vs Technology vs US Equity
类似：

```text
SOXX / QQQ
QQQ / SPY
```

如果：SPY +0.3%，QQQ +1.2%，SOXX +3.0%
说明：风险偏好正在从 Broad Market → Technology → Semiconductor 集中。
长期目标：自动识别 Capital Rotation / Risk Preference Chain

## 15. Factor E — Breadth

Breadth 不仅限于股票数量。
可以考虑：Sector ETF breadth、Theme ETF breadth、Family breadth
例如：11 大 Sector ETF：多少上涨、站上 MA20、站上 MA50、创 20 日新高
用于判断：Broad Market 的上涨是否健康。
例如：SPY 很强，但只有 Technology / Communication / Semiconductor 强，其它 Sector 大量转弱。
那么：市场指数可能很热，但 Breadth 温度并不高。

## 16. Temperature Score

最终每个 Market / Asset / Sector / Industry / Theme / ETF Family 都应该有：

```text
Temperature: 0–100
```

初步解释：

```text
0–15   Extreme Cold
15–35  Cold
35–45  Cool
45–55  Neutral
55–65  Warm
65–85  Hot
85–100 Extreme Hot
```

这些区间后续必须用数据验证，而不是永久写死。

## 17. Temperature ≠ Prediction

整个项目必须遵守：

```text
TEMPERATURE = STATE
SIGNAL = INTERPRETATION
TRADE = DECISION
```

三者严格分开。
例如：Semiconductor = 94° 只说明：半导体处于非常热的市场状态。
不能自动翻译成 SELL。也不能自动翻译成 BUY。
未来可以研究：在 Temperature 10、20、30 … 90、95 附近，未来 1D、5D、20D 历史收益分布如何。
但这是另外一个：Research Layer。

## 18. Higher-Level Market Temperature

最终应该形成多层级 Dashboard。
例如：GLOBAL → Equity → US Equity → Technology → Semiconductor → Memory
每一级都有 Temperature。
首页不要显示几百只 ETF。
而应该显示：

```text
US EQUITY          73°
NASDAQ             81°
TECHNOLOGY         87°
SEMICONDUCTOR      92°
MEMORY             95°

FINANCIALS         54°
ENERGY             61°
HEALTHCARE         42°

GOLD               74°
TREASURY           31°

HONG KONG          47°
CHINA INTERNET     52°
```

用户点进去以后才看到：Family、ETF、Factor breakdown。

## 19. Factor Breakdown

每一个 Temperature 页面应该可以解释：
例如：Semiconductor

```text
Temperature       92

Trend             96
Volume            89
Bull/Bear         94
Relative Strength 93
Breadth            86
```

用户必须可以理解：为什么现在是 92°。
禁止黑盒评分。

## 20. Temperature History

所有 Temperature 必须保存时间序列。
至少：1D、1W、1M、3M、6M、1Y
允许观察：升温、降温、持续高温、持续低温、快速转冷、快速转热
未来可以进一步形成：

```text
Temperature Velocity
Temperature Acceleration
```

即：温度变化速度。

## 21. Rotation Map

后续开发：Capital Rotation Map
例如：过去 5 个交易日：
Gold 73 → 61
Technology 62 → 84
Semiconductor 67 → 93
说明：资金风险偏好向高 Beta 资产迁移。
这是未来产品最重要的视觉模块之一。

## 22. 数据模型必须支持扩展

ETF metadata 至少包括：

```text
ticker
name
exchange
issuer

asset_class
region

sector
industry
theme

family_id
role

benchmark

direction
leverage_factor

AUM
avg_volume
avg_dollar_volume

liquidity_tier

active
```

以后新增 ETF 时：只需要增加 metadata。
Temperature engine 不应该重新开发。

## 23. ETF Discovery

未来开发：ETF discovery engine。
定期发现：新上市 ETF、ETF 改名、ETF 清盘、AUM 大幅变化、流动性提升
然后：根据 benchmark、fund description、holdings、issuer metadata
建议：asset_class、sector、industry、theme、family、role
但：第一阶段必须由人工确认。
禁止 AI 自动修改 production taxonomy。

## 24. 项目商业模式预留

产品未来可能：
免费：Market overview、部分温度
Premium：完整 Sector、Industry、Theme、ETF Family、Historical Temperature、Rotation、Alerts
潜在定价：Monthly subscription、Annual subscription
例如：$9.9 / month，$99 / year
但第一阶段不要开发付款系统。
首先确保：指标对自己有价值。

## 25. MVP 原则

V1 不追求全球所有 ETF。
优先覆盖：
US Broad Market、Nasdaq、US Sectors、Technology、Semiconductor、Memory、Financials、Energy、Biotech、Gold、Silver、Treasury、Hong Kong、China
然后再扩展。
建议首批：30–60 个高流动性 ETF。
不要超过约 100 个。

## 26. 第一阶段任务

现在不要开发完整网站。
首先完成：

- Task 1：建立 `docs/taxonomy.md`，定义整个 ETF taxonomy。
- Task 2：建立 `data/etf_universe.yaml`，第一版 ETF universe。每一个 ETF 必须包含：分类、Family、Role、Benchmark、Liquidity Tier
- Task 3：建立 `docs/family-model.md`，解释 ETF Family 模型。特别研究：Leveraged / Inverse ETF 如何用于 Sentiment，而避免 double counting。
- Task 4：建立 `docs/temperature-model.md`，详细设计：Trend、Volume、Bull/Bear、Relative Strength、Breadth 五个 Factor。暂时不要过度优化权重。
- Task 5：建立 `docs/data-requirements.md`，明确每一个 Factor 需要什么数据：OHLCV、Dollar Volume、ETF metadata、AUM etc. 并研究可用数据源。
- Task 6：建立 `docs/mvp.md`，定义第一版 MVP 应该做什么，明确写出 IN SCOPE、OUT OF SCOPE。

## 27. 研究原则

任何 ETF：不要仅根据 ticker 猜用途。
必须验证：基金官网、Benchmark、Fund objective
尤其是：Leveraged ETF、Inverse ETF 必须确认：它跟踪什么 benchmark，以及 daily leverage target。
如果发现 ETF：benchmark 不一致，即使名字类似，也不能强行归为同一个 Family。

## 28. 工程原则

项目必须：Git-first。
所有核心：代码、Prompt、研究、Decision、配置、数据结构，都必须进入 repo。
必须维护：README.md、docs/、data/、src/、tests/、CHANGELOG.md、DECISIONS.md
未来每一个重要阶段：commit。
不要让核心设计只存在于 Claude 对话里。

## 29. Decision Log

对于重要设计决定：例如：为什么用 Dollar Volume、为什么 Bull/Bear ETF 不独立投票、为什么 Temperature ≠ Signal、为什么选择某些 ETF
必须记录：`DECISIONS.md`
避免未来重新讨论同一个问题。

## 30. 当前执行要求

请从：Architecture / Research Phase 开始。
第一轮不要大量写程序。
首先输出：

1. 你对整个产品的理解
2. Taxonomy 架构
3. ETF Family 模型
4. 首批 ETF Universe
5. Temperature 五因子框架
6. 你认为目前设计里最大的 5 个风险
7. 哪些问题必须在写代码前解决
8. 建议的 repo directory structure

然后创建对应 docs。
如果发现我的设计有错误：直接指出。
不要为了顺从我而保留错误设计。
优先保证：Financial logic、Data integrity、Explainability、Extensibility
之后再考虑：UI、Growth、Monetization。

---

## Amendments

### A1 — 2026-10-06 · 轻量级 GitHub 资产化（原文见 `prompts/2026-10-06_github_checkpoint.md`）

- 项目资产必须进入 `timye9527/etf-market-temperature`，形成第一个 checkpoint。
- 核心 Prompt 存 `prompts/`，不只存在于对话中。
- `.gitignore` 必须排除 API Key / Token / Password / .env / 本地敏感配置。
- **覆盖第 28 条**：现阶段暂不建立 CHANGELOG、版本 Tag、复杂灾难恢复体系或大量管理文档。原则：开发优先，GitHub 持续沉淀，重要成果及时 commit/push。
- 本项目只在 ETF-Market-Temperature repository 开发，不修改、不合并 AI-supply-chain repository。
