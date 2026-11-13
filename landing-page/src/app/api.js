// The workspace service, one function per request. A refusal arrives as the service's own Chinese sentence.
async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { cache: "no-store", ...options });
  } catch {
    throw new Error("连不上本机服务，请确认服务已经启动后再试");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw Object.assign(new Error(body?.error || `服务返回了 ${response.status}`), { code: response.status });
  return body;
}

export const getDatasets = () => request("/api/workspace/datasets").then((b) => b.datasets);

export const getTasks = () => request("/api/workspace/tasks").then((b) => b.tasks);

export const getDataset = (name, version = null) =>
  request(`/api/workspace/datasets/${encodeURIComponent(name)}${version ? `?version=${version}` : ""}`);

export const uploadDatasets = (payload) =>
  request("/api/workspace/datasets/upload", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then((b) => b.results);

/** A file's bytes as base64, which is how the service takes them. */
export async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}
