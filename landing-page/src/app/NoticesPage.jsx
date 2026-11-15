import React, { useState } from "react";
import { WORKSPACE_CHANGED, getNotices, readNotices } from "./api.js";
import { timeText } from "./format.js";
import { useLoad } from "./useLoad.js";

/** This person's notices: what an action they are named on (by name, by an attribute, or through a relation) changed after it was approved. Newest first. */
export function NoticesPage() {
  const [state, reload] = useLoad(getNotices, []);
  const [error, setError] = useState("");
  const read = async (fields) => {
    setError("");
    try {
      await readNotices(fields);
      window.dispatchEvent(new Event(WORKSPACE_CHANGED));   // the count beside 消息 is read again
    } catch (e) {
      setError(e.message);
    }
    reload();
  };
  const list = state.data?.notices ?? [];
  return (
    <main className="page">
      <div className="page-head">
        <h1 tabIndex={-1}>消息</h1>
        {state.data?.unread > 0 && <button className="secondary" onClick={() => read({ all: true })}>全部标为已读</button>}
      </div>
      <p className="muted" style={{ marginBottom: 16 }}>行为里写了“批准后通知”的，改动一经批准就通知到这里。只通知看得到那一行的人；批准的人自己不收。</p>
      {state.status === "error" && <p className="error">{state.error}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !list.length && <p className="muted">还没有消息。</p>}
      <ul className="checks">
        {list.map((n) => (
          <li key={n.id} className={n.read ? "faint" : ""}>
            <span className="small faint">{timeText(n.at)}</span> {n.text}{" "}
            {!n.read && <button className="plain" onClick={() => read({ ids: [n.id] })}>标为已读</button>}
          </li>
        ))}
      </ul>
    </main>
  );
}
