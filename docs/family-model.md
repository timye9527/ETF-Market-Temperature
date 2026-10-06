# ETF Family Model（v0.1）

## 1. 为什么要 Family

同一个指数的多个 ETF 不是多个独立的市场观点，而是**同一个 underlying factor 的不同包装**。
SOXX +3%、SOXL +9%、SOXS −9% 是一件事（半导体指数涨了 3%），不是三票看多。

所以 Family 把 ETF 分成两类信息，进入**不同的 Factor**，每类信息在一个 Family 内只计一次：

| 信息类型 | 来自哪些 role | 进入哪个 Factor | Family 内如何合并 |
|---|---|---|---|
| **价格信息**（underlying 走势） | CORE（只用 CORE 一只） | Trend、Relative Strength、Breadth | 只取 CORE 的价格序列；ALTERNATIVE_CORE 不再投票 |
| **关注度信息**（总成交额） | CORE + ALTERNATIVE_CORE | Volume / Attention | 美元成交额**相加**（同一暴露的总交易量） |
| **情绪信息**（杠杆/反向资金的方向） | LEVERAGED_BULL、LEVERAGED_BEAR、INVERSE | Bull/Bear Sentiment | 敞口加权后算 Bull Share（§4） |

杠杆 ETF 的**价格**永远不进入 Trend/RS/Breadth（它只是 CORE 价格的路径依赖变换，再算一次就是 double counting）。
杠杆 ETF 的**成交额**不进入 Volume factor（否则同一笔投机兴趣会在 Volume 和 Bull/Bear 两个因子里各算一次）。

## 2. 数据结构

```yaml
families:
  - id: SEMI_ICE_US
    node: EQUITY/US/SECTOR/INFORMATION_TECHNOLOGY/SEMICONDUCTORS   # 分类只存在这里
    benchmark: NYSE Semiconductor Index (ICE)
    identity_basis: INDEX          # INDEX | SPOT_ASSET | FUTURES_STRATEGY | ACTIVE
etfs:
  - {ticker: SOXX, family: SEMI_ICE_US, role: CORE,           direction: LONG,  leverage: 1, tier: 1}
  - {ticker: SOXL, family: SEMI_ICE_US, role: LEVERAGED_BULL, direction: LONG,  leverage: 3, tier: 1}
  - {ticker: SOXS, family: SEMI_ICE_US, role: LEVERAGED_BEAR, direction: SHORT, leverage: 3, tier: 1}
```

ETF 的 asset_class / region / sector / industry / theme 由 `family.node` 路径推导（`Universe.resolve()`），
**不在每只 ETF 上重复填写**——重复填写就会出现不一致。

### 特殊情况：sentiment-only Family
有些杠杆 ETF 跟踪期货指数，与现货 Family 不同（AGQ/ZSL 跟踪 Bloomberg Silver Subindex，而 SLV 是实物银）。
按规则它们不能并入 SLV 的 Family，但它们的情绪信息对 Silver 节点有价值。
处理：`sentiment_only: true` + `price_proxy_family: SILVER_SPOT`（必须同节点）。它们只贡献 Bull/Bear 因子。

## 3. 一个节点有多个 Family 时

例：Semiconductors 节点有 `SEMI_ICE_US`（SOXX）与 `SEMI_MVIS_US`（SMH）。两者持仓高度重叠，但指数不同。

- **Trend / RS**：每个 Family 先各自算出因子分，再在节点内按 `sqrt(美元成交额)` 加权平均（流动性越好、价格发现越强，权重越大；sqrt 防止一只巨无霸垄断）。
- **Volume**：每个 Family 先各自算 percentile，再同样加权（不能把两只的成交额直接相加后算 percentile——两只的历史长度和结构不同）。
- **Bull/Bear**：只有拥有杠杆成员的 Family 贡献；没有就不贡献，不补零。
- **Breadth**：同一节点内的多个 Family **不算多个 breadth 样本**（它们是同一个市场概念）；Breadth 只数子节点。

## 4. Leveraged / Inverse ETF 用于情绪，而不 double count

### 4.1 敞口加权
$1 的 SOXL 成交 ≈ $3 的半导体多头敞口；$1 的 SH 成交 ≈ $1 的空头敞口。所以：

```text
BullExposure_t = Σ_{bull members} DollarVolume_i,t × leverage_i
BearExposure_t = Σ_{bear+inverse members} DollarVolume_i,t × leverage_i
BullShare_t    = BullExposure_t / (BullExposure_t + BearExposure_t)
```

原 Prompt 的 `Bull DV / (Bull DV + Bear DV)` 在 bull 与 bear 杠杆倍数相同时（TQQQ/SQQQ 都是 3x）等价；
但 SP500_US 同时有 3x（UPRO/SPXU）与 −1x（SH），不加权就会把 SH 的对冲资金低估 3 倍。

### 4.2 只和自己的历史比
原始 BullShare 有结构性偏差（例如某些 Family 的 bear ETF 长期被用作对冲工具，BullShare 常年 < 0.5）。
所以因子分 = `BullShare 的 5 日均值` 在该 Family **自身过去 252 个交易日**分布里的 percentile。
不同 Family 之间不比较原始 BullShare。

### 4.3 两个独立读数，不合成一个方向
- **Speculative Appetite** = Bull 敞口相对 CORE 成交额的 percentile（杠杆多头资金有多活跃）。
- **Hedging Demand** = Bear 敞口相对 CORE 成交额的 percentile（对冲/看空资金有多活跃）。

两者都高 = 分歧大、波动大，而不是“中性”。页面上必须同时展示，不能只给一个 Bull Share。
（原 Prompt §13 的提醒：极高 Bear Volume 首先是对冲关注上升，不是下跌预测。）

### 4.4 已知的失真
- **日度再平衡**：杠杆 ETF 在收盘前按当日涨跌幅向同方向再平衡，这部分是机械交易，体现在 underlying 而不是 ETF 份额成交上；我们只用 ETF 自身成交额，不受影响，但要知道 ETF 成交额 ≠ 资金净流入。
- **成交额 ≠ 资金流向**：买卖双方各一半。真正的资金流是 creation/redemption（份额变化 × NAV），V2 研究 `shares_outstanding` 的变化作为补充。
- **反向分拆**：杠杆 ETF 经常 reverse split，份额成交量序列会跳变；美元成交额（价格 × 份额）不受影响——这也是用 Dollar Volume 的另一个原因（D-002）。
- **长期结构增长**：杠杆 ETF 市场整体在扩张，原始成交额的 percentile 会长期偏高。因此 4.3 用“相对 CORE 成交额”的比例，而不是绝对值。

## 5. Role 定义

| Role | 定义（来自 fact sheet daily objective） | 用途 |
|---|---|---|
| CORE | +1x，该 Family 内流动性/价格发现最强的一只；每个非 sentiment-only Family **恰好 1 只** | 价格 + 关注度 |
| ALTERNATIVE_CORE | +1x，同一 Family 的其他工具（IVV、VOO、QQQM、IAU、FBTC） | 只贡献关注度 |
| LEVERAGED_BULL | > +1x | 情绪（多） |
| LEVERAGED_BEAR | < −1x | 情绪（空） |
| INVERSE | −1x | 情绪（空/对冲） |
| THEMATIC | 主题 Family 的 +1x 主工具（相当于主题的 CORE） | 价格 + 关注度 |
| SATELLITE | 同节点但不同指数、不足以成为独立 Family 的补充观察（V1 未使用） | 仅展示 |
| PROXY | 间接代理（例如以 EWY 观察 Memory），不进入该节点温度 | 仅展示 |

## 6. Liquidity Tier 规则（初值为判断，上线后按数据重算）

| Tier | 规则（20 日中位数美元成交额 ADV$，AUM） | 处理 |
|---|---|---|
| 1 | ADV$ ≥ $500M，或该市场的主价格发现工具 | 计算 + 首页 |
| 2 | ADV$ ≥ $50M 且 AUM ≥ $500M | 计算 |
| 3 | ADV$ ≥ $5M | 只为**自己所在节点**算温度（标记低置信度），不进入父节点 Breadth、不上首页；Tier 3 杠杆成员只在同 Family 另一侧也存在时进入 Bull/Bear，避免单边 |
| IGNORE | ADV$ < $5M、上市 < 1 年、或与已有 Family 完全重复且无增量 | 不收录 |

额外条件：中位数 bid/ask spread > 0.30% 的降一级；上市不足 252 个交易日的，Volume percentile 和 Bull/Bear percentile 标记为低置信度。

## 7. 时间维度（必须支持）

Family 成员与 benchmark 会变（SOXX 2021 年换指数；ETF 改名、清盘、杠杆倍数调整，如 NUGT/DUST 2020 年由 3x 改 2x）。
V1 的 YAML 只描述当前状态；Phase 2 起增加 `effective_from / effective_to`，回测时按历史成员关系计算，避免用今天的分类解释过去（look-ahead）。
