# 发现与决策记录

## 决策

| ID | 日期 | 决定 | 原因 | 复审条件 |
|---|---|---|---|---|
| D-001 | 2026-08-29 | 生成器先做确定性内核 | 先验证方法论结构，避免把模板缺陷藏在 LLM 文案中 | 稳定生成两个行业样例后接 AI |
| D-002 | 2026-08-29 | MVP 输出 Markdown 和结构化 JSON | 便于审查、diff、二次编辑和后续 Web 展示 | 出现正式 Office 交付需求时增加渲染层 |
| D-003 | 2026-08-29 | 一个方案只围绕一个主决策 | 防止 POC 退化成功能清单和大而全平台方案 | 实际项目证明必须多决策联合验收时复审 |
| D-004 | 2026-08-29 | 无客户数据时强制标记 synthetic demo | 演示结构不能被写成客户事实或业务效果 | 不复审 |
| D-005 | 2026-08-29 | 用 ProjectBlueprint 作为多种项目材料的唯一事实源 | POC、PRD、数据和验收材料若分别推导会产生口径漂移 | 实际使用证明不同材料需要独立业务模型时复审 |
| D-006 | 2026-08-29 | Studio 与 EIP 分为设计期和运行期 | 新工具可独立使用，同时保留进入 EIP 验证和运营的路径 | EIP 接口稳定后复审适配深度 |
| D-007 | 2026-08-29 | 核心采用六边形架构，CLI/LLM/EIP 都是适配器 | 保持领域编译器独立，避免 renderer 和外部平台复制业务规则 | 出现真实部署约束时复审基础设施实现 |
| D-008 | 2026-08-29 | MVP 先用 append-only 文件仓库 | 当前是单用户本地 CLI，数据库尚无用户价值依据 | 多用户并发或跨项目查询出现时复审 |
| D-009 | 2026-08-29 | EIP 首次集成仅做 pipeline_mapping 只读验证 | EIP 发布和行动能力仍是局部基础，不能作为稳定依赖 | EIP API 和 capability matrix 完成后复审 |
| D-010 | 2026-08-29 | 后续采用“计划—开发—验证—参考—复盘—修订”的滚动闭环 | 固定功能路线图不能吸收新发现，纯研究驱动又会造成范围膨胀 | 连续两轮证明维护成本高于决策价值时复审 |
| D-011 | 2026-08-29 | EIP 既是第一方开发参考，也是未来运行验证平台 | EIP 是同一开发者已走过的真实路径，应吸收其规格、四态、血缘、裁决和版本经验 | EIP 与生成器产品职责发生实质重叠时复审 |
| D-012 | 2026-08-29 | 五轮演进按进入门推进，同一时间只执行一个 Loop（已由 D-015 的七 Loop 路线取代） | 防止 Web、AI、版本和 EIP 集成同时展开，保证每轮都有可运行纵向结果 | superseded by D-015 |
| D-013 | 2026-08-29 | 本仓库从设计工具逐步长成一套新的 EIP，替代 D-006/D-009/D-011 的“Studio 对接旧 EIP”终局 | 用户希望从零重建 EIP，并保留小步开发过程；旧 EIP 当前也没有稳定入站验证契约 | 三次真实决策共创不能形成可复用修正轨迹时收缩为内部设计工具 |
| D-014 | 2026-08-29 | 旧 EIP 只作为只读行为参考，不复制模块或共享运行底座 | 复制旧实现会继承历史结构、耦合和未完成接口，也失去重新验证设计的意义 | 仅在明确版本化公共协议上允许跨仓兼容测试 |
| D-015 | 2026-08-29 | 采用七个纵向 Loop 重建，新能力必须让同一个黄金场景多走一步 | 平台模块横向铺开容易形成大提交和空壳能力；纵向骨架能持续运行、验证和 commit | 某 Loop 的最小纵切面无法独立验收时重新拆分 |
| D-016 | 2026-08-29 | 人工 review 必须绑定不可变版本和 subject checksum | 只绑定元素 ID 会把旧确认静默套到内容已变化的新元素 | 不复审 |
| D-017 | 2026-08-29 | 关闭 Loop 0 后才进入 Loop 1 的最小知识辅助计划 | 已验证的基线只能忠实表达输入，不能把缺少来源的关系或未实现运行能力包装为知识；下一步必须先补来源与适用性，再讨论可执行本体 | Loop 1 不能产生可追溯且输入外的 candidate 建议时，维持当前基线并重新收缩范围 |
| D-018 | 2026-08-29 | 将七个 Loop 解释为 Persistent AI FDE 生产线，产品机制命名为 AI FDE Decision Compiler，核心资产保持 `DecisionPack` | “方案可执行”只有在理解、规格、验证、影响、审查和发布形成连续证据后才可证伪；Markdown 只是投影 | Loop 4 用户验证不能产生可复用修正时收缩定位 |
| D-019 | 2026-08-29 | 黄金主决策收敛为“哪些订单进入优先干预队列” | 原供应链样例同时包含订单选择和处置动作两个决定，不满足一个 pack 一个主决策 | 真实共创证明两者必须不可分割验收时复审 |
| D-020 | 2026-08-29 | Loop 4 同时输出结构 semantic diff 与业务 `DecisionDelta`，并作为产品验证闸 | 字段变化不是业务价值；FDE 需要看到新逻辑翻转了哪些订单结论以及依据 | 真实 FDE/业务负责人能纠正、批准或复用 DecisionDelta 后才开放 Loop 5–7 |
| D-021 | 2026-08-29 | Loop 1 负责 source/suggestion 稳定身份和不可变 DecisionPack；Loop 2 负责 OntologySpec 类型与引用闭包；Loop 3 回执绑定内容 hash；Loop 4 才引入版本、审查和发布 | 防止为一个知识单元提前建设运行时和治理基础设施，也避免后续对象无稳定引用锚点 | 前一 Loop 的出口契约不能支撑下一 Loop 时修改下一 Loop 计划，不回写已完成证据 |
| D-022 | 2026-08-29 | Loop 1 使用 schema-validated payload profiles，不增加 typed intermediate candidate 层 | `DecisionPack` 已能保留建议语义、来源和稳定身份；提前增加第二套候选对象会制造映射漂移 | Loop 2 必须对每个已识别 profile 编译为 spec element 或生成结构化 issue，不能静默丢弃 |

## 新发现

| ID | 日期 | 来源 | 发现 | 处理 | 状态 |
|---|---|---|---|---|---|
| F-001 | 2026-08-29 | EIP 项目经验 | 可落地 POC 的最小单位不是本体对象，而是一个“触发—判断—决策—行动—反馈”闭环 | 把业务决策卡作为生成器第一层输出 | incorporated |
| F-002 | 2026-08-29 | 既有乳业方案 | LLM、规则、专业模型、Agent 和人工角色混写会造成能力过度承诺 | 输出固定增加技术职责边界 | incorporated |
| F-003 | 2026-08-29 | 开源平台对齐 | WebProtégé/VocBench 的协作能力适合方案审查，但不是 MVP 生成内核的前置 | 放入 Stage 5 | incorporated |
| F-004 | 2026-08-29 | 双行业样例 | 同一输入契约可覆盖乳品研发与供应链异常，无需行业分支代码 | 保持生成内核领域无关，行业知识后续进入独立场景包 | incorporated |
| F-005 | 2026-08-29 | 首版生成结果 | 已被 Loop 0 推翻：对象相邻自动连边没有业务语义，且会随输入顺序变化 | Loop 0 已移除 adjacency inference；Loop 1 只允许有来源的知识建议产生 candidate 关系，缺少显式关系或来源时报告信息不足 | superseded |
| F-006 | 2026-08-29 | CLI 环境验证 | 系统默认 `python3` 在不同 shell 中可能指向 Python 3.9，当前用户本地 Python 3.13 可稳定运行 | README 后续统一建议虚拟环境或显式解释器；企业安装放入单独阶段 | active |
| F-007 | 2026-08-29 | EIP 能力复盘 | EIP 的 T-Box、四态规则、血缘、裁决、版本和行动可以转化为方案设计语义，不需要复制运行表和页面 | 在 PRD 中定义设计期 ProjectBlueprint，EIP 作为后续验证适配器 | incorporated |
| F-008 | 2026-08-29 | 多交付物分析 | POC、PRD、数据清单和验收矩阵共享同一批业务事实 | 在 Web 工作台前新增 Stage 1.5，先建设统一蓝图和多 renderer | incorporated |
| F-009 | 2026-08-29 | EIP 开发路径复盘 | 真实能力在“结构化规格—确定性验证—人工裁决—版本记录”的循环中逐步形成 | 把后续路线重构为五个证据驱动 Loop | incorporated |
| F-010 | 2026-08-29 | 路线图复审 | 原 Stage 2–7 以功能类别排列，缺少进入条件和新发现回流机制 | 保留已完成基线，改用 NOW/NEXT/LATER 和每轮出口门 | incorporated |
| F-011 | 2026-08-29 | 参考项目使用边界 | 参考平台的机制不能自动成为需求，必须先对应当前问题和可验证验收条件 | 每轮最多一个主要外部参考，其他发现进入 deferred | active |
| F-012 | 2026-08-29 | 多 Agent 代码复核 | 当前候选关系只由 `zip(objects, objects[1:])` 产生，信息量没有超过输入且会随数组顺序变化 | Loop 0 删除顺序推导；Loop 1 用有来源知识单元产生 candidate suggestion | accepted |
| F-013 | 2026-08-29 | 旧 EIP 契约核查 | 旧 EIP versioning 未挂公共 router，既有 Loop 5 fixture 也不满足原生 spec 的 mapping 字段 | 取消把旧 EIP HTTP 回执作为产品终局；新仓先实现自己的无状态验证内核 | accepted |
| F-014 | 2026-08-29 | 产品方向复审 | 用户希望通过连续小 commit 从生成器逐步重建 EIP，而不是把旧 EIP 整体复制过来 | 重锚为 DecisionPack → OntologySpec → validation → review/version → mapping/lineage → decision/action 的演进路径 | accepted |
| F-015 | 2026-08-29 | Loop 0 双样例 CLI smoke / regression | 删除对象顺序推导后，两份无显式关系的样例都会明确关系信息不足；供应链“物流节点状态”仍为 `unavailable`，并保留 `synthetic_demo` 边界与未实现能力的计划表述 | 作为 Loop 0 出口证据；双样例不证明跨行业有效 | accepted |
| F-016 | 2026-08-29 | Loop 0 知识边界复核 | 当前生成器只投影已声明的对象、约束、数据源和显式关系；没有来源知识单元、适用性匹配或输入外建议，知识增益仍为零 | Loop 1 必须以可追溯、确定性的 candidate 建议解决该缺口；在此之前继续返回信息不足 | accepted |
| F-017 | 2026-08-29 | AI FDE 产品复审 | 本体字段 diff 不能回答业务负责人最关心的“哪些订单结论被翻转” | Loop 4 增加 published/candidate `ValidationReceipt` 比较得到的 `DecisionDelta` | accepted |
| F-018 | 2026-08-29 | 供应链黄金场景复审 | “哪些订单优先干预”与“采取什么处置动作”是两个治理时点不同的决定 | 黄金 pack 只保留前者；后者延后到 Loop 6 | accepted |
| F-019 | 2026-08-29 | 旧 nano-ontoprompt 供应商风险行为复核 | 合格供应商资格与历史采购事实不能共用一种关系；只从 A 买过不能推出只有 A 合格 | Loop 1 以固定 snapshot 和 caveat 建立 `QUALIFIED_TO_SUPPLY` / `HAS_SUPPLIED` 首个知识单元，不复制旧代码、不把旧测试当客户事实 | accepted |
| F-020 | 2026-08-29 | Loop 1 DecisionPack 质量复核 | 权威 pack 不仅需要 frozen dataclass，还需要稳定 ID 唯一、引用闭包和嵌套 payload 的深度不可变 | 构造时拒绝重复/悬空引用，并把映射递归冻结为稳定 tuple；canonical hash 覆盖完整 pack 内容 | accepted |
| F-021 | 2026-08-29 | Loop 1 Markdown 投影复核 | 来源 title、locator 和 caveat 即使来自受校验知识包，也可能包含换行或 Markdown 结构字符，破坏候选边界 | renderer 对来源字段做单行结构转义；保留原始值只在结构化 JSON 中 | accepted |
| F-022 | 2026-08-29 | Loop 1 黄金场景验证 | pending 入队政策只形成 readiness gap；ready 只移除 gap，并不会凭空产生可执行规则 | Loop 2 基础出口允许无 rule；另设 synthetic `decision_rule.v1` policy gate 才能进入 Loop 3 | accepted |
| F-023 | 2026-08-29 | Loop 1 opt-in CLI smoke | 同一知识单元对供应链为 applicable、对乳品为 not_applicable；缺桥接为 insufficient，证明 matcher 使用声明语义而非行业标签 | 保留乳品为跨行业 regression；不把这一结果解释为跨行业知识有效性 | accepted |
| F-024 | 2026-08-29 | Loop 2 黄金 CLI 与集成验证 | 供应链 source unit 和 synthetic policy 可编译为 canonical draft/candidate `OntologySpec`，引用闭包完成且 candidate 建议边界未丢失 | 关闭 Loop 2；Loop 3 另行实现 `ValidationReceipt`，不把 spec 生成解释为 publication 或 production | accepted |

## 验证证据

| 日期 | 验证 | 结果 | 能证明什么 | 不能证明什么 |
|---|---|---|---|---|
| 2026-08-29 | 生成器 unittest | 7 passed | 参数校验、确定性 Markdown/JSON、CLI 和双行业契约可运行 | 尚不能证明方案满足真实客户需求 |
| 2026-08-29 | 乳品研发与供应链异常样例生成 | 两份方案均包含 12 个必要章节 | 同一方法论内核可覆盖两个不同场景 | 候选关系仍需业务专家确认 |
| 2026-08-29 | Loop 0 全量 unittest | `PYTHONPATH=src python -m unittest discover -s tests -v`：25 tests，OK | 严格 boolean / 数据源状态、显式关系、关系信息不足、未实现能力表述和双行业回归在当前仓库可运行 | 不能证明真实客户价值、跨行业有效性或任何规则 / Agent / 任务 / 版本 / 回执已经运行 |
| 2026-08-29 | Loop 0 CLI 双样例临时输出检查 | `dairy_rnd.json` 与 `supply_chain_exception.json` 都保留 `synthetic_demo`；无显式关系时写明信息不足；供应链物流节点仍为 `unavailable` / 不可用；未发现把规则、Agent、任务、版本或回执写成已执行的表述 | 当前投影不会补造关系或弱化不可用状态 | 双样例仅是 smoke / regression，不证明跨行业有效；当前知识增益仍为零，须由 Loop 1 的有来源建议验证 |
| 2026-08-29 | Loop 1 全量 unittest | `PYTHONPATH=src python -m unittest discover -s tests -v`：107 tests，OK | 来源/知识契约、通用匹配、payload profile、深度不可变 DecisionPack、稳定 identity/hash、兼容投影和 CLI 防越界在当前仓库可运行 | 不证明客户适用性、规则求值、最终订单队列、Action、review、version 或 publication |
| 2026-08-29 | Loop 1 opt-in 双样例与边界 smoke | 供应链：`synthetic_demo / applicable / 7 suggestions / 3 sources`；乳品：`synthetic_demo / not_applicable / 0 / 0`；缺桥接：`insufficient_information / 0`；pending policy：7 条含 readiness gap；ready：6 条且无 gap；重复编译 pack hash 一致 | 知识单元能贡献输入外且可追溯的 candidate 建议，并在不适用、信息不足和 readiness 状态之间保持诚实边界 | 不代表建议已确认、事实已验证或优先干预队列已计算；当前 queue policy 仍只是 gap |
| 2026-08-29 | Loop 1 默认兼容与投影安全复核 | 不传 `--knowledge-unit` 的 JSON/Markdown 与 Loop 0 golden 字节一致；Task 4/5 spec review 与 quality review 均为 APPROVED；Markdown 来源结构注入回归通过 | 知识能力保持 opt-in，未改变默认契约；来源可读投影不会越过 Markdown 结构边界 | JSON 中的原始来源文本仍应被消费者作为数据而非指令处理 |
| 2026-08-29 | Loop 2 全量 unittest 与黄金 CLI | 集成点 `fbc0f33` 全量测试 **198/198** 通过；canonical spec hash `31b00f3432281459d71615fa7ba4733a522332987d26632aeeb50737a7ecfed3`；`is_closed=true` / 36 checked refs；3 entities、3 relations（2 knowledge suggestions）、2 symbolic properties、1 `categorical_all_of_v1` candidate rule、5 `requires_review` suggestion-bound issues、0 blocking issues | `DecisionPack` 可确定性编译为保持 draft/candidate/`synthetic_demo` 边界且引用闭合的 `OntologySpec` | `ValidationReceipt`、version、review、publication、action 和 writeback 尚未实现；Loop 2 完成不代表 publication 或 production |
