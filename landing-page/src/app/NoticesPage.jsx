import React, { useState } from "react";
import { WORKSPACE_CHANGED, getNotices, readNotices } from "./api.js";
import { timeText } from "./format.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

/** This person's notices: what an action they are named on (by name, by an attribute, or through a relation) changed after it was approved. Newest first, unread marked. */
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
  const unread = state.data?.unread ?? 0;
  return (
    <main className="page">
      <PageHeader title="消息" sub={unread > 0 ? `${unread} 条未读` : "行为改动经批准后，会通知到看得到那一行的人；批准的人自己不收。"}
        actions={unread > 0 && <button className="secondary" onClick={() => read({ all: true })}>全部标为已读</button>} />
      {state.status === "error" && <p className="error">{state.error}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {state.status === "loading" && !state.data && <p className="muted">加载中</p>}
      {state.data && !list.length && <EmptyState icon="bell" title="还没有消息" text="行为里写了“批准后通知”的，改动一经批准就会通知到这里。" />}
      {list.length > 0 && (
        <ul className="notice-list">
          {list.map((n) => (
            <li key={n.id} className={n.read ? "notice read" : "notice unread"}>
              <span className="notice-dot" aria-hidden="true" />
              <div className="notice-body">
                <p>{n.text}</p>
                <p className="small muted">{timeText(n.at)}{n.read ? "" : "　未读"}</p>
              </div>
              {!n.read && <button className="plain" onClick={() => read({ ids: [n.id] })}>标为已读</button>}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
