// The workspace service, one function per request. A refusal arrives as the service's own Chinese sentence.

// the page that holds the sign-in decides what a 401 means: it shows the sign-in form
let onSignedOut = () => {};
export const whenSignedOut = (fn) => {
  onSignedOut = fn;
};

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { cache: "no-store", ...options });
  } catch {
    throw new Error("连不上本机服务，请确认服务已经启动后再试");
  }
  const body = await response.json().catch(() => null);
  if (response.status === 401 && path !== "/api/auth/login") onSignedOut();   // the session ended (or never was): back to the sign-in form
  if (!response.ok) {
    throw Object.assign(new Error(body?.error || `服务返回了 ${response.status}`), {
      code: response.status, files: body?.files, readers: body?.readers, setup: body?.setup, mustChange: body?.must_change, keyCheck: body?.key_check,
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

export const uploadDatasets = (payload) =>
  request("/api/workspace/datasets/upload", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then((b) => b.results);

// object types
const typePath = (id, tail = "") => `/api/workspace/types/${encodeURIComponent(id)}${tail}`;
export const getTypes = () => request("/api/workspace/types").then((b) => b.types);
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
export const confirmView = (id, version, seen) => send("/api/workspace/types/views/confirm", { id, version, seen });
export const suggestTypes = (datasets, purpose) => send("/api/workspace/types/suggest", { datasets, purpose });

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
export const savePipeline = (name, version, spec) => send("/api/workspace/pipelines/update", { id: name, version, spec });
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

// relations, the 待确认 queue, who sees which type
const relationPath = (id, tail = "") => `/api/workspace/relations/${encodeURIComponent(id)}${tail}`;
export const getRelations = () => request("/api/workspace/relations").then((b) => b.relations);
export const getRelation = (id) => request(relationPath(id));
export const getRelationLog = (id) => request(relationPath(id, "/log")).then((b) => b.log);
/** The types the person may see with their dataset's columns: what a relation's two ends are picked from. */
export const getRelationForm = () => request("/api/workspace/relation-form").then((b) => b.types);
export const createRelation = (payload) => send("/api/workspace/relations", payload);
export const updateRelation = (payload) => send("/api/workspace/relations/update", payload);
/** {items, count}: everything waiting to be judged that this person may see, and how many of it they may confirm now. */
export const getQueue = () => request("/api/workspace/queue");
/** Only how many items this person may confirm now: read from the states, cheap enough to ask on every page. */
export const getQueueCount = () => request("/api/workspace/queue?count=1").then((b) => b.count);
/** Confirms one queue item as the version the person saw, with the item's `seen` (what it showed of the data: the connected-row counts of a relation, the version and rows of a type's dataset). */
export const confirmItem = (element, version, seen = undefined) => send("/api/workspace/queue/confirm", { element, version, ...(seen ? { seen } : {}) });
export const sendBack = (element, version, reason) => send("/api/workspace/queue/send-back", { element, version, reason });
export const getPermissions = () => request("/api/workspace/permissions");
/** `visibleTo`: "everyone" or the ids of the people who may see the type. */
export const setPermission = (type, visibleTo) => send("/api/workspace/permissions", { type, visible_to: visibleTo });
/** `rules`: the whole list of one type, [{column, value, user_ids}]: these people see the rows where the property equals the value. */
export const setRowRules = (type, rules) => send("/api/workspace/row-rules", { type, rules });

// Q&A: the scope line with the person's own history, one saved answer as it stands now, a new question
export const getAsk = () => request("/api/workspace/ask");
export const getAnswer = (id) => request(`/api/workspace/ask/${id}`);
/** The model works out the query: it can take up to a minute, there is no timeout here. */
export const askQuestion = (question) => send("/api/workspace/ask", { question });
/** A builder's switch on one property: its values are not sent to the model that reads a question. */
export const setValuesHidden = (id, column, hide) => send("/api/workspace/types/privacy", { id, column, hide_values: hide });

/** A file's bytes as base64, which is how the service takes them. */
export async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}
