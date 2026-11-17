// The agent page: what an outside agent is told to run, as plain functions of what the service sends.

export const TOKEN_PLACEHOLDER = "<在下面创建令牌后填这里>";

/** The entry an MCP client puts in its settings to start the server as the person the token belongs to, from the installed package. `local` adds this machine's code path (the admin's, for a machine that has not installed the package). With a token the server offers the read-only tools unless told otherwise. */
export function connectConfig({ command, origin, token, local = false }) {
  const env = { ONTOPOC_URL: origin, ONTOPOC_TOKEN: token || TOKEN_PLACEHOLDER };
  return JSON.stringify({
    mcpServers: {
      ontopoc: {
        command: command.python,
        args: ["-m", command.module],
        env: local && command.local_src ? { PYTHONPATH: command.local_src, ...env } : env,
      },
    },
  }, null, 2);
}

/** A tool's first sentence: what it does, without the notes after it. */
export const firstSentence = (text) => text.split(/[。\n]/)[0];

/** What the skill folder holds, in one line. */
export const skillText = (skill) => `${skill.types} 个对象类型、${skill.relations} 条关系、${skill.views} 个视图、${skill.derived} 个派生属性；都是已确认的，没有数据行`;

export const SCOPES = [["read", "只读：读定义和数据行、提问；不能上传、确认、改"], ["all", "全部：和主人在页面上能做的一样"]];
export const EXPIRY_DAYS = [7, 30, 90, 365];

/** A token's reach in a word. */
export const scopeWord = (t) => (t.scope === "all" ? "全部" : "只读");

/** When a token ends: its day, or that it has ended already; a token made before expiry existed has no end. */
export const endText = (t) => (!t.expires_at ? "不过期" : t.expired ? "已过期" : t.expires_at.slice(0, 10));

/** A token's state in a word. */
export const tokenState = (t) => (t.revoked ? "已撤销" : t.expired ? "已过期" : t.last_used_at ? "在用" : "还没用过");

export const TOOL_GROUPS = ["读", "问", "建模", "确认", "导出", "其他"];

// What each tool does in one Chinese line, and the group it sits in: 读 reads what the team confirmed or the data, 问 asks a question of it, 建模 builds, 确认 records a person's judgement, 导出 hands files out.
const TOOLS = {
  describe_definitions: ["读", "团队已确认的业务定义：对象类型、关系、视图、派生属性"],
  list_unconfirmed: ["读", "还没确认的定义和原因（这些不能用来回答问题）"],
  read_derived_property: ["读", "读一个已确认的派生属性的值"],
  ontopoc_query: ["问", "用本体查询直接算一个数，不调模型，快"],
  ask: ["问", "用一句话问业务问题；写不出查询时用，会调模型"],
  health: ["其他", "服务是否在跑、有没有配模型"],
  list_runs: ["其他", "保存过的运行，新的在前"],
  run_overview: ["其他", "一次运行的概况：对象、关系、体检、稳定性"],
  preview_upload: ["建模", "看这几份文件会发给模型什么，不调模型"],
  build_ontology: ["建模", "上传文件并建本体，会调模型，要等"],
  list_objects: ["读", "本体里的对象：说明、来自哪些表、识别字段"],
  object_fields: ["读", "一个对象的属性：类型、长度、空值、来源"],
  object_rows: ["读", "一个对象在数据里的每个实例，一页 20 个"],
  list_relations: ["读", "本体里的关系：两端、含义、基数"],
  suggest_relations: ["建模", "数据里看到、本体里没有的关系，只是建议"],
  find_instances: ["读", "按名称或编号找数据里的某个对象"],
  instance_neighbourhood: ["读", "一个对象和与它相连的对象"],
  list_rules: ["读", "数据里找到的规则和已采纳的规则"],
  set_rules: ["确认", "采纳或不要规则"],
  draft_form: ["建模", "让模型起草对象的中文名和描述，会调模型"],
  save_form: ["建模", "保存对象表单"],
  export_forms: ["导出", "按对象表单导出 CSV"],
  export_mermaid: ["导出", "导出组织图（Mermaid）"],
  export_ttl: ["导出", "按 W3C 标准导出 Turtle"],
  export_pipeline_spec: ["导出", "生成交给搭管道的人的加工需求单"],
  data_layout: ["读", "上传的每张表：行数、列类型、空值"],
  data_check: ["读", "数据体检：七项检查是否通过"],
  ask_question: ["问", "用数据回答一个业务问题，会调模型，慢且花钱"],
  list_questions: ["问", "模型出的题、人问过的题和验收问题"],
  confirm_derived: ["确认", "确认一个派生指标"],
  fix_question: ["确认", "把问过的题固定为验收问题"],
  drop_filter: ["问", "去掉模型给一道题加的条件并重算"],
  confirm_ontology: ["确认", "保存人对本体的逐项判断"],
  compare_reference: ["读", "拿参考本体和这次的本体对照"],
  get_card: ["读", "口径卡：数据是什么意思"],
  save_card: ["确认", "记下客户对口径卡的答复"],
  list_proposed_views: ["读", "别人提出、等你确认的视图"],
  confirm_proposed_view: ["确认", "确认别人提出的一个视图"],
  find_name_variants: ["建模", "找同一个东西的不同写法，只是建议，会调模型"],
};

/** A tool's group and Chinese line; `known` is false for a tool this page has no line for. */
export function toolInfo(name) {
  const [group, line] = TOOLS[name] ?? ["其他", ""];
  return { group, line, known: name in TOOLS };
}

/** Tools sorted into the groups, in the group order; a tool keeps its place inside its group and an empty group is left out. */
export function groupTools(tools) {
  return TOOL_GROUPS.map((group) => ({ group, tools: tools.filter((t) => toolInfo(t.name).group === group) })).filter((g) => g.tools.length);
}
