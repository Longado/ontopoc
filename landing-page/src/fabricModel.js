// The Fabric IQ export link: with the workspace and lakehouse the tables were loaded into, the definition carries data
// bindings; without them, the types alone. Checked here so a mistyped id never downloads an error as a file.
const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function fabricLink(savedAs, workspace, lakehouse) {
  const base = `/api/ontology/runs/${encodeURIComponent(savedAs)}/export/fabric`;
  const [w, l] = [workspace.trim(), lakehouse.trim()];
  if (!w && !l) return { url: base, note: "只含对象和关系；填上两个 ID 才带数据绑定" };
  if (!w || !l) return { url: null, note: "两个 ID 要一起填" };
  if (!GUID.test(w) || !GUID.test(l)) return { url: null, note: "ID 要写成 GUID，例如 580f410e-733d-43bd-8a87-be12b536f7ff" };
  return { url: `${base}?workspace=${w}&lakehouse=${l}`, note: "带数据绑定" };
}
