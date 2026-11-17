import React, { useEffect, useMemo, useRef, useState } from "react";
import { getActions, getBoards, getDatasets, getPipelines, getRelations, getTypes } from "../api.js";
import { canBuild } from "../authModel.js";
import { buildEntries, pageEntries, search } from "../searchModel.js";
import { Icon } from "./Icon.jsx";

const KIND_ICON = { 页面: "arrow", 数据集: "table", 对象类型: "cube", 关系: "link", 管道: "pipeline", 看板: "board", 行为: "play", 最近: "clock" };

/** Reads the lists a search covers; a list this person may not read (or that fails) is simply left out. */
async function loadLists(user) {
  const builder = canBuild(user);
  const ok = (p) => p.then((v) => v, () => null);
  const [datasets, types, relations, pipelines, boards] = await Promise.all([
    ok(getDatasets()), ok(getTypes()), ok(getRelations()), builder ? ok(getPipelines()) : null, ok(getBoards().then((b) => b.dashboards)),
  ]);
  const acts = builder && types ? await Promise.all(types.map((t) => ok(getActions(t.id).then((b) => (b.actions ?? []).map((a) => ({ ...a, type: t.id })))))) : [];
  return { datasets, types, relations, pipelines, boards, actions: acts.flat().filter(Boolean) };
}

/** The ⌘K search. Props: `open`, `onClose`, `user` (decides which pages and lists are offered), `recents` ([{href, label}]: the last places visited, newest first).
 * Searches datasets, object types, relations, pipelines, boards, actions and pages by name; ↑ ↓ move, Enter opens, Esc closes. With nothing typed it lists the recents and the pages. */
export function CommandPalette({ open, onClose, user, recents = [] }) {
  const [query, setQuery] = useState("");
  const [lists, setLists] = useState(null);
  const [at, setAt] = useState(0);
  const input = useRef(null);
  const list = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    setQuery("");
    setAt(0);
    setLists(null);
    input.current?.focus();
    let live = true;
    loadLists(user).then((l) => live && setLists(l));
    return () => {
      live = false;
    };
  }, [open]);
  const pages = useMemo(() => pageEntries(user), [user]);
  const entries = useMemo(() => [...pages, ...buildEntries(lists ?? {})], [pages, lists]);
  const rows = useMemo(() => {
    if (query.trim()) return search(entries, query, 12).map((e) => ({ ...e, icon: e.icon ?? KIND_ICON[e.kind] }));
    return [
      ...recents.map((r) => ({ kind: "最近打开", label: r.label, sub: "", href: r.href, icon: "clock" })),
      ...pages.map((p) => ({ ...p, kind: "跳转到页面" })),
    ];
  }, [query, entries, recents, pages]);
  useEffect(() => setAt(0), [query]);
  useEffect(() => {
    list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [at, rows]);
  if (!open) return null;
  const go = (row) => {
    if (!row) return;
    onClose();
    window.location.hash = row.href;
  };
  const key = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setAt((n) => Math.min(n + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setAt((n) => Math.max(n - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(rows[at]);
    }
  };
  let last = null;
  return (
    <div className="ui-drawer-root palette-root">
      <div className="ui-overlay" onClick={onClose} />
      <div className="palette" role="dialog" aria-modal="true" aria-label="搜索" onKeyDown={key}>
        <div className="palette-input">
          <Icon name="search" />
          <input ref={input} type="text" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={rows[at] ? `palette-${at}` : undefined}
            aria-label="搜索数据集、对象类型、关系、管道、看板、行为或页面" placeholder="搜索数据集、对象类型、管道、看板…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <kbd>Esc</kbd>
        </div>
        <div className="palette-list" id="palette-list" role="listbox" ref={list}>
          {rows.map((row, i) => {
            const head = row.kind !== last;
            last = row.kind;
            return (
              <React.Fragment key={`${row.kind}${row.href}${i}`}>
                {head && !query.trim() && <p className="palette-head">{row.kind}</p>}
                <a id={`palette-${i}`} role="option" aria-selected={i === at} href={row.href} className={i === at ? "on" : ""} onMouseMove={() => setAt(i)} onClick={(e) => { e.preventDefault(); go(row); }}>
                  <Icon name={row.icon ?? "arrow"} />
                  <span className="palette-label">{row.label}</span>
                  {row.sub && <span className="palette-sub">{row.sub}</span>}
                  {query.trim() && <span className="palette-kind">{row.kind}</span>}
                </a>
              </React.Fragment>
            );
          })}
          {query.trim() && !rows.length && <p className="palette-none">{lists ? `没有找到“${query.trim()}”` : "正在读取…"}</p>}
          {query.trim() && !lists && rows.length > 0 && <p className="palette-none">还在读取数据，结果可能还会增加</p>}
        </div>
        <p className="palette-foot"><kbd>↑</kbd><kbd>↓</kbd> 选择 <kbd>Enter</kbd> 打开 <kbd>Esc</kbd> 关闭</p>
      </div>
    </div>
  );
}
