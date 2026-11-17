import React from "react";
import { CopyButton } from "./CopyButton.jsx";
import { diagnose } from "./connectModel.js";
import { Icon } from "./ui/Icon.jsx";

/** The one place a failed connection is explained: what the service said, the likely causes with how to check each, and a button that copies the report for a DBA.
 * `report` is the text to copy (errorReport); `children` are the buttons that follow (retry, go back). */
export function ConnectFailure({ message, report, children, note }) {
  const d = diagnose(message);
  return (
    <div className="wiz-result bad-card" role="alert">
      <p className="wiz-result-title"><Icon name="alert" /> 没连上：{d.title}</p>
      <p className="wiz-said">{message}</p>
      <h3>可能的原因，和怎么查</h3>
      <ol className="causes">
        {d.causes.map((c) => <li key={c.what}><strong>{c.what}</strong><span>{c.check}</span></li>)}
      </ol>
      <div className="wiz-result-actions">
        <CopyButton text={report} label="复制错误信息" />
        {children}
      </div>
      {note && <p className="hint">{note}</p>}
    </div>
  );
}
