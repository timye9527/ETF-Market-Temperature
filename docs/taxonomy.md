# Taxonomy — ETF 市场分类体系（v0.1）

数据文件：`data/taxonomy.yaml`（节点树）、`data/etf_universe.yaml`（Family 与 ETF）。
校验：`python3 src/etf_temperature/universe.py`。

## 1. 三个对象，三种关系

| 对象 | 是什么 | 例子 |
|---|---|---|
| **Node（节点）** | 市场里的一个“地方”，有温度 | `EQUITY/US/SECTOR/INFORMATION_TECHNOLOGY/SEMICONDUCTORS` |
| **Family** | 一个**经济暴露的身份**（同一指数 / 同一现货资产） | `SEMI_ICE_US`（ICE 半导体指数） |
| **ETF** | 表达这个暴露的具体工具，带 role | SOXX(CORE)、SOXL(LEVERAGED_BULL)、SOXS(LEVERAGED_BEAR) |

关系：`ETF —(1:1)→ Family —(1:1 primary)→ Node —(1:1)→ Parent Node`。

**对原设计的修正**：原 Prompt 把 SOXX 与 SMH 放在同一个 `SEMICONDUCTOR_US` Family 里，但它们跟踪不同指数（SOXX: ICE/NYSE Semiconductor；SMH: MVIS US Listed Semiconductor 25），这违反了原 Prompt 第 27 条自己的规则。因此：
**Family = 指数身份；Node = 市场概念。** 一个 Node 可以挂多个 Family（Semiconductors 节点挂 `SEMI_ICE_US` 与 `SEMI_MVIS_US`）。见 DECISIONS D-004。

## 2. 节点路径与层级

节点 id 就是路径，父节点 = 去掉最后一段，自动推导，不另存。

```text
MARKET (ROOT)
├── EQUITY (ASSET_CLASS)
│   ├── GLOBAL (REGION)
│   │   └── SECTOR (DIMENSION) / MATERIALS / GOLD_MINERS, JUNIOR_GOLD_MINERS
│   ├── US (REGION)
│   │   ├── BROAD (DIMENSION)  → TOTAL_MARKET, SP500, NASDAQ100, DOW, SMALL_CAP
│   │   ├── STYLE (DIMENSION)  → GROWTH, VALUE, DIVIDEND, LOW_VOLATILITY, HIGH_BETA, QUALITY
│   │   └── SECTOR (DIMENSION) → 11 GICS sectors
│   │        └── INDUSTRY → SUB_INDUSTRY   (e.g. INFORMATION_TECHNOLOGY/SEMICONDUCTORS/MEMORY)
│   ├── HONG_KONG, CHINA(/LARGE_CAP), JAPAN, EUROPE, INDIA, TAIWAN, KOREA, EMERGING_MARKETS
├── THEME (DIMENSION, 独立于 GICS 树)
│   └── AI_INFRASTRUCTURE, CYBERSECURITY, DISRUPTIVE_INNOVATION, CHINA_INTERNET, URANIUM_NUCLEAR
├── BOND → US → TREASURY(/SHORT, INTERMEDIATE, LONG), CREDIT(/INVESTMENT_GRADE, HIGH_YIELD)
├── PRECIOUS_METALS → GOLD, SILVER
├── COMMODITY → BROAD, ENERGY/(CRUDE_OIL, NATURAL_GAS), INDUSTRIAL_METALS/COPPER
├── CURRENCY → USD                      (REFERENCE)
├── CRYPTO → BITCOIN, ETHEREUM
├── VOLATILITY → VIX_SHORT_TERM_FUTURES (REFERENCE)
├── REAL_ESTATE                         (视图别名 → EQUITY/US/SECTOR/REAL_ESTATE)
└── CASH_LIKE → US → TBILLS             (REFERENCE)
```

| level | 含义 | 是否打分 |
|---|---|---|
| ROOT / DIMENSION | 纯分组（例如 “US Sectors” 这个集合） | 否 |
| ASSET_CLASS / REGION | 有温度；自身价格由 `anchor_family` 代表，Breadth 来自子节点 | 是 |
| SEGMENT / SECTOR / INDUSTRY / SUB_INDUSTRY / THEME | 有温度；价格来自直接挂在该节点上的 Family | 是 |

## 3. 关键分类规则（新增 ETF 时按顺序判断）

1. **先看 benchmark，不看 ticker、不看名字**。必须对照基金官网 fact sheet（原 Prompt §27）。
2. **Family 身份**（`identity_basis`）：
   - `INDEX`：跟踪同一个指数 → 同一 Family（例：QQQ/QQQM/TQQQ/SQQQ/PSQ 都跟踪 Nasdaq-100）。
   - `SPOT_ASSET`：实物/现货支持、同一资产 → 同一 Family，即使参考价提供商不同（GLD/IAU；IBIT/FBTC）。
   - `FUTURES_STRATEGY`：每只期货基金滚动规则不同、长期回报显著不同 → **各自成 Family**（USO ≠ UCO 的指数）。
   - `ACTIVE`：主动管理 → 各自成 Family（ARKK）。
3. **Family 挂到哪个节点**：
   - benchmark 是标准行业指数（GICS 或 S&P Select Industry 等）→ 挂到 `SECTOR` 树。
   - benchmark 是主题指数（AI、Cybersecurity、Uranium & Nuclear、Innovation…）→ 挂到 `THEME/*`，可用 `sector_hint` 标注展示位置，但**不参与 Sector 温度**。
   - 持仓跨国的行业（金矿股）→ `EQUITY/GLOBAL/SECTOR/...`。
4. **Role** 由 fact sheet 的 daily objective 决定：+1x → CORE / ALTERNATIVE_CORE（流动性最好、价格发现最强的一只为 CORE）；>+1x → LEVERAGED_BULL；−1x → INVERSE；<−1x → LEVERAGED_BEAR。
5. 不满足任何规则 → 不收录，记录在 Phase 1b 的待决清单里。**禁止 AI 自动修改 production taxonomy**（原 Prompt §23）。

## 4. 对原 Prompt 分类的修正（都已写入 DECISIONS.md）

| 原设计 | 问题 | 修正 |
|---|---|---|
| SOXX、SMH、SOXL、SOXS 同一 Family | SMH 指数不同 | Family 按指数拆分，同挂一个节点（D-004） |
| `Commodity → Gold → Gold Miners` | 金矿股是股票，不是商品；且 Gold 已有独立资产类 `PRECIOUS_METALS` | 金矿股 → `EQUITY/GLOBAL/SECTOR/MATERIALS/GOLD_MINERS`；Gold → `PRECIOUS_METALS/GOLD`；`COMMODITY` 不含贵金属（D-006） |
| `Commodity → Uranium` | 美国没有流动的实物铀 ETF；URA 是铀矿+核电零部件股票，指数是主题指数 | `THEME/URANIUM_NUCLEAR`（EQUITY）（D-006） |
| `REAL_ESTATE` 资产类 + GICS Real Estate sector | REIT ETF 就是股票，两处都挂会重复计数 | `REAL_ESTATE` 只是指向 `EQUITY/US/SECTOR/REAL_ESTATE` 的视图别名（D-006） |
| `Technology → Software → Cybersecurity`、`Technology → AI Infrastructure` | 原 Prompt 自己要求 Theme 与 Sector 分层，但这几条又把主题放进了 Sector 树 | 全部放到 `THEME/*` |
| 示例 `NUGT / DUST` 作为 Gold 的 Bull/Bear | 它们跟踪金矿股指数（GDX 的指数），不是金价 | 归入 `GOLD_MINERS` Family |
| `Memory` 节点有温度 95° | V1 universe 里没有经过验证的纯 Memory ETF | 节点保留，`status: NO_COVERAGE`，**不显示温度，不伪造**（D-011） |

## 5. Temperature mode

- `DIRECTIONAL`：温度高 = 该资产价格状态强、关注度高、杠杆资金偏多。绝大多数节点。
- `REFERENCE`：只作为其他计算的输入（Risk-on/off、RS 基准），首页不显示“热度”。VIX 期货 ETP（结构性衰减）、美元、T-Bills。

**注意**：`BOND/US/TREASURY` 高温 = 债券价格强 = 收益率下降，通常对应 **risk-off**。温度描述资产自身状态，Risk-on/Risk-off 是另一层解释（SIGNAL 层），见 D-007。

## 6. 扩展方式

- 新地区（Vietnam、Brazil…）：在 `taxonomy.yaml` 加 `EQUITY/<REGION>` 节点 + 在 universe 加 Family/ETF。引擎不改。
- 新子行业：加节点，`rs_benchmark` 指向父节点。
- 港股本地上市 ETF（2800.HK、3033.HK 等）：V1 不收录（单一交易日历与币种，见 D-009），V2 在 `EQUITY/HONG_KONG` 下新增 Family，`listing_market: HK`。
