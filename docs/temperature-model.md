# Temperature Model（v0.1 设计稿，未定权重）

原则：**TEMPERATURE = STATE，SIGNAL = INTERPRETATION，TRADE = DECISION**。本文件只定义 STATE。
每一个数都必须能被拆解解释（Factor Breakdown），禁止黑盒。

## 0. 先指出原设计的一个核心矛盾（必须在写代码前定案 → Q1）

原设计把 Trend（方向）和 Volume（关注度）放进同一个 0–100 的温度。问题：
**恐慌下跌**时成交额极高 → Volume 因子 ≈ 95，Trend ≈ 10，合成后 ≈ 50 “Neutral”。
这恰恰是市场最“热”（最激烈）的时候，却被显示成中性；而且 50° 无法区分“平静”与“剧烈分歧”。

本稿的处理（提议，待 Owner 确认，见 DECISIONS D-008）：

1. **Temperature 是有方向的**：高 = 价格强 + 资金追逐 + 杠杆偏多；低 = 价格弱 + 资金撤离/对冲。
2. **Volume 进入 Temperature 时带方向**（Directional Attention，§2.2），即“放量上涨”加温、“放量下跌”降温、“缩量”≈ 中性。
3. **另设一个无方向的 Activity（关注度）读数**，与温度并排显示：
   `Semiconductor 92° · Activity 88`、`Regional Banks 18° · Activity 97`（恐慌）。
   这样“冷且剧烈”和“冷且无人问津”能被区分。

## 1. 通用规则

### 1.1 归一化：自身历史的滚动 percentile
- 每个原始指标 x_t 转为它在**该工具自身过去 N 个交易日**（默认 N = 252，不足 126 天则不出分）分布中的 percentile × 100。
- 只用 t 及之前的数据（无 look-ahead）。percentile 用 rank（并列取中位）。
- 为什么不用跨 ETF 比较：不同资产的波动率、成交结构完全不同；“热”是相对自己而言的。
- 已知缺陷：一条长期**匀速**上涨的资产，均线偏离和动量本身变成“常态”，分位会回落到中间（测试 `test_steady_trend_regresses_toward_middle`）；温度衡量的是“相对自身历史的异常程度”，不是绝对强度。52 周位置子指标部分抵消这一点。percentile 有界、会饱和（连续创新高时一直 = 100）；对长期趋势性增长的指标（成交额）会长期偏高。后者用比例指标或去趋势处理（§2.2）。
- 备选（Phase 2 对比）：z-score → 正态 CDF。两种都实现，用历史数据比较稳定性后决定（Q5）。

### 1.2 合成
- Factor 分 = 其子指标分的**等权平均**（V1 不优化权重）。
- 节点 Temperature = 可用 Factor 的加权平均；V1 权重全部相等；某 Factor 不可用（例如没有杠杆 ETF、子节点不足）时**剔除并把权重重新归一**，同时降低置信度。不补 50。
- 每个温度同时输出：`temperature, factors{}, sub_indicators{}, coverage(可用因子数/5), confidence(HIGH/MED/LOW)`。

### 1.3 已知的“回归中间”效应
多个 percentile 平均后分布会向 50 集中（中心极限效应），85+ 或 15− 会很少出现。
因此 §6 的区间不能直接用原 Prompt 的阈值，需要在历史温度分布上校准（Q6）。

## 2. 五个 Factor

符号：P = CORE 收盘价（复权），DV = 美元成交额 = 未复权收盘价 × 成交股数。

### Factor A — Trend（趋势有多强）
数据源：节点上各 Family 的 CORE 价格（不用杠杆 ETF 价格）。

| 子指标 | 原始值 | 归一化 |
|---|---|---|
| A1 均线位置 | (P / MA20 − 1), (P / MA50 − 1), (P / MA200 − 1) | 各自 percentile 后平均 |
| A2 动量 | 5D、20D、60D 收益（**不含 1D**：1D 噪音太大，放到 Velocity 观察） | 各自 percentile 后平均 |
| A3 52 周位置 | (P − Low252) / (High252 − Low252) | 本身在 0–1，直接 ×100 |

Trend = mean(A1, A2, A3)。
说明：原候选的 MA125 与 MA200 高度相关，V1 只保留 MA20/50/200；原 1D Momentum 不进入 Trend。

### Factor B — Volume（Directional Attention）
数据源：节点上各 Family 的 CORE + ALTERNATIVE_CORE 美元成交额之和（不含杠杆）。

| 子指标 | 原始值 |
|---|---|
| B1 Activity | 5 日平均 DV 在过去 252 日 DV 分布中的 percentile（0–100，**无方向**） |
| B2 Volume Z | log(DV₅) 相对 log(DV) 的 60 日均值/标准差的 z-score（只用于展示与研究） |

进入温度的是带方向的版本：
```text
dir_t           = sign(5 日收益)                       ∈ {−1, 0, +1}
DirAttention_t  = 50 + 0.5 × Activity_t × dir_t        ∈ [0, 100]
```
放量上涨 → 接近 100；放量下跌 → 接近 0；缩量 → 接近 50。Activity 单独展示（§0）。
为什么用 Dollar Volume：见 D-002。成交额长期增长的去趋势：V2 用 DV / 父节点 CORE DV 的比例作为第二个 Activity 读数。

### Factor C — Bull/Bear Sentiment
数据源：节点上 Family 的 LEVERAGED_BULL / LEVERAGED_BEAR / INVERSE 成员（包括 sentiment-only Family）。
只使用 `verified: true` 的成员（数据完整性，见 data/etf_universe.yaml 头注）。

| 子指标 | 原始值 |
|---|---|
| C1 Bull Share | 敞口加权 BullShare 的 5 日均值（family-model §4.1），自身 252 日 percentile |
| C2 Speculative Appetite | BullExposure₅ / CORE DV₅ 的 percentile |
| C3 Hedging Demand | BearExposure₅ / CORE DV₅ 的 percentile |

Bull/Bear Factor = mean(C1, C2, 100 − C3)。C2、C3 原值同时展示。
只有单边（只有 Bull 或只有 Bear 成员）时：只算 C2 或 C3，不算 C1，置信度 LOW。
没有杠杆成员的节点：该 Factor 不可用（多数行业、地区、主题都是这种情况）。

**VOLATILITY 节点的语义反转**：UVXY（“做多波动率”）在含义上是恐慌方向。VIX 节点为 REFERENCE 模式，不出“热度”；
其 Bull 活跃度作为全市场 Hedging Demand 的输入，在 Risk Regime（SIGNAL 层）使用。

### Factor D — Relative Strength（资金偏好什么）
每个节点有 `rs_benchmark`（taxonomy.yaml）。RS 线 = 节点 CORE 价格 / 基准节点 CORE 价格。

| 子指标 | 原始值 |
|---|---|
| D1 RS 动量 | RS 线 20D、60D 变化率，各自 percentile |
| D2 RS 趋势 | RS / MA50(RS) − 1，percentile |

RS = mean(D1, D2)。
层级链（Risk Preference Chain）：SOXX/XLK → XLK/SPY → SPY/ACWI。链上每一环都 > 60 说明风险偏好沿链集中——这是 SIGNAL 层的“Rotation”解释，不在温度里。
注意：原 Prompt 用 SOXX/QQQ，但 QQQ 不是 Technology sector（它包含 Amazon、Costco 等）。按 GICS 层级应为 **SOXX vs XLK vs SPY**。QQQ 作为 Nasdaq-100 节点自身 vs SPY。

### Factor E — Breadth（上涨是否健康）
**只对拥有 ≥ 5 个已打分子节点的节点计算**（否则统计无意义）。样本 = 子节点（每个子节点用其主 Family 的 CORE，每个子节点 1 票）。

| 子指标 | 原始值 |
|---|---|
| E1 | 子节点中 P > MA20 的比例 |
| E2 | 子节点中 P > MA50 的比例 |
| E3 | 子节点中 20D 收益 > 0 的比例 |
| E4 | 子节点中创 20 日新高的比例 − 创 20 日新低的比例（映射到 0–100） |

Breadth = mean(E1..E4) × 100（比例本身就是 0–100，V1 不再做 percentile）。
V1 可计算 Breadth 的节点：`EQUITY/US`（11 个 sector），`EQUITY/US/SECTOR`，`EQUITY`/`EQUITY/GLOBAL`（地区，≥5），`EQUITY/US/STYLE`。
行业/主题节点没有 Breadth（需要持仓层数据，V2 研究）。

## 3. 各级节点用哪些 Factor

| 节点类型 | Trend | Volume | Bull/Bear | RS | Breadth |
|---|---|---|---|---|---|
| ASSET_CLASS / REGION | anchor_family | anchor_family | anchor_family 若有杠杆成员 | 有 rs_benchmark 时 | 子节点 ≥ 5 时 |
| SECTOR / INDUSTRY / SEGMENT / THEME | 节点上 Family | 节点上 Family | 节点上有杠杆成员时 | ✓ | 通常无 |

父节点温度**不是**子节点温度的平均（否则 Technology 会被 Semiconductors 重复计入）；父节点有自己的 anchor 价格，子节点只通过 Breadth 影响父节点。

## 4. 温度历史、速度、加速度
- 每个交易日收盘后计算一次（EOD），保存每个节点的 temperature、5 个 factor、子指标、Activity、coverage、confidence。
- Velocity_k = T_t − T_{t−k}，k ∈ {1, 5, 20}；Acceleration = Velocity_5,t − Velocity_5,t−5。
- 历史视图：1D/1W/1M/3M/6M/1Y。存储为不可变的日快照（便于事后复现每一个数，D-010）。

## 5. 区间（暂定，需校准）

原 Prompt 区间：0–15 Extreme Cold · 15–35 Cold · 35–45 Cool · 45–55 Neutral · 55–65 Warm · 65–85 Hot · 85–100 Extreme Hot。
V1 先按此显示，但 Phase 2 用 3–5 年历史温度的经验分布校准，使得例如 “Extreme Hot” ≈ 历史上最热的 5% 天数。
校准后的阈值写入配置文件（不写死在代码里），并在 DECISIONS 记录。

## 6. Research Layer（不属于温度本身）
在 Phase 3 研究：给定温度区间，未来 1D/5D/20D 收益与波动的历史分布；温度 Velocity 对波动的解释力。
**这些研究结果只能出现在 SIGNAL/Research 页面，并附样本量与置信区间，永远不改变温度定义本身。**

## 7. 开放问题（汇总见 docs/phase1-review.md）
Q1 方向/关注度分离 · Q5 归一化方法与窗口 · Q6 区间校准 · 权重是否最终需要非等权（V1 不做）。
