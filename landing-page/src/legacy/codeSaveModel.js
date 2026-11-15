import { serviceError } from "./ontologyStudioModel.js";

/** What a person says about code columns or a repeated key is posted to the service, which answers with the lists as they
 *  now stand; the run is read again because the answers were worked out again. The service may add `warning`: what it
 *  kept, and the step after that did not finish. A failure to read the run is said as such: what was posted is kept. */
export async function postAndReread({ send = fetch, url, body, runName }) {
  const response = await send(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ saved_as: runName, ...body }) });
  const lists = await response.json().catch(() => ({ error: `服务返回 ${response.status}` }));
  if (!response.ok) throw new Error(serviceError(response.status, lists));
  const reread = await send(`/api/ontology/runs/${runName}`, { cache: "no-store" });
  const run = await reread.json().catch(() => ({}));
  if (!reread.ok) throw new Error(`已记下，但没能读到重算后的答案：${serviceError(reread.status, run)}`);
  return { lists, run, warning: lists.warning || "" };
}
