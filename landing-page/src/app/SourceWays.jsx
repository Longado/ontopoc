import React, { useId, useState } from "react";
import { CopyButton } from "./CopyButton.jsx";
import { t } from "./i18n/index.js";
import { hrefFor } from "./routeModel.js";
import { Icon } from "./ui/Icon.jsx";

const dbaText = () => ["l0", "", "l1", "l2", "l3", "l4", "l5", "l6", "", "l7"].map((k) => (k ? t(`sources.dba.${k}`) : "")).join("\n");
const adminText = () => ["l0", "l1", "l2", "l3", "l4", "l5"].map((k) => t(`sources.ask.${k}`)).join("\n");

/** The passive way to connect: a folded panel holding a message to send to whoever runs the database (`audience` "dba") or to an admin ("admin"), with a one-click copy and what to do next. */
export function PassiveWay({ audience = "dba", defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const admin = audience === "admin";
  const message = admin ? adminText() : dbaText();
  return (
    <div className={`cw cw-passive${open ? " cw-open" : ""}`}>
      <button type="button" className="cw-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <span className="cw-ico"><Icon name="send" size={16} /></span>
        <span className="cw-toggle-text"><strong>{admin ? t("sources.way.admin.toggle") : t("sources.way.passive.toggle")}</strong><span className="muted small">{t("sources.way.passive.hint")}</span></span>
        <Icon name="chevron-down" size={16} />
      </button>
      {open && (
        <div className="cw-body" id={id}>
          {!admin && <p className="muted">{t("sources.way.passive.intro")}</p>}
          <div className="cw-msg-head"><span className="caption">{t("sources.way.passive.msgLabel")}</span><CopyButton text={message} label={t("sources.way.passive.copy")} /></div>
          <pre className="cw-msg" tabIndex={0} aria-label={t("sources.way.passive.msgLabel")}>{message}</pre>
          <p className="hint">{admin ? t("sources.way.admin.after") : t("sources.way.passive.after")}</p>
          <p className="hint">{t("sources.way.passive.excel")} <a href={hrefFor({ page: "datasets" })}>{t("sources.way.passive.upload")}</a>.</p>
        </div>
      )}
    </div>
  );
}

/** What an admin sees on the Sources page: the active way first (the guide), then the passive one folded. */
export function ConnectWays({ onConnect }) {
  return (
    <section className="cw-list" aria-label={t("sources.way.title")}>
      <div className="cw cw-active">
        <span className="cw-ico"><Icon name="plug" size={16} /></span>
        <div className="cw-active-text">
          <p className="cw-title"><strong>{t("sources.way.active.title")}</strong><span className="cw-badge">{t("sources.way.active.badge")}</span></p>
          <p className="muted">{t("sources.way.active.text")}</p>
          <p className="faint small">{t("sources.way.active.steps")}</p>
        </div>
        <button className="primary" onClick={onConnect}>{t("sources.connect")}</button>
      </div>
      <PassiveWay audience="dba" />
    </section>
  );
}
