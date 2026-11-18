// The workspace service, one function per request. A refusal arrives as the service's own sentence, in the page's language (Accept-Language).
import { getLocale } from "./i18n/index.js";

// the page that holds the sign-in decides what a 401 means: it shows the sign-in form
let onSignedOut = () => {};
export const whenSignedOut = (fn) => {
  onSignedOut = fn;
};

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { cache: "no-store", ...options, headers: { "Accept-Language": getLocale() === "zh" ? "zh-CN" : "en", ...(options.headers ?? {}) } });
  } catch {
    throw new Error(getLocale() === "zh" ? "连不上本机服务，请确认服务已经启动后再试" : "Can't reach the OntoPoc service. Check that it is running, then try again.");
  }
  const body = await response.json().catch(() => null);
  if (response.status === 401 && path !== "/api/auth/login") onSignedOut();   // the session ended (or never was): back to the sign-in form
  if (!response.ok) {
    throw Object.assign(new Error(body?.error || (getLocale() === "zh" ? `服务返回了 ${response.status}` : `The service answered ${response.status}`)), {
      code: response.status, files: body?.files, readers: body?.readers, setup: body?.setup, mustChange: body?.must_change, keyCheck: body?.key_check, offer: body?.offer,
    });
  }
  return body;
}

export const WORKSPACE_CHANGED = "workspace-changed";   // what the navigation listens for, to count what waits for this person again

const send = (path, payload = {}) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then((body) => {
    if (path.startsWith("/api/workspace/")) window.dispatchEvent(new Event(WORKSPACE_CHANGED));
    return body;
  });

// accounts
export const getMe = () => request("/api/auth/me");
export const signIn = (username, password) => send("/api/auth/login", { username, password });
export const signOut = () => send("/api/auth/logout");
export const changePassword = (current, next) => send("/api/auth/password", { current, new: next });
export const getTokens = () => request("/api/auth/tokens").then((b) => b.tokens);
export const createToken = (label) => send("/api/auth/tokens", { label });
export const revokeToken = (id) => send("/api/auth/tokens/revoke", { id });
export const getUsers = () => request("/api/users").then((b) => b.users);
export const createUser = (fields) => send("/api/users", fields);
export const updateUser = (id, fields) => send("/api/users/update", { id, ...fields });
export const setUserDisabled = (id, disabled) => send("/api/users/disable", { id, disabled });
export const resetUserPassword = (id, password) => send("/api/users/reset-password", { id, password });
export const getTwoPerson = () => request("/api/settings").then((b) => b.two_person);
export const setTwoPerson = (enabled) => send("/api/settings", { two_person: enabled }).then((b) => b.two_person);

export const getDatasets = () => request("/api/workspace/datasets").then((b) => b.datasets);

/** {tasks, unreadable}: the tasks, and how many job records the service could not read. */
export const getTasks = () => request("/api/workspace/tasks");

const datasetPath = (name, version, extra = "") => {
  const query = [version ? `version=${version}` : "", extra].filter(Boolean).join("&");
  return `/api/workspace/datasets/${encodeURIComponent(name)}${query ? `?${query}` : ""}`;
};

export const getDataset = (name, version = null, page = 1) => request(datasetPath(name, version, page > 1 ? `page=${page}` : ""));

/** The address that downloads one version as a CSV. */
export const csvHref = (name, version = null) => datasetPath(name, version, "format=csv");

/** Removes a dataset with all its versions; refused (409, with `readers`) while something reads it. */
export const deleteDataset = (name, who) =>
  request("/api/workspace/datasets/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, who: who.trim() }) });

/** What an upload would send back to "needs another look", worked out on a copy: {moved: [{element, kind, title, reason}], datasets}. Nothing is written. */
export const previewUpload = (payload) =>
  request("/api/workspace/datasets/upload/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });

export const uploadDatasets = (payload) =>
  request("/api/workspace/datasets/upload", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then((b) => b.results);

// object types
const typePath = (id, tail = "") => `/api/workspace/types/${encodeURIComponent(id)}${tail}`;
export const getTypes = () => request("/api/workspace/types").then((b) => b.types);
/** {types, hidden}: the types this person may open, and how many more exist that they may not (a count, never names). */
export const getTypeList = () => request("/api/workspace/types");
export const getType = (id) => request(typePath(id));
export const getTypeObjects = (id, page = 1) => request(typePath(id, `/objects${page > 1 ? `?page=${page}` : ""}`));
export const getTypeLog = (id) => request(typePath(id, "/log")).then((b) => b.log);
/** Checks a key before anything is saved: {rows_checked, warnings}; a key that repeats is refused with `keyCheck` (the repeated values) on the error. */
export const checkTypeKey = (dataset, key) => send("/api/workspace/types/key-check", { dataset, key });
export const createType = (payload) => send("/api/workspace/types", payload);
export const updateType = (payload) => send("/api/workspace/types/update", payload);
export const proposeMeanings = (id, column, values) => send("/api/workspace/types/meanings", { id, column, values });
/** Confirms the type (without `column`) or the meanings of one code column, as the version the person saw and with the `seen` the service sent (the data they read). */
export const confirmType = (id, version, seen, column = null) => send("/api/workspace/types/confirm", { id, version, seen, ...(column ? { column } : {}) });
/** Asks the model for types. It can take up to two minutes: there is no timeout here, the dialog says it is waiting. */
/** {data: {dataset, version, uploaded_at, who, link}, used_by: [{kind, label, count, items}]}: the data the type stands on and what stands on it. */
export const getTypeUses = (id) => request(typePath(id, "/uses"));
/** {nodes, edges, rows_limited}: the types and relations this person may see; the lineage adds datasets, views, actions and their own saved answers. */
export const getRelationGraph = () => request("/api/workspace/graph/relations");
export const getLineageGraph = () => request("/api/workspace/graph/lineage");
export const getTypeViews = (id) => request(typePath(id, "/views"));
export const createView = (payload) => send("/api/workspace/types/views", payload);
export const confirmView = (id, version, seen, newValues = undefined) => send("/api/workspace/types/views/confirm", { id, version, seen, ...(newValues?.length ? { new_values: newValues } : {}) });

// derived properties of a type. A try (试算, 校验, the path's shape) writes nothing, so it does not tell the navigation to count again.
const tryDerived = (tail, payload) => request(`/api/workspace/types/derived${tail}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
/** {derived: [...], form}: the properties of this type with the trial on the data as it is now, and what a form for a new one offers (null for a viewer). */
export const getTypeDerived = (id) => request(typePath(id, "/derived"));
export const getDerivedLog = (id, name) => request(typePath(id, `/derived/${encodeURIComponent(name)}/log`));
export const createDerived = (payload) => send("/api/workspace/types/derived", payload);
export const updateDerived = (payload, version) => send("/api/workspace/types/derived/update", { ...payload, version });
export const confirmDerived = (type, englishName, version, seen) => send("/api/workspace/types/derived/confirm", { type, english_name: englishName, version, seen });
export const trialDerived = (payload) => tryDerived("/trial", payload);
export const shapeDerived = (type, path) => tryDerived("/shape", { type, path });
export const checkDerivedExpression = (type, expression) => tryDerived("/expression", { type, expression });
export const suggestTypes = (datasets, purpose) => send("/api/workspace/types/suggest", { datasets, purpose });
/** The assistant's draft of the meanings of one type's code columns: one model call over counts, nothing is saved. */
export const draftMeanings = (id) => send("/api/workspace/types/meanings-draft", { id });

// actions: the definitions of one type with their parameters, one action with its records and log, submitting, approving
const actionPath = (name, tail = "") => `/api/workspace/actions/${encodeURIComponent(name)}${tail}`;
export const getActions = (type) => request(`/api/workspace/actions?type=${encodeURIComponent(type)}`);
export const getAction = (name) => request(actionPath(name));
export const createAction = (payload) => send("/api/workspace/actions", payload);
export const confirmAction = (id, version) => send("/api/workspace/actions/confirm", { id, version });
/** `key` {column: value} names the object, `params` {column: new value}. The record waits in 待确认 for another builder. */
export const submitAction = (action, key, params, reason) => send("/api/workspace/actions/submit", { action, key, params, reason });
export const decideRecord = (id, decision, note = "") => send("/api/workspace/actions/decide", { id, decision, note });
export const withdrawRecord = (id) => send("/api/workspace/actions/withdraw", { id });
export const undoRecord = (id) => send("/api/workspace/actions/undo", { id });

// pipelines. A try (preview, summary, expression trial) writes nothing, so it does not tell the navigation to count again.
const pipelinePath = (name, tail = "") => `/api/workspace/pipelines/${encodeURIComponent(name)}${tail}`;
const tryOut = (path, payload) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const getPipelines = () => request("/api/workspace/pipelines").then((b) => b.pipelines);
/** The operators by category, the functions by group, the aggregations, the join kinds: what the editors list. */
export const getPipelineOptions = () => request("/api/workspace/pipelines/options");
export const getPipeline = (name) => request(pipelinePath(name));
export const getPipelineVersions = (name, from = null, to = null) => request(pipelinePath(name, `/versions${from && to ? `?from=${from}&to=${to}` : ""}`));
export const getPipelineRuns = (name) => request(pipelinePath(name, "/runs")).then((b) => b.runs);
export const getPipelineRun = (name, id) => request(pipelinePath(name, `/runs/${id}`));
export const getPipelineLog = (name) => request(pipelinePath(name, "/log")).then((b) => b.log);
export const createPipeline = (name, description, spec) => send("/api/workspace/pipelines", { name, description, spec });
/** Saves a changed definition as the version the person had open (409 when it moved since). */
export const savePipeline = (name, version, spec, receipt = null) => send("/api/workspace/pipelines/update", { id: name, version, spec, ...(receipt ? { draft_receipt: receipt } : {}) });
export const runPipeline = (name) => send("/api/workspace/pipelines/run", { id: name });
/** Confirms what the person looked at: the definition version and the input versions they saw. */
export const confirmPipeline = (name, version, inputs) => send("/api/workspace/pipelines/confirm", { id: name, version, seen: { inputs } });
export const reviewPipeline = (name) => tryOut("/api/workspace/pipelines/review", { id: name });
/** Every node's counts for the cards, from the draft as it is now. */
export const pipelineSummary = (name, spec) => tryOut("/api/workspace/pipelines/summary", { id: name, spec });
export const previewNode = (name, spec, node, operator = null) => tryOut("/api/workspace/pipelines/preview", { id: name, spec, node, ...(operator == null ? {} : { operator }) });
export const operatorColumns = (name, spec, step, operator) => tryOut("/api/workspace/pipelines/columns", { id: name, spec, step, operator });
export const checkExpression = (name, spec, step, operator, expression, type) => tryOut("/api/workspace/pipelines/expression/check", { id: name, spec, step, operator, expression, ...(type ? { type } : {}) });
export const trialExpression = (name, spec, step, operator, expression) => tryOut("/api/workspace/pipelines/expression/trial", { id: name, spec, step, operator, expression });
export const guessDateFormat = (examples) => tryOut("/api/workspace/pipelines/format-guess", { examples });

// the AI step: where it stands, 试跑, the sample review, the kept answers; and the assistant. The ones that call the model can take a while: there is no timeout here.
const llmPath = (route) => `/api/workspace/pipelines/llm/${route}`;
export const llmState = (name, spec, step) => tryOut(llmPath("state"), { id: name, spec, step });
/** `body`: {mode: "sample" | "rows" | "values", n?, seed?, rows?, values?, exclude_labelled?}. Calls the model. */
export const llmTrial = (name, spec, step, body) => tryOut(llmPath("trial"), { id: name, spec, step, ...body });
/** `labels`: [{fields, expected}]; `remove`: row hashes. The expected answers of rows, kept with the node. */
export const llmLabel = (name, spec, step, labels, remove = []) => send(llmPath("label"), { id: name, spec, step, labels, remove });
/** Runs the labelled rows through the step as it is now and counts the matches. Calls the model. */
export const llmReview = (name, spec, step) => send(llmPath("review"), { id: name, spec, step });
export const llmClearCache = (name, spec, step) => send(llmPath("clear-cache"), { id: name, spec, step });
/** A sentence into a filter (kind "filter") or a calculated column (kind "calc"). `more`: {raw, answers} when a question was answered. */
export const aiParse = (name, spec, step, operator, kind, text, more = {}) => tryOut("/api/workspace/pipelines/ai/parse", { id: name, spec, step, operator, kind, text, ...more });
/** A draft of steps over the selected nodes. `more`: {raw, answers} when a question was answered. Nothing is saved. */
export const aiDraft = (name, spec, selected, text, more = {}) => tryOut("/api/workspace/pipelines/ai/draft", { id: name, spec, selected, text, ...more });
export const aiExplain = (name, spec, selected) => tryOut("/api/workspace/pipelines/ai/explain", { id: name, spec, selected });

// relations, the 待确认 queue, who sees which type
const relationPath = (id, tail = "") => `/api/workspace/relations/${encodeURIComponent(id)}${tail}`;
export const getRelations = () => request("/api/workspace/relations").then((b) => b.relations);
export const getRelation = (id) => request(relationPath(id));
export const getRelationLog = (id) => request(relationPath(id, "/log")).then((b) => b.log);
/** The types the person may see with their dataset's columns: what a relation's two ends are picked from. */
export const getRelationForm = () => request("/api/workspace/relation-form").then((b) => b.types);
export const createRelation = (payload) => send("/api/workspace/relations", payload);
export const updateRelation = (payload) => send("/api/workspace/relations/update", payload);
/** How many rows a relation not yet saved would connect: {rows, matched, unmatched, empty, samples, many_name, one_name}. Writes nothing. */
export const previewRelation = (payload) => send("/api/workspace/relations/preview", payload);
/** {items, count}: everything waiting to be judged that this person may see, and how many of it they may confirm now. */
export const getQueue = () => request("/api/workspace/queue");
/** Only how many items this person may confirm now: read from the states, cheap enough to ask on every page. */
export const getQueueCount = () => request("/api/workspace/queue?count=1").then((b) => b.count);
/** Confirms one queue item as the version the person saw, with the item's `seen` (what it showed of the data: the connected-row counts of a relation, the version and rows of a type's dataset). */
export const confirmItem = (element, version, seen = undefined) => send("/api/workspace/queue/confirm", { element, version, ...(seen ? { seen } : {}) });
/** The items one version of a dataset moved, in the order they are confirmed in, each with what its own screen shows. */
export const getQueueGroup = (dataset, version) => request(`/api/workspace/queue/group?dataset=${encodeURIComponent(dataset)}&version=${version}`);
/** Confirms them in one action: `items` [{element, version, seen, new_values?}], what the person looked at. All or nothing. */
export const confirmGroup = (dataset, version, items) => send("/api/workspace/queue/confirm-group", { dataset, version, items });
export const sendBack = (element, version, reason) => send("/api/workspace/queue/send-back", { element, version, reason });
export const getPermissions = () => request("/api/workspace/permissions");
/** `visibleTo`: "everyone" or the ids of the people who may see the type. */
export const setPermission = (type, visibleTo) => send("/api/workspace/permissions", { type, visible_to: visibleTo });
/** `rules`: the whole list of one type, [{column, value, user_ids}]: these people see the rows where the property equals the value. */
export const setRowRules = (type, rules) => send("/api/workspace/row-rules", { type, rules });
export const getNotices = () => request("/api/workspace/notices");
export const readNotices = (fields) => send("/api/workspace/notices/read", fields);
export const setActionNotify = (action, recipients) => send("/api/workspace/actions/notify", { action, recipients });
export const setColumnAccess = (type, column, visibleTo) => send("/api/workspace/column-access", { type, column, visible_to: visibleTo });

// Q&A: the scope line with the person's own history, one saved answer as it stands now, a new question
export const getAsk = () => request("/api/workspace/ask");
export const getAnswer = (id) => request(`/api/workspace/ask/${id}`);
/** The model works out the query: it can take up to a minute, there is no timeout here. */
export const askQuestion = (question) => send("/api/workspace/ask", { question });
/** A builder's switch on one property: its values are not sent to the model that reads a question. */
export const setValuesHidden = (id, column, hide) => send("/api/workspace/types/privacy", { id, column, hide_values: hide });

// live sources and schedules. The password goes out in createSource / updateSource and never comes back: the service answers has_password.
const sourcePath = (name, tail = "") => `/api/workspace/sources/${encodeURIComponent(name)}${tail}`;
export const getSources = () => request("/api/workspace/sources").then((b) => b.sources);
export const getSource = (name) => request(sourcePath(name));
/** The tables in the database now, over a live connection (it can take a few seconds). */
export const getSourceTables = (name) => request(sourcePath(name, "/tables")).then((b) => b.tables);
export const createSource = (fields) => send("/api/workspace/sources", fields);
export const updateSource = (fields) => send("/api/workspace/sources/update", fields);
export const deleteSource = (name) => send("/api/workspace/sources/delete", { name });
/** Connects, lists the tables with row counts, checks whether the account can write: {status, note, tables, can_write}. A failed connection is a result, not an error. */
export const testSource = (name) => send("/api/workspace/sources/test", { name });
/** Reads a table as a dataset: {source, table, name?, mode?, key_columns?}. Returns the run: {status, rows, version, error, detail}. */
export const pullTable = (fields) => send("/api/workspace/sources/pull", fields).then((b) => b.run);
export const refreshDataset = (dataset) => send("/api/workspace/sources/refresh", { dataset }).then((b) => b.run);
export const getSchedules = () => request("/api/workspace/schedules").then((b) => b.schedules);
export const getScheduleRuns = (id) => request(`/api/workspace/schedules/${id}/runs`).then((b) => b.runs);
export const createSchedule = (fields) => send("/api/workspace/schedules", fields);
export const updateSchedule = (fields) => send("/api/workspace/schedules/update", fields);
export const deleteSchedule = (id) => send("/api/workspace/schedules/delete", { id });

// the use layer: the explorer, boards, and what an outside agent may call. Reads that are POSTs only because the query is long write nothing, so they do not tell the navigation to count again.
const readPost = (path, payload) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
/** What the explorer offers on a type: its fields (with the values a filter can be picked from), the views, the relations a pivot goes through. */
export const getExploreMeta = (type) => request(`/api/workspace/explore/${encodeURIComponent(type)}`);
export const exploreTable = (query, page = 1) => readPost("/api/workspace/explore/table", { query, page });
export const exploreChart = (query, chart) => readPost("/api/workspace/explore/chart", { query, chart });
/** OntoPoc Query: run a text as this person (no model, nothing kept). A text that cannot be read is an error saying what can be written. */
export const runQuery = (text, params) => readPost("/api/workspace/query", params ? { text, params } : { text });
export const getExploreObject = (type, n) => request(`/api/workspace/explore/${encodeURIComponent(type)}/object/${n}`);

export const getBoards = () => request("/api/workspace/dashboards");
export const getBoard = (id) => request(`/api/workspace/dashboards/${id}`);
/** The board worked out for this person; `bar` is the filter bar's picks {field: value}; `params` the values typed for its parameters {name: value}. */
export const getBoardData = (id, bar = {}, params = {}) => readPost("/api/workspace/dashboards/data", { id, bar, params });
export const previewBoard = (spec, bar = {}, params = {}) => readPost("/api/workspace/dashboards/preview", { spec, bar, params });
export const createBoard = (payload) => send("/api/workspace/dashboards", payload);
export const updateBoard = (payload) => send("/api/workspace/dashboards/update", payload);
export const deleteBoard = (id) => send("/api/workspace/dashboards/delete", { id });

export const getAgentInfo = () => request("/api/workspace/agent");
/** The address that downloads the skill folder (a zip) as the signed-in person. */
export const SKILL_HREF = "/api/workspace/agent/skill";
export const getAgentTokens = () => request("/api/users/tokens").then((b) => b.tokens);
export const createAgentToken = (userId, label, scope, days) => send("/api/users/tokens", { user_id: userId, label, scope, days });
export const revokeAgentToken = (id) => send("/api/users/tokens/revoke", { id });

/** A file's bytes as base64, which is how the service takes them. */
export async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}

/** {model_ready, running, on_disk, stale}: the service is up, whether a model is configured, and the build it runs (a fingerprint of its code). */
export const getHealth = () => request("/api/ontology/health");
/** Whether the service has a model to call (the AI buttons need one): false when it has no credentials. */
export const getModelReady = () => request("/api/ontology/health").then((b) => Boolean(b.model_ready), () => true);
