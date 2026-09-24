import assert from "node:assert/strict";
import test from "node:test";

import { handoffLines, isOrg, orgPlaces, orgTree, roleRows } from "./orgModel.js";

const entity = (key, org_type, label, definition = "", when = null) => ({ key, org_type, label, definition, when, evidence: [`${label} 的原文`] });
const fact = (kind, from, to, extra = {}) => ({ key: `${kind}_${from}_${to}`, kind, from, to, label: kind, what: null, when: null, evidence: ["原文"], ...extra });

const run = (extra = {}) => ({
  mode: "org",
  file: { name: "palantir.md", kind: "document" },
  ontology: {
    object_types: [
      entity("bd", "unit", "业务拓展与部署"), entity("pd", "unit", "产品研发"),
      entity("echo", "role", "Echo", "业务定义、工作流与采用"), entity("delta", "role", "Delta", "技术实现与部署"),
      entity("dev", "role", "Dev"), entity("ryan", "person", "Ryan Beiermeister"),
      entity("generalize", "duty", "通用化与版本演进"), entity("p1", "period", "第一阶段", "", "2003—2015"),
      entity("lonely", "unit", "独立运营组"),
    ],
    relations: [
      fact("part_of", "echo", "bd"), fact("part_of", "delta", "bd"), fact("part_of", "dev", "pd"),
      fact("holds", "ryan", "dev", { when: "2019年" }),
      fact("hands_to", "echo", "delta", { what: "业务目标与约束" }),
      fact("hands_to", "delta", "dev", { what: "功能论证与候选代码", when: "2019年" }),
      fact("works_with", "dev", "echo", { what: "路线协调" }),
      fact("responsible_for", "dev", "generalize"),
    ],
    open: [{ text: "争议由谁最终裁决", evidence: "公开材料仍未说明" }],
  },
  evaluation: { periods: { periods: [{ key: "p1", name: "第一阶段", from: 2003, to: 2015, facts: [] }], undated: [] } },
  ...extra,
});

test("an organisation run is told apart from an ordinary document", () => {
  assert.equal(isOrg(run()), true);
  assert.equal(isOrg({ file: { kind: "document" }, ontology: {}, evaluation: {} }), false);
});

test("the module's places carry what is in each, and an empty one is left out", () => {
  assert.deepEqual(orgPlaces(run()), [["tree", "组织树", "7"], ["flow", "协作交接", "3"], ["roles", "角色", "3"], ["periods", "时期", "1"], ["open", "未说明", "1"]]);
  const bare = run({ ontology: { ...run().ontology, open: [] }, evaluation: { periods: { periods: [], undated: [] } } });
  assert.deepEqual(orgPlaces(bare).map(([k]) => k), ["tree", "flow", "roles"]);
});

test("the tree puts roles under their unit and people under the role they hold, and says who hangs loose", () => {
  const { roots, loose } = orgTree(run());
  assert.deepEqual(roots.map((n) => [n.label, n.children.map((c) => c.label)]), [["业务拓展与部署", ["Echo", "Delta"]], ["产品研发", ["Dev"]]]);
  assert.deepEqual(roots[1].children[0].children.map((c) => c.label), ["Ryan Beiermeister"]);
  assert.deepEqual(loose, ["独立运营组"]);   // nothing says where it belongs
});

test("每条交接写明谁交给谁、交了什么，协作是双向的", () => {
  assert.deepEqual(handoffLines(run()), [
    { key: "hands_to_echo_delta", from: "Echo", to: "Delta", what: "业务目标与约束", when: null, both: false },
    { key: "hands_to_delta_dev", from: "Delta", to: "Dev", what: "功能论证与候选代码", when: "2019年", both: false },
    { key: "works_with_dev_echo", from: "Dev", to: "Echo", what: "路线协调", when: null, both: true },
  ]);
});

test("the role table is what a report prints: the role, its duties and who it works with", () => {
  const rows = roleRows(run());
  assert.deepEqual(rows.find((r) => r.label === "Dev"), {
    key: "dev", label: "Dev", note: "", unit: "产品研发", duties: ["通用化与版本演进"],
    people: ["Ryan Beiermeister"], partners: ["Delta", "Echo"],
  });
  assert.deepEqual(rows.map((r) => r.label), ["Echo", "Delta", "Dev"]);
});
