import React, { useState } from "react";
import { WORKSPACE_CHANGED, getNotices, readNotices } from "./api.js";
import { timeText } from "./format.js";
import { useT } from "./i18n/index.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

/** This person's notices: what an action they are named on (by name, by an attribute, or through a relation) changed after it was approved. Newest first, unread marked. */
export function NoticesPage() {
  const t = useT();
  const [state, reload] = useLoad(getNotices, []);
  const [error, setError] = useState("");
  const read = async (fields) => {
    setError("");
    try {
      await readNotices(fields);
      window.dispatchEvent(new Event(WORKSPACE_CHANGED));   // the count beside Notifications is read again
    } catch (e) {
      setError(e.message);
    }
    reload();
  };
  const list = state.data?.notices ?? [];
  const unread = state.data?.unread ?? 0;
  return (
    <main className="page">
      <PageHeader title={t("notices.title")} sub={unread > 0 ? t("notices.unread", { count: unread }) : t("notices.sub")}
        actions={unread > 0 && <button className="secondary" onClick={() => read({ all: true })}>{t("notices.markAll")}</button>} />
      {state.status === "error" && <p className="error">{state.error}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {state.status === "loading" && !state.data && <p className="muted">{t("notices.loading")}</p>}
      {state.data && !list.length && <EmptyState icon="bell" title={t("notices.empty.title")} text={t("notices.empty.text")} />}
      {list.length > 0 && (
        <ul className="notice-list">
          {list.map((n) => (
            <li key={n.id} className={n.read ? "notice read" : "notice unread"}>
              <span className="notice-dot" aria-hidden="true" />
              <div className="notice-body">
                <p>{n.text}</p>
                <p className="small muted">{timeText(n.at)}{n.read ? "" : ` · ${t("notices.unreadTag")}`}</p>
              </div>
              {!n.read && <button className="plain" onClick={() => read({ ids: [n.id] })}>{t("notices.markRead")}</button>}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
