import { useEffect, useMemo, useRef, useState } from "react";

import { searchHits, searchIndex } from "./searchModel.js";

const KIND_TEXT = { object: "对象", field: "字段", relation: "关系", table: "表" };

/** ⌘K: find an object, field, relation or table in this run and go where it is shown. */
export function SearchDialog({ run, decisions, onGo, onClose }) {
  const [query, setQuery] = useState("");
  const [at, setAt] = useState(0);
  const input = useRef(null);
  const index = useMemo(() => searchIndex(run, decisions), [run, decisions]);
  const hits = searchHits(index, query);
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => setAt(0), [query]);
  useEffect(() => { document.getElementById(`os-hit-${at}`)?.scrollIntoView({ block: "nearest" }); }, [at]);
  function key(e) {
    if (e.key === "Escape") onClose();
    else if (e.key === "ArrowDown") { e.preventDefault(); setAt((i) => Math.min(i + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter" && hits[at]) onGo(hits[at].target);
  }
  return <div className="os-search-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="os-search-box" role="dialog" aria-modal="true" aria-label="搜索">
      <input id="os-global-search" ref={input} value={query} placeholder="对象、字段、关系、表" onChange={(e) => setQuery(e.target.value)} onKeyDown={key}
        role="combobox" aria-expanded={hits.length > 0} aria-controls="os-hits" aria-activedescendant={hits[at] ? `os-hit-${at}` : undefined} />
      {query.trim() && <ul id="os-hits" role="listbox" className="os-hits">
        {hits.map((h, i) => <li key={`${h.kind}-${h.target.object || ""}-${h.text}`} id={`os-hit-${i}`} role="option" aria-selected={i === at}
          onMouseEnter={() => setAt(i)} onClick={() => onGo(h.target)}>
          <em className={`os-hit-kind is-${h.kind}`}>{KIND_TEXT[h.kind]}</em><b>{h.text}</b>{h.sub && <small>{h.sub}</small>}</li>)}
        {!hits.length && <li className="os-hit-none">没有找到</li>}
      </ul>}
    </div>
  </div>;
}
