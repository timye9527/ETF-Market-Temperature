# DECISIONS — 设计决策日志

格式：编号 · 日期 · 状态（ACCEPTED 已定 / PROPOSED 待 Owner 确认）· 决定 · 理由。
已定的决定不重复讨论；要推翻，新增一条并引用旧编号。

---

### D-001 · 2026-10-06 · ACCEPTED — Temperature ≠ Signal ≠ Trade
温度只描述市场状态。任何“买/卖/预测”解释属于 SIGNAL 或 Research 层，与温度分开存储、分开展示。
理由：Owner 原则（MASTER_PROMPT §17）；也是合规与可信度的底线。

### D-002 · 2026-10-06 · ACCEPTED — 用 Dollar Volume，不用股数成交量
DV = 未复权收盘价 × 成交股数。
理由：不同 ETF 单价差异巨大，股数不可比；杠杆 ETF 频繁 reverse split，股数序列会跳变，DV 不受影响；DV 才能做敞口加权（D-005）。复权价不能用于 DV。

### D-003 · 2026-10-06 · ACCEPTED — 同一 Family 的 ETF 不独立投票
Family 内只取 CORE 的价格；CORE + ALTERNATIVE_CORE 的成交额相加作为关注度；杠杆/反向成员只进入 Bull/Bear 因子，其价格不进入任何因子，其成交额不进入 Volume 因子。
理由：它们是同一 underlying 的不同包装，多次计入就是 double counting。

### D-004 · 2026-10-06 · ACCEPTED — Family = 指数（或现货资产）身份；Node = 市场概念
- benchmark 不同 → 不同 Family，即使名字相似（SOXX ≠ SMH；KWEB ≠ CWEB；SLV ≠ AGQ/ZSL）。一个 Node 可挂多个 Family。
- 实物/现货支持的同一资产（GLD/IAU，IBIT/FBTC）→ 同一 Family（`identity_basis: SPOT_ASSET`），即使参考价提供商不同。
- 期货滚动策略各自成 Family（`FUTURES_STRATEGY`）。
- 与现货 Family 不同指数、但对节点情绪有价值的杠杆 ETF → `sentiment_only` Family，价格取同节点的 `price_proxy_family`。
理由：原 Prompt §27；修正了原 §8 示例中 SOXX/SMH 同 Family 的错误。

### D-005 · 2026-10-06 · ACCEPTED — Bull/Bear 用敞口加权，并只与自身历史比较
Exposure = DV × |leverage|；BullShare 的因子分是其相对自身 252 日历史的 percentile；同时独立展示 Speculative Appetite 与 Hedging Demand，不把它们压成一个方向结论。
理由：混合 3x 与 −1x 时原始 DV 失真；不同 Family 有结构性的对冲偏好；高 Bear 成交首先是对冲关注（原 §13）。

### D-006 · 2026-10-06 · ACCEPTED — 资产类不重复
- Gold、Silver 只在 `PRECIOUS_METALS`；`COMMODITY` 不含贵金属。
- 金矿股是 `EQUITY/GLOBAL/SECTOR/MATERIALS/GOLD_MINERS`，不是商品。
- Uranium（URA）是 `THEME/URANIUM_NUCLEAR`（股票主题），不是商品。
- `REAL_ESTATE` 资产类是指向 `EQUITY/US/SECTOR/REAL_ESTATE` 的视图别名，不挂 Family。
理由：原 Prompt §4 “不能随意创造重复类别”。

### D-007 · 2026-10-06 · ACCEPTED — 温度描述资产自身，Risk-on/off 是另一层
Treasury 高温 = 债券价格强（通常 risk-off）。VIX 期货 ETP、美元、T-Bills 为 REFERENCE 模式，不显示“热度”，只作为 Risk Regime 的输入。
理由：避免“所有东西都热 = 市场很好”的误读。

### D-008 · 2026-10-06 · PROPOSED（待 Owner 确认 Q1）— 方向温度 + 独立 Activity
温度有方向；Volume 以 Directional Attention 形式进入温度（50 + 0.5 × Activity × sign(5D 收益)）；无方向的 Activity 与温度并排显示。
理由：否则恐慌下跌（高成交、低趋势）会被合成为 “Neutral”。

### D-009 · 2026-10-06 · ACCEPTED（可被 Q3 推翻）— V1 只用美股上市 ETF
港股/中国用 EWH、FXI、MCHI、KWEB 代理。单一交易日历与币种，降低数据复杂度。
已知代价：与本地市场时区错位（美股交易时段反映的是前一个亚洲交易日之后的信息）。V2 加入港股本地 ETF。

### D-010 · 2026-10-06 · ACCEPTED — 可复现
原始数据按日不可变保存；温度快照可由原始数据 + 当时的 universe 版本完整重算；数字型动态 metadata 不手填进 YAML。

### D-011 · 2026-10-06 · ACCEPTED — 没有工具就不显示温度
Memory 节点 V1 为 `NO_COVERAGE`：不显示温度，不用不相关 ETF 拼凑。EWY 只作为 `MEMORY_PROXY` 标签展示。
理由：数据完整性优先于覆盖面。Phase 1b 调研是否已有合格的存储主题 ETF。

### D-012 · 2026-10-06 · ACCEPTED — Universe 控制在 ~100 只以内
V1：97 只。Tier 1+2 参与计算，Tier 3 只为自身节点出低置信度温度。新增 ETF 必须带来新的信息（新节点、新 Family 或必要的 Bull/Bear 对）。

### D-013 · 2026-10-06 · ACCEPTED — 核验前不使用杠杆/反向成员
`verified: false` 的 LEVERAGED_* / INVERSE 不进入 Bull/Bear 因子。全部 97 只当前均未核验（研究员知识整理），Phase 1b 逐只对照官网核验。

### D-014 · 2026-10-06 · ACCEPTED — 独立 repository
本项目只在 `timye9527/etf-market-temperature` 开发，与 AI-supply-chain 完全分离。

---

### D-015 · 2026-10-06 · ACCEPTED（临时）— 按 D-008 方案开工
Owner 指示“先继续跑，做出整个网站”，Q1 尚未回答。V1 先按 D-008 实现：温度有方向；Volume 以 Directional Attention 进入温度；无方向的“活跃度”并排显示。
实现细节：方向不是 ±1 的符号，而是 `clip(5 日收益 / 其 252 日标准差, −1, 1)`，避免平淡的一周在 ±1 之间跳动。Owner 若在 Q1 选择“激烈程度”，只需改 `engine.volume_scores`。

### D-016 · 2026-10-06 · ACCEPTED — 杠杆成员的自动一致性校验（修订 D-013）
人工核验之前，杠杆/反向成员若满足：近 252 日日收益对核心 ETF 回归 β 在目标倍数 ±15% 以内且 R² ≥ 0.85，则可以进入 Bull/Bear 因子。
它验证的是“方向 × 倍数 × Family 归属”在数据上成立，不验证 benchmark 名称；人工核验仍是 Phase 1b 必做项。页面上逐只显示 β、R² 与是否通过。

### D-017 · 2026-10-06 · ACCEPTED — 演示数据模式
开发环境无法访问行情源（网络策略拒绝 stooq.com、query1.finance.yahoo.com、api.tiingo.com）。为了在无数据时也能开发与测试引擎和网站，提供 `--source demo`：确定性的合成行情（市场因子 + 节点因子 + 由核心收益推导的杠杆成员 + 对涨跌有反应的成交额）。
所有由演示数据生成的页面都显示“演示数据，不代表真实市场”横幅。演示数据只用于开发，不用于任何研究结论或区间校准。

### D-018 · 2026-10-06 · ACCEPTED（原型期）— 真实数据先用 Yahoo chart 接口，由 GitHub Actions 每日运行
`.github/workflows/daily.yml` 在美股收盘后运行 `--source yahoo`，提交 `site/data.js` 并部署 GitHub Pages。
Yahoo 接口非官方、条款不允许商用：只用于个人原型。商业化之前必须换成有授权的数据源（Q2）。

### D-019 · 2026-10-06 · ACCEPTED — 已知性质：温度衡量“相对自身历史的异常程度”
匀速长期上涨的资产，其均线偏离与动量会成为常态，分位回落到中间（见测试 `test_steady_trend_regresses_toward_middle`）。这是自身历史归一化的直接结果，页面“方法”中向用户说明。

### D-020 · 2026-10-06 · ACCEPTED — 真实数据已接通
GitHub Actions 首次运行成功：97/97 只 ETF 从 Yahoo 取得 5 年日线，截至 2026-10-05。
自动杠杆校验在真实数据上排除了 UCO（对 USO 的 β = 1.14、R² = 0.84，目标 2×）：UCO 跟踪 Bloomberg WTI 子指数而 USO 是自有滚动策略，二者期货合约不同，校验按设计生效。
已知问题：低波动资产（1–3 年国债、T-Bills）的分位数对极小的价格变化很敏感，温度日间跳动大，需要在区间校准阶段处理（例如对低波动节点放宽窗口或加最小变动阈值）。

### D-021 · 2026-10-06 · ACCEPTED — 温度取 3 日平均
首次真实数据显示低波动节点（1–3 年国债等）5 日内温度跳动 30° 以上。节点温度改为每日因子合成值的 3 日均值；因子本身不平滑，Factor Breakdown 仍显示当日值。

### D-022 · 2026-10-06 · ACCEPTED — 研究层：温度分组后的历史表现
`engine.forward_stats` 把所有 DIRECTIONAL 节点的每日温度按 10° 分组，统计其后 5/20 个交易日的价格涨跌（均值、中位数、上涨概率、10/90 分位、样本数）。只在“研究”页展示，标注重叠样本与跨资产混合的局限，结果永远不反馈到温度定义。历史长度改为 10 年（`--years 10`）以增加样本。
同一页显示各温度区间在历史上的实际出现频率，作为区间校准（Q6）的依据。

### D-023 · 2026-10-06 · ACCEPTED — GitHub Pages 从 gh-pages 分支发布
仓库已改为公开。每日任务把 `site/` 强制推送到 `gh-pages` 分支，Pages 从该分支发布。地址：https://timye9527.github.io/ETF-Market-Temperature/
