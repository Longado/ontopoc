// The agent page: what an outside agent is told to run, as plain functions of what the service sends.
import { t } from "./i18n/index.js";

/** The placeholder shown in the connect block until a token has been made. */
export const tokenPlaceholder = () => t("agents.placeholder");

/** The entry an MCP client puts in its settings to start the server as the person the token belongs to, from the installed package. `local` adds this machine's code path (the admin's, for a machine that has not installed the package). With a token the server offers the read-only tools unless told otherwise. */
export function connectConfig({ command, origin, token, local = false }) {
  const env = { ONTOPOC_URL: origin, ONTOPOC_TOKEN: token || tokenPlaceholder() };
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

/** A tool's first sentence: what it does, without the notes after it (a full stop, a Chinese full stop or a line break ends it). */
export const firstSentence = (text) => text.split(/[\u3002\n]|\.\s/)[0].replace(/\.$/, "");

/** What the skill folder holds, in one line. */
export const skillText = (skill) => t("agents.skill", skill);

/** The permissions a token can be given: [[key, text]]. */
export const scopes = () => [["read", t("agents.scope.read")], ["all", t("agents.scope.all")]];
export const EXPIRY_DAYS = [7, 30, 90, 365];

/** A token's reach in a word. */
export const scopeWord = (tok) => t(tok.scope === "all" ? "agents.scopeWord.all" : "agents.scopeWord.read");

/** When a token ends: its day, or that it has ended already; a token made before expiry existed has no end. */
export const endText = (tok) => (!tok.expires_at ? t("agents.end.never") : tok.expired ? t("agents.end.expired") : tok.expires_at.slice(0, 10));

/** A token's state in a word. */
export const tokenState = (tok) => t(tok.revoked ? "agents.state.revoked" : tok.expired ? "agents.state.expired" : tok.last_used_at ? "agents.state.inUse" : "agents.state.unused");

export const TOOL_GROUPS = ["read", "ask", "model", "confirm", "export", "other"];

// The group each tool sits in: read reads what the team confirmed or the data, ask asks a question of it, model builds, confirm records a person's judgement, export hands files out.
// The line that says what a tool does is the dictionary's agents.tool.<name>.
const TOOLS = {
  describe_definitions: "read", list_unconfirmed: "read", read_derived_property: "read", definition_standing: "read", ontopoc_query: "ask", ask: "ask", health: "other", list_runs: "other", run_overview: "other",
  preview_upload: "model", build_ontology: "model", list_objects: "read", object_fields: "read", object_rows: "read", list_relations: "read", suggest_relations: "model",
  find_instances: "read", instance_neighbourhood: "read", list_rules: "read", set_rules: "confirm", draft_form: "model", save_form: "model", export_forms: "export",
  export_mermaid: "export", export_ttl: "export", export_pipeline_spec: "export", data_layout: "read", data_check: "read", ask_question: "ask", list_questions: "ask",
  confirm_derived: "confirm", fix_question: "confirm", drop_filter: "ask", confirm_ontology: "confirm", compare_reference: "read", get_card: "read", save_card: "confirm",
  list_proposed_views: "read", confirm_proposed_view: "confirm", find_name_variants: "model",
};

/** A tool's group and its line in the current language; `known` is false for a tool this page has no line for. */
export function toolInfo(name) {
  const known = name in TOOLS;
  return { group: TOOLS[name] ?? "other", line: known ? t(`agents.tool.${name}`) : "", known };
}

/** Tools sorted into the groups, in the group order; a tool keeps its place inside its group and an empty group is left out. Each group carries its label and hint. */
export function groupTools(tools) {
  return TOOL_GROUPS.map((group) => ({ group, label: t(`agents.group.${group}`), hint: t(`agents.hint.${group}`), tools: tools.filter((tool) => toolInfo(tool.name).group === group) })).filter((g) => g.tools.length);
}
