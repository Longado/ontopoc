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
      code: response.status, files: body?.files, readers: body?.readers, setup: body?.setup, mustChange: body?.must_change,
    });
  }
  return body;
}

const send = (path, payload = {}) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });

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

/** A file's bytes as base64, which is how the service takes them. */
export async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}
