import React, { useEffect, useRef, useState } from "react";
import { KIND_LABEL, STATE_COLOUR, stateTone } from "./graphModel.js";
import { useT } from "./i18n/index.js";
import { TWIN_KINDS, TWIN_STYLE, kindCounts, mapLayout, searchMatches, traceSubgraph } from "./lineageModel.js";
import { Columns, Icon, TwinEdge, TwinNode, TwinSvg, useViewport } from "./TwinMap.jsx";
import { edgeTone } from "./lineageModel.js";

const TONES = ["confirmed", "needs_look", "rejected", "none"];

/** A group of buttons of which one is on. */
export function Segmented({ label, value, options, onChange, lead }) {
  return (
    <div className="tw-seg" role="group" aria-label={label}>
      {lead && <span className="tw-seg-lead">{lead}</span>}
      {options.map(([key, text]) => <button key={String(key)} type="button" className={value === key ? "on" : ""} aria-pressed={value === key} onClick={() => onChange(key)}>{text}</button>)}
    </div>
  );
}

/** An icon button with a tooltip; `on` marks a mode that is switched on. */
export function IconButton({ icon, label, on, onClick, text }) {
  return (
    <button type="button" className={`tw-btn${on ? " on" : ""}${text ? " text" : ""}`} aria-label={label} title={label} aria-pressed={on === undefined ? undefined : on} onClick={onClick}>
      <Icon name={icon} />{text && <span>{text}</span>}
    </button>
  );
}

/** Search over the name, the kind and the object type of every node, with a dropdown of what it finds (name / kind). Typing dims the rest of the map; picking a match goes to it. */
export function Search({ nodes, query, onQuery, onGo }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState(0);
  const holder = useRef(null);
  const matches = searchMatches(nodes, query, (n) => KIND_LABEL[n.kind]);
  useEffect(() => setAt(0), [query]);
  useEffect(() => {
    const away = (e) => { if (!holder.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, []);
  const go = (n) => { setOpen(false); onGo(n); };
  const key = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setAt((i) => Math.min(matches.length - 1, i + 1)); setOpen(true); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter" && matches[at]) { e.preventDefault(); go(matches[at]); }
    else if (e.key === "Escape") { if (open) { e.stopPropagation(); setOpen(false); } else onQuery(""); }
  };
  const showList = open && query.trim();
  return (
    <div className="tw-search" ref={holder}>
      <label className="tw-search-box">
        <Icon name="search" size={14} />
        <input type="text" role="combobox" aria-expanded={Boolean(showList)} aria-controls="tw-matches" aria-autocomplete="list" placeholder={t("lineage.twin.search")} aria-label={t("lineage.twin.search_aria")}
          value={query} onChange={(e) => { onQuery(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={key} />
        {query && <button type="button" className="tw-search-clear" aria-label={t("lineage.twin.search_clear")} onClick={() => onQuery("")}><Icon name="close" size={12} /></button>}
      </label>
      {showList && (
        <ul className="tw-matches" id="tw-matches" role="listbox" aria-label={t("lineage.twin.matches")}>
          {matches.length ? matches.map((n, i) => (
            <li key={n.id} role="option" aria-selected={i === at} className={i === at ? "on" : ""} onPointerDown={(e) => e.preventDefault()} onClick={() => go(n)} onMouseEnter={() => setAt(i)}>
              <span className="tw-dot" style={{ background: TWIN_STYLE[n.kind]?.colour }} aria-hidden="true" />
              <span className="tw-match-name">{n.name}</span>
              <span className="tw-match-kind">{KIND_LABEL[n.kind]}</span>
            </li>
          )) : <li className="none" role="option" aria-selected="false">{t("lineage.twin.no_match")}</li>}
        </ul>
      )}
    </div>
  );
}

/** "Node types": what the map holds, by kind and by health. A kind can be switched off to dim it; the reason filter lives here too. */
export function TypesPopover({ nodes, off, onToggle, filter, onFilter }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const holder = useRef(null);
  useEffect(() => {
    const away = (e) => { if (!holder.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, []);
  const counts = kindCounts(nodes);
  const tones = TONES.map((tone) => [tone, nodes.filter((n) => stateTone(n) === tone).length]);
  const filters = [["", t("lineage.filter.all")], ["data", t("lineage.filter.data")], ["definition", t("lineage.filter.definition")]];
  return (
    <div className="tw-pop-holder" ref={holder}>
      <button type="button" className={`tw-btn text${open || off.size || filter ? " on" : ""}`} aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((v) => !v)}>
        <Icon name="layers" /><span>{t("lineage.twin.types")}</span>{off.size > 0 && <span className="tw-badge">{TWIN_KINDS.length - off.size}/{TWIN_KINDS.filter((k) => counts[k]).length}</span>}
      </button>
      {open && (
        <div className="tw-pop" role="dialog" aria-label={t("lineage.twin.types")}>
          <h2>{t("lineage.twin.types")}</h2>
          <ul className="tw-kinds">
            {TWIN_KINDS.filter((k) => counts[k]).map((kind) => (
              <li key={kind}>
                <button type="button" className={off.has(kind) ? "off" : ""} aria-pressed={!off.has(kind)} onClick={() => onToggle(kind)}>
                  <span className="tw-chip" style={{ background: TWIN_STYLE[kind].colour }} aria-hidden="true"><svg viewBox="0 0 24 24" width="11" height="11"><path d={TWIN_STYLE[kind].icon} /></svg></span>
                  <span className="tw-kind-name">{KIND_LABEL[kind]}</span>
                  <span className="tw-kind-count">{counts[kind]}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="tw-pop-hint">{t("lineage.twin.types_hint")}</p>
          <h3>{t("lineage.legend.states")}</h3>
          <ul className="tw-tones">
            {tones.map(([tone, n]) => (
              <li key={tone} className={n ? "" : "zero"}><span className="tw-tone-dot" style={{ background: STATE_COLOUR[tone] }} aria-hidden="true" /><span>{t(`lineage.legend.tone.${tone}`)}</span><span className="tw-kind-count">{n}</span></li>
            ))}
          </ul>
          <p className="tw-pop-hint">{t("lineage.twin.lines_hint")}</p>
          <h3>{t("lineage.filter.aria")}</h3>
          <Segmented label={t("lineage.filter.aria")} value={filter} options={filters} onChange={onFilter} />
        </div>
      )}
    </div>
  );
}

/** What a picked node offers, over the node: hide it, trace its path, or let go. */
export function SelectionBar({ at, onHide, onTrace, onCancel }) {
  const t = useT();
  return (
    <div className={`tw-selbar${at.below ? " below" : ""}`} style={{ left: at.x, top: at.y }} role="toolbar" aria-label={t("lineage.twin.select_aria")}>
      <button type="button" onClick={onHide}><Icon name="eyeoff" size={14} />{t("lineage.twin.hide")}</button>
      <button type="button" className="primary" onClick={onTrace}><Icon name="trace" size={14} />{t("lineage.twin.trace")}</button>
      <button type="button" onClick={onCancel}><Icon name="close" size={14} />{t("lineage.twin.cancel")}</button>
    </div>
  );
}

/** The trace of one node: only its chain, upstream and downstream, drawn as its own map in a dialog, with each step's columns and rows. */
export function TraceDialog({ node, nodes, edges, curved, onClose }) {
  const t = useT();
  const [full, setFull] = useState(false);
  const sub = traceSubgraph(node.id, nodes, edges);
  const layout = mapLayout(sub.nodes, sub.edges);
  const viewport = useViewport(layout);
  const byId = Object.fromEntries(sub.nodes.map((n) => [n.id, n]));
  useEffect(() => {
    const esc = (e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    document.addEventListener("keydown", esc, true);
    return () => document.removeEventListener("keydown", esc, true);
  }, [onClose]);
  return (
    <div className="tw-modal-back" role="presentation" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`tw-modal${full ? " full" : ""}`} role="dialog" aria-modal="true" aria-label={t("lineage.twin.trace_title", { name: node.name })}>
        <header>
          <Icon name="trace" />
          <h2>{t("lineage.twin.trace")}</h2>
          <span className="tw-modal-sub">{node.name}</span>
          <span className="tw-modal-count">{t("lineage.twin.trace_count", { count: sub.nodes.length })}</span>
          <span className="tw-spacer" />
          <IconButton icon="fit" label={t("lineage.tools.fit")} onClick={viewport.fit} />
          <IconButton icon={full ? "collapse" : "expand"} label={full ? t("lineage.twin.exit_fullscreen") : t("lineage.twin.fullscreen")} onClick={() => setFull((v) => !v)} />
          <IconButton icon="close" label={t("lineage.twin.close")} onClick={onClose} />
        </header>
        <div className="tw-modal-body">
          <TwinSvg viewport={viewport} content={layout} mode="hand" label={t("lineage.twin.trace_title", { name: node.name })}>
            <Columns layout={layout} />
            {sub.edges.map((e) => <TwinEdge key={`${e.from}>${e.to}`} from={layout.positions[e.from]} to={layout.positions[e.to]} tone={edgeTone(e, byId)} lit curved={curved} />)}
            {sub.nodes.map((n) => <TwinNode key={n.id} node={n} box={layout.positions[n.id]} picked={n.id === node.id} interactive={false} onPick={() => {}} />)}
          </TwinSvg>
        </div>
      </div>
    </div>
  );
}
