"use strict";
// Curated architecture examples, never live repository facts or execution results.
document.documentElement.classList.add("js");
const $ = (id) => document.getElementById(id);
const setText = (id, text) => {
  $(id).textContent = text;
};
const ns = "http://www.w3.org/2000/svg";
function svgElement(tag, attrs = {}, text) {
  const el = document.createElementNS(ns, tag);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  if (text !== undefined) el.textContent = text;
  return el;
}

// Selection highlights direct relationships, not inferred impacts or proof.
function renderGraph(id, nodes, inputEdges, insightId, width, height) {
  const root = $(id);
  const edges = inputEdges.filter(
    (e) =>
      nodes.some((n) => n.id === e.from) && nodes.some((n) => n.id === e.to),
  );
  const svg = svgElement("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "group",
    "aria-label": root.getAttribute("aria-label") || "阶段语义关系图",
    class: "semantic-graph",
  });
  const defs = svgElement("defs");
  const marker = svgElement("marker", {
    id: `${id}-arrow`,
    viewBox: "0 0 10 10",
    refX: "9",
    refY: "5",
    markerWidth: "6",
    markerHeight: "6",
    orient: "auto-start-reverse",
  });
  marker.append(
    svgElement("path", {
      d: "M 1 1 L 9 5 L 1 9",
      fill: "none",
      stroke: "#9cafa0",
      "stroke-width": "1.5",
    }),
  );
  defs.append(marker);
  svg.append(defs);
  const edgeGroups = [],
    nodeGroups = [],
    mobileButtons = [];
  const mobile = document.createElement("ul");
  mobile.className = "graph-mobile";
  edges.forEach((edge) => {
    const a = nodes.find((n) => n.id === edge.from),
      b = nodes.find((n) => n.id === edge.to);
    let x1 = a.x + 80,
      y1 = a.y + 60,
      x2 = b.x + 80,
      y2 = b.y;
    if (Math.abs(a.y - b.y) < 20) {
      x1 = a.x + (b.x > a.x ? 160 : 0);
      y1 = a.y + 30;
      x2 = b.x + (b.x > a.x ? 0 : 160);
      y2 = b.y + 30;
    } else if (a.y > b.y) {
      y1 = a.y;
      y2 = b.y + 60;
    }
    const g = svgElement("g", { class: "semantic-edge" });
    g.append(
      svgElement("path", {
        d: edge.path || `M${x1} ${y1} L${x2} ${y2}`,
        "marker-end": `url(#${id}-arrow)`,
      }),
    );
    g.append(
      svgElement(
        "text",
        {
          x: edge.lx ?? (x1 + x2) / 2,
          y: edge.ly ?? (y1 + y2) / 2 - 8,
          "text-anchor": "middle",
        },
        edge.label,
      ),
    );
    svg.append(g);
    edgeGroups.push({ el: g, ...edge });
  });
  const names = Object.fromEntries(nodes.map((n) => [n.id, n.label]));
  function select(node) {
    const related = new Set([node.id]);
    const relations = edges.filter(
      (e) => e.from === node.id || e.to === node.id,
    );
    relations.forEach((e) => {
      related.add(e.from);
      related.add(e.to);
    });
    nodeGroups.forEach((item) => {
      item.el.classList.toggle("dimmed", !related.has(item.id));
      item.el.setAttribute("aria-pressed", String(item.id === node.id));
    });
    mobileButtons.forEach((item) =>
      item.el.setAttribute("aria-pressed", String(item.id === node.id)),
    );
    edgeGroups.forEach((item) =>
      item.el.classList.toggle(
        "dimmed",
        item.from !== node.id && item.to !== node.id,
      ),
    );
    const paths = relations
      .map((e) => `${names[e.from]} —${e.label}→ ${names[e.to]}`)
      .join("；");
    setText(
      insightId,
      `${node.description} ${paths || "本阶段尚未建立直接关系。"}`,
    );
  }
  nodes.forEach((node) => {
    const group = svgElement("g", {
      class: `semantic-node type-${node.type} state-${node.state || "existing"}`,
      transform: `translate(${node.x},${node.y})`,
      role: "button",
      tabindex: "0",
      "aria-label": `${node.label}，${node.status}`,
      "aria-pressed": "false",
    });
    group.append(svgElement("rect", { width: 160, height: 60, rx: 4 }));
    group.append(
      svgElement("text", { x: 12, y: 20, class: "node-kind" }, node.status),
    );
    group.append(
      svgElement("text", { x: 12, y: 43, class: "node-name" }, node.label),
    );
    group.addEventListener("click", () => select(node));
    group.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        select(node);
      }
    });
    svg.append(group);
    nodeGroups.push({ el: group, id: node.id });
    const li = document.createElement("li"),
      button = document.createElement("button");
    button.className = `type-${node.type} state-${node.state || "existing"}`;
    button.setAttribute("aria-pressed", "false");
    const name = document.createElement("strong"),
      status = document.createElement("span");
    name.textContent = node.label;
    status.textContent = node.status;
    button.append(name, status);
    button.addEventListener("click", () => select(node));
    li.append(button);
    mobile.append(li);
    mobileButtons.push({ el: button, id: node.id });
  });
  const relationList = document.createElement("p");
  relationList.className = "graph-mobile-relations";
  relationList.textContent = edges
    .map((e) => `${names[e.from]} —${e.label}→ ${names[e.to]}`)
    .join("；");
  root.replaceChildren(svg, mobile, relationList);
}
const heroNodes = [
  {
    id: "requirement",
    label: "带宽需求",
    type: "business",
    status: "业务需求",
    x: 20,
    y: 25,
    description: "需求描述期望结果：部署路径满足最小可用带宽。",
  },
  {
    id: "rule",
    label: "最小带宽规则",
    type: "business",
    status: "业务规则",
    x: 370,
    y: 25,
    description: "规则是可被实现和验证的一等业务对象。",
  },
  {
    id: "slice",
    label: "路径计算切片",
    type: "business",
    status: "业务—技术桥接",
    x: 195,
    y: 175,
    description: "实现切片组织共同承担业务责任的技术对象。",
  },
  {
    id: "api",
    label: "请求字段",
    type: "code",
    status: "技术 · API",
    x: 20,
    y: 335,
    description: "请求字段表示带宽要求，但不是业务属性本身。",
  },
  {
    id: "code",
    label: "约束求值器",
    type: "code",
    status: "技术 · 代码",
    x: 215,
    y: 335,
    description: "求值器承担规则执行责任；映射声明仍需证据验证。",
  },
  {
    id: "test",
    label: "带宽规则测试",
    type: "evidence",
    status: "验证规范",
    x: 410,
    y: 335,
    description: "测试设计说明如何验证规则，不代表测试已经执行。",
  },
];
renderGraph(
  "hero-graph",
  heroNodes,
  [
    { from: "requirement", to: "rule", label: "受规则约束" },
    { from: "rule", to: "slice", label: "落实到", lx: 415, ly: 128 },
    { from: "slice", to: "api", label: "契约入口", lx: 130, ly: 281 },
    { from: "slice", to: "code", label: "支持实现", lx: 315, ly: 282 },
    {
      from: "test",
      to: "rule",
      label: "验证",
      path: "M570 352 C620 352 618 55 530 55",
      lx: 591,
      ly: 220,
    },
  ],
  "hero-insight",
  640,
  430,
);

function bindTabs(selector, onChange) {
  const tabs = [...document.querySelectorAll(selector)];
  function activate(index, focus = false) {
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
    });
    $(tabs[index].getAttribute("aria-controls")).setAttribute(
      "aria-labelledby",
      tabs[index].id,
    );
    onChange(index);
    if (focus) tabs[index].focus();
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => activate(i));
    tab.addEventListener("keydown", (e) => {
      let next;
      if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
      if (e.key === "ArrowLeft") next = (i + tabs.length - 1) % tabs.length;
      if (e.key === "Home") next = 0;
      if (e.key === "End") next = tabs.length - 1;
      if (next !== undefined) {
        e.preventDefault();
        activate(next, true);
      }
    });
  });
}
const concepts = [
  [
    "BusinessRule · 业务规则",
    "规则是一等对象，可以被业务步骤采用、由技术机制执行，并接受验证。",
    "CodeEntity —enforcesRule→ BusinessRule",
    "带宽约束规则",
    "在网络领域，明确带宽需求、链路可用带宽及比较语义。",
    "BandwidthRule ⊆ BusinessRule",
    "路径带宽必须满足要求",
    "本项目的规则约束路径选择，关联求值器设计与规则测试。",
    "求值器 —enforcesRule→ 最小带宽规则",
    "“表示”“执行规则”“验证”是不同的语义关系；建立关联，不自动证明业务规则已经实现。",
  ],
  [
    "BusinessAttribute · 业务属性",
    "业务属性描述业务对象的特征，可以有值域、单位和约束。",
    "BusinessObject —hasAttribute→ Attribute",
    "网络策略的最小带宽",
    "领域层明确带宽含义与单位，避免请求参数与链路指标语义不一致。",
    "MinimumBandwidth ⊆ BusinessAttribute",
    "本项目的带宽要求",
    "请求字段 minimumBandwidthMbps 表示该属性；字段与属性保留各自身份。",
    "请求字段 —represents→ 带宽要求",
    "业务属性、API 字段和数据库列不是同一个对象。映射说明技术表示；约束与证据检验其一致性。",
  ],
  [
    "StateTransition · 状态迁移",
    "行为建模包括状态、事件、守卫、执行步骤与失败路径。",
    "Transition —guardedBy→ BusinessRule",
    "网络策略部署生命周期",
    "从部署中到已部署，需要设备确认；部分失败还可能进入回滚过程。",
    "DeploymentTransition ⊆ StateTransition",
    "全部设备确认后完成部署",
    "Deploying → Deployed，由 AllTargetDevicesMustAcknowledge 守卫；此处只展示行为模型。",
    "迁移 —guardedBy→ 全部设备确认",
    "文档已有行为与状态建模。完整的执行语义、并发与补偿适配器仍需扩展；建模不等于自动生成行为。",
  ],
];
const conceptIds = [
  "concept-meta",
  "concept-meta-desc",
  "concept-meta-code",
  "concept-domain",
  "concept-domain-desc",
  "concept-domain-code",
  "concept-project",
  "concept-project-desc",
  "concept-project-code",
  "concept-note",
];
bindTabs("[data-concept]", (i) =>
  conceptIds.forEach((id, j) => setText(id, concepts[i][j])),
);
const slices = [
  {
    title: "带宽约束路径计算",
    description: "把规则的实现责任，连接到数据输入、核心求值与验证对象。",
    members: [
      ["契约入口", "PolicyRequest", "输入带宽要求"],
      ["数据来源", "LinkMetrics", "提供链路可用带宽"],
      ["执行规则", "ConstraintEvaluator", "判断链路是否满足约束"],
      ["验证规则", "规则测试", "检查满足与不足两种输入"],
    ],
  },
  {
    title: "带宽要求的技术表示",
    description:
      "同一业务属性在接口和算法中具有不同技术表示，需要显式映射与单位约定。",
    members: [
      ["API 表示", "minimumBandwidthMbps", "请求字段，单位 Mbps"],
      ["业务属性", "minimumBandwidth", "领域语义，不是代码字段"],
      ["算法输入", "minimumAvailableBandwidth", "路径约束输入"],
      ["验证映射", "API 契约测试", "验证输入与规则的衔接"],
    ],
  },
  {
    title: "过期数据拒绝与下发隔离",
    description: "失败行为跨越时间判断、配置、控制流和测试，不能只验证错误码。",
    members: [
      ["数据时间", "BandwidthSample.timestamp", "采样时间与有效性"],
      ["配置依赖", "topology.bandwidth.max-age", "允许的数据最大年龄"],
      ["行为边界", "下发调用路径", "过期分支不得到达下发入口"],
      ["负向验证", "零次下发测试", "确认拒绝后没有发生南向调用"],
    ],
  },
];
function bindChoices(selector, callback) {
  const buttons = [...document.querySelectorAll(selector)];
  buttons.forEach((button, i) =>
    button.addEventListener("click", () => {
      buttons.forEach((b, j) =>
        b.setAttribute("aria-pressed", String(i === j)),
      );
      callback(i);
    }),
  );
}
function showSlice(i) {
  const slice = slices[i];
  setText("slice-title", slice.title);
  setText("slice-description", slice.description);
  $("slice-members").replaceChildren(
    ...slice.members.map(([role, name, description]) => {
      const li = document.createElement("li");
      ["span", "button", "small"].forEach((tag, j) => {
        const el = document.createElement(tag);
        el.textContent = [role, name, description][j];
        if (tag === "button") {
          el.setAttribute("aria-label", `反向查看 ${name} 的业务责任`);
          el.addEventListener("click", () => {
            setText(
              "mapping-insight",
              `${name} —${role}→ ${slice.title}：${description}。这是当前所选设计切片中的业务责任，不代表已验证的实现。`,
            );
          });
        }
        li.append(el);
      });
      return li;
    }),
  );
  setText(
    "mapping-insight",
    "选择技术对象，可反向查看它在当前实现切片中承担的业务责任。",
  );
}
bindChoices("[data-slice]", showSlice);
showSlice(0);

const graphNodes = [
  {
    id: "rule",
    label: "最小带宽规则",
    type: "business",
    x: 20,
    y: 25,
    description: "路径上每条链路的可用带宽必须满足策略要求。",
  },
  {
    id: "fresh",
    label: "过期不得下发",
    type: "business",
    x: 325,
    y: 25,
    description: "数据新鲜度不仅影响错误码，也约束下发行为。",
  },
  {
    id: "test",
    label: "零次下发测试",
    type: "evidence",
    x: 630,
    y: 25,
    description: "验证过期数据被拒绝后，没有发生设备下发调用。",
  },
  {
    id: "api",
    label: "策略请求字段",
    type: "code",
    x: 20,
    y: 190,
    description: "请求模式与字段表达业务的带宽要求。",
  },
  {
    id: "eval",
    label: "路径约束求值器",
    type: "code",
    x: 325,
    y: 190,
    description: "求值器在路径计算过程中执行带宽及新鲜度约束。",
  },
  {
    id: "send",
    label: "设备下发入口",
    type: "code",
    x: 630,
    y: 190,
    description: "过期拒绝分支不能继续到达设备下发入口。",
  },
  {
    id: "metric",
    label: "链路带宽指标",
    type: "code",
    x: 20,
    y: 350,
    description: "数据包含可用带宽；新鲜度判断还需要采样时间。",
  },
  {
    id: "config",
    label: "数据过期阈值",
    type: "code",
    x: 325,
    y: 350,
    description: "配置数据最大允许年龄，影响新鲜度规则判断。",
  },
];
const baseEdges = [
  { from: "api", to: "eval", label: "输入" },
  { from: "eval", to: "metric", label: "读取", lx: 211, ly: 308 },
  { from: "eval", to: "send", label: "正常路径调用" },
];
const targetEdges = [
  ...baseEdges,
  { from: "eval", to: "rule", label: "执行规则", lx: 170, ly: 139 },
  { from: "eval", to: "fresh", label: "执行拒绝行为", lx: 472, ly: 135 },
  { from: "test", to: "fresh", label: "验证" },
  {
    from: "config",
    to: "fresh",
    label: "配置",
    path: "M485 380 C545 380 554 95 485 55",
    lx: 553,
    ly: 302,
  },
];
const stages = [
  {
    space: "CURRENT / 当前事实",
    title: "先看清系统现在有什么。",
    description:
      "从代码、契约和平台数据采集事实。本例基线包含策略入口、路径求值、链路指标与下发入口。",
    question: "哪些能力已存在？事实来源和采集范围是什么？",
    code: "Current：代码与契约采集\nPolicyRequest → ConstraintEvaluator\nConstraintEvaluator → LinkMetrics\nConstraintEvaluator → 下发入口",
    boundary: "此处是示意基线，不是对某个真实 SDN 仓库的扫描结果。",
    insight: "事实图必须有来源；未采集到，不等于不存在。",
    visible: ["api", "eval", "send", "metric"],
    status: () => ["existing", "已有 · 示意基线"],
  },
  {
    space: "BUSINESS + DESIRED / 目标模型",
    title: "将业务要求，表达为目标图。",
    description:
      "增加最小带宽规则、过期拒绝行为与验证要求；技术设计明确请求字段、求值器和配置的目标关系。",
    question: "完成需求后，哪些对象、关系和约束应当成立？",
    code: "业务规则：可用带宽 ≥ 要求带宽\n失败行为：数据过期 → 拒绝下发\n验收目标：南向下发调用次数 = 0",
    boundary: "虚线表示期望状态，不能写入当前事实图假装已经实现。",
    insight: "目标图中的关系是设计声明，需要实际实现与证据。",
    status: () => ["desired", "目标 · 尚待实现"],
  },
  {
    space: "CURRENT ↔ DESIRED / 语义差异",
    title: "对齐实体，再决定如何变化。",
    description:
      "已有下发入口可复用；请求、求值器和指标需要修改；规则、配置及负向测试需要新增或确认。",
    question: "复用什么、修改什么、新增什么，哪些映射还不确定？",
    code: "Reuse   下发入口\nModify  请求字段 / 求值器 / 指标\nAdd     带宽规则 / 过期阈值 / 测试",
    boundary:
      "示例分类依赖这份预设基线。真实对齐需要稳定身份、来源与人工确认，不是简单集合相减。",
    insight: "相似名称只提供对齐线索，不自动证明是同一实体。",
    status: (n) =>
      n.id === "send"
        ? ["existing", "复用 · 边界需检查"]
        : [
            "desired",
            ["api", "eval", "metric"].includes(n.id)
              ? "修改 · 差异提案"
              : "新增 · 差异提案",
          ],
  },
  {
    space: "PROPOSED + IMPACT → APPROVED",
    title: "将候选变化，变成批准的责任。",
    description:
      "按变化类型、传播前提和停止条件评审影响；明确实现义务与验证义务，再批准具体计划及内容版本。",
    question: "为什么需要这些变化？谁承担实现与验证责任？",
    code: "实现义务：过期分支终止下发\n验证义务：证明零次南向调用\n批准对象：计划 + 内容摘要\nImpact：候选须经规则与证据评估",
    boundary:
      "这里展示批准计划的结构，不代表已发生真实人工审批。图可达不自动等于 Confirmed 影响。",
    insight: "批准的是明确的变更范围，不是任意修改代码的授权。",
    status: () => ["planned", "计划 · 演示批准范围"],
  },
  {
    space: "APPROVED → IMPLEMENTATION",
    title: "图变更指导代码，执行器落实语义。",
    description:
      "批准任务携带设计、规则、技术栈和验收责任，通过受支持的转换适配器、Agent 或人工实现，保留来源与版本。",
    question: "哪些语义需要保留？用什么执行方式落实？",
    code: "# 伪代码：过期时必须阻断后续调用\nif bandwidth_data_is_stale:\n    reject_and_stop()\nelse:\n    evaluate_path_then_install()",
    boundary:
      "此 SDN 行为没有在网站中执行或生成。文本模型不会自行成为算法；仍需相应转换器和验证器。",
    insight: "生成源码不会自动产生实际事实，更不能自动证明需求满足。",
    status: () => ["planned", "实现任务 · 非执行结果"],
  },
  {
    space: "ACTUAL ↔ APPROVED / 实际对账",
    title: "代码存在，还要检验行为成立。",
    description:
      "假设字段和求值器已补齐，但过期后仍发生下发：节点存在性通过，负向行为验证仍失败，不能宣布需求完成。",
    question: "实际图与批准设计哪里一致？哪里仍有缺口？",
    code: "节点检查：字段 / 方法存在\n行为检查：过期后仍发生下发\n对账结论：示例中尚未满足\n后续动作：修复控制流并重新验证",
    boundary:
      "这是一条刻意设置缺口的对账示例，不是真实 SDN 测试结果。实际事实应由重采集和运行证据提供。",
    insight: "返回错误码不是充分证据；还需检查控制流与零次下发断言。",
    status: (n) =>
      ["fresh", "test", "send"].includes(n.id)
        ? ["gap", "! 行为缺口 · 示例"]
        : ["existing", "观察到 · 假设结果"],
  },
];
function showStage(i) {
  const stage = stages[i];
  ["space", "title", "description", "question", "code", "boundary"].forEach(
    (key) => setText(`stage-${key}`, stage[key]),
  );
  setText("stage-number", `${String(i + 1).padStart(2, "0")} / 06`);
  setText("evolution-insight", stage.insight);
  const nodes = graphNodes
    .filter((n) => !stage.visible || stage.visible.includes(n.id))
    .map((n) => {
      const [state, status] = stage.status(n);
      return { ...n, state, status };
    });
  renderGraph(
    "evolution-graph",
    nodes,
    i === 0
      ? baseEdges
      : targetEdges.map((edge) =>
          i === 5 && edge.from === "eval" && edge.to === "fresh"
            ? { ...edge, label: "! 拒绝行为未落实" }
            : edge,
        ),
    "evolution-insight",
    825,
    440,
  );
}
bindTabs("[data-stage]", showStage);
showStage(0);
const answers = [
  [
    "沿实现切片，看见共同责任。",
    "带宽规则 → 路径计算切片 → 请求字段 / 链路指标 / 求值器 / 规则测试",
    "业务责任跨越输入、数据、算法与验证。一个方法的链接，不能代表整个实现切片。",
    "这些是设计关联。确认已实现，需要实际采集与验证证据。",
  ],
  [
    "从条款引用，找到复核候选。",
    "规则变化 → 引用设计 / 生成规范 / 实现映射 / 验证规范 → 复核义务",
    "沿明确关系收集候选，再结合变化类型、兼容性、作用范围与证据判断影响。",
    "可达不等于确定影响；不能把所有相连对象都判定为必须修改。",
  ],
  [
    "对账不仅检查节点，也检查关系与行为。",
    "过期拒绝规则 → 失败分支 → 下发入口不可达 → 零次下发测试证据",
    "即使新字段和方法都存在，也必须验证规则确实被执行、失败行为符合要求。",
    "测试与实现关联只是线索。满足性判断必须绑定同模型、同快照、同范围的真实证据。",
  ],
];
bindChoices("[data-question]", (i) =>
  ["answer-title", "answer-path", "answer-description", "answer-limit"].forEach(
    (id, j) => setText(id, answers[i][j]),
  ),
);
const toggle = document.querySelector(".menu-toggle"),
  navigation = $("navigation");
function closeMenu(focus = false) {
  toggle.setAttribute("aria-expanded", "false");
  navigation.classList.remove("is-open");
  if (focus) toggle.focus();
}
toggle.addEventListener("click", () => {
  const expanded = toggle.getAttribute("aria-expanded") !== "true";
  toggle.setAttribute("aria-expanded", String(expanded));
  navigation.classList.toggle("is-open", expanded);
});
navigation
  .querySelectorAll("a")
  .forEach((a) => a.addEventListener("click", () => closeMenu()));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true")
    closeMenu(true);
});
window.matchMedia("(max-width: 820px)").addEventListener("change", (e) => {
  if (!e.matches) closeMenu();
});
