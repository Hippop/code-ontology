"use strict";

// Presentation-only examples: no backend calls and no simulated live verification.
const steps = [
  {
    tag: "METAMODEL / 语义底座",
    title: "先约定，怎样描述软件开发。",
    description:
      "元模型定义业务概念、行为条款、设计决策和证据等类型。具体项目使用这些类型建模，再通过约束检查模型是否完整。",
    nodes: ["元模型", "项目模型", "技术表示"],
    file: "domain-model.ttl · 简化示意",
    code: "TaskConcept rdfs:subClassOf BusinessConcept .\n\ntask a TaskConcept ;\n  hasAttribute priority .\n\npriority a BusinessAttribute .",
    note: "模型中的 Task 节点是业务概念的表示，不是某个用户创建的任务记录。",
  },
  {
    tag: "CONTRACT / 行为与约束",
    title: "将业务要求，拆成可检查的条款。",
    description:
      "值域条款规定允许值与默认值，行为条款表达前置条件、后置条件及失败行为。验收条件再明确：观察什么结果，才算满足需求。",
    nodes: ["需求", "语义契约", "验收条件"],
    file: "priority-contract.ttl · 简化示意",
    code: 'valueClause a ValueConstraint ;\n  allowedValue "low", "medium", "high" ;\n  defaultValue "medium" .\n\nbehaviorClause a BehaviorClause ;\n  failureBehavior "拒绝非法优先级" .',
    note: "当前一般行为仍以文本表达。任意自然语言不能自动变成算法；本例的拒绝行为由固定适配器实现。",
  },
  {
    tag: "DESIGN / 明确技术落点",
    title: "让每个设计选择，都能回到业务。",
    description:
      "设计决策选择 Python 字符串枚举与构造时校验。生成规范进一步关联目标设计、转换规则、技术栈、输出位置和需要保留的条款。",
    nodes: ["业务属性", "目标设计", "生成规范"],
    file: "generation-specification · 关系示意",
    code: "priority 属性\n  → Python Task.priority\n  → Literal + 构造时校验\n\n批准的实现任务\n  → python-enum-dataclass-v1",
    note: "生成前检查模型约束与批准范围。批准一个版本，并不等于已经验证这个版本。",
  },
  {
    tag: "GENERATION / 受控转换",
    title: "把支持的语义，变成实际代码。",
    description:
      "适配器读取结构化输入，生成允许值、字段默认值和运行时检查。源码同时记录生成规范、规则、保留条款和模型输入摘要。",
    nodes: ["生成规范", "适配器", "Python 代码"],
    file: "src/task.py · 核心代码节选",
    code: "@dataclass(frozen=True)\nclass Task:\n    priority: Literal['high', 'low', 'medium'] = 'medium'\n\n    def __post_init__(self):\n        if self.priority not in ALLOWED_PRIORITY:\n            raise ValueError('invalid priority')",
    note: "代码为讲解节选，省略导入、允许值集合与追溯常量。当前仅支持限定 Python 适配器，并非通用业务生成器。",
  },
  {
    tag: "EVIDENCE / 可验证交付",
    title: "不是输出文件，而是取得证据。",
    description:
      "固定验收程序在独立进程中真实执行，记录退出码、测试结果和摘要。证据支持满足性判断及义务关闭，后续查询再检查证据适用性。",
    nodes: ["真实验收", "版本证据", "交付判断"],
    file: "report.json · 历史验收摘要",
    code: '{\n  "testCases": 8,\n  "passedCases": 8,\n  "exitCode": 0,\n  "filesUnchanged": true,\n  "recordedStatus": "Ready"\n}',
    note: "来自 2026-09-08 的限定切片。五项满足性判断共享一份报告；八项测试通过不等于所有业务行为均被证明。",
  },
];

const tabs = [...document.querySelectorAll('[role="tab"]')];
const panel = document.getElementById("method-panel");
function showStep(index, focus = false) {
  const step = steps[index];
  if (!step) return;
  tabs.forEach((tab, i) => {
    tab.setAttribute("aria-selected", String(i === index));
    tab.tabIndex = i === index ? 0 : -1;
  });
  panel.setAttribute("aria-labelledby", `step-${index}`);
  const values = {
    "panel-tag": step.tag,
    "panel-title": step.title,
    "panel-description": step.description,
    "mini-left": step.nodes[0],
    "mini-middle": step.nodes[1],
    "mini-right": step.nodes[2],
    "code-filename": step.file,
    "method-code": step.code,
    "panel-note": step.note,
    "panel-count": `${String(index + 1).padStart(2, "0")} / 05`,
  };
  Object.entries(values).forEach(([id, value]) => {
    document.getElementById(id).textContent = value;
  });
  if (focus) tabs[index].focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => showStep(index));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (["ArrowDown", "ArrowRight"].includes(event.key))
      next = (index + 1) % tabs.length;
    if (["ArrowUp", "ArrowLeft"].includes(event.key))
      next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      showStep(next, true);
    }
  });
});

const toggle = document.querySelector(".menu-toggle");
const navigation = document.getElementById("navigation");
function closeMenu(returnFocus = false) {
  toggle.setAttribute("aria-expanded", "false");
  navigation.classList.remove("is-open");
  if (returnFocus) toggle.focus();
}
toggle.addEventListener("click", () => {
  const expanded = toggle.getAttribute("aria-expanded") !== "true";
  toggle.setAttribute("aria-expanded", String(expanded));
  navigation.classList.toggle("is-open", expanded);
});
navigation
  .querySelectorAll("a")
  .forEach((link) => link.addEventListener("click", () => closeMenu()));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true")
    closeMenu(true);
});
const compactScreen = window.matchMedia("(max-width: 820px)");
function updateLayout() {
  document
    .querySelector('[role="tablist"]')
    .setAttribute(
      "aria-orientation",
      compactScreen.matches ? "horizontal" : "vertical",
    );
  if (!compactScreen.matches) closeMenu();
}
compactScreen.addEventListener("change", updateLayout);
updateLayout();
