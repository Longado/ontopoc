import { useEffect, useMemo, useState } from "react";

import { boxOf, edgePath, forceLayout, moveNode } from "./forceLayoutModel.js";
import { PanZoom } from "./PanZoom.jsx";
import { typeLabel } from "./ontologyStudioModel.js";

const get = (url) => fetch(url, { cache: "no-store" }).then(async (r) => {
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `服务返回 ${r.status}`);
  return body;
});
const failure = (e) => (e.message === "Failed to fetch" ? "连不上本机建模服务" : e.message);

/** The data itself as a graph, as a knowledge graph tool shows it: pick one object, then open whatever it connects to. */
export function InstanceGraph({ run }) {
  const { ontology } = run;
  const types = ontology.object_types;
  const colour = Object.fromEntries(types.map((t, i) => [t.key, `ig-t${i % 8}`]));
  const base = `/api/ontology/runs/${run.saved_as}`;
  const [type, setType] = useState(types[0]?.key);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [fields, setFields] = useState({});
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {   // what matches the search, a moment after typing stops
    if (!run.saved_as || !type) return undefined;
    const timer = setTimeout(() => get(`${base}/instances/${encodeURIComponent(type)}?q=${encodeURIComponent(query)}`).then(setFound, (e) => setError(failure(e))), 250);
    return () => clearTimeout(timer);
  }, [type, query, base, run.saved_as]);

  async function open(id, fresh = false) {
    if (id.startsWith("more:")) return;
    setBusy(true); setError("");
    try {
      const g = await get(`${base}/graph?node=${encodeURIComponent(id)}`);
      const more = g.more.map((m) => ({ id: `more:${id}:${m.relation}`, label: `还有 ${m.hidden} 个${typeLabel(ontology, m.type)}`, type: m.type, more: true }));
      setNodes((old) => { const keep = fresh ? [] : old; const have = new Set(keep.map((n) => n.id)); return [...keep, ...[...g.nodes, ...more].filter((n) => !have.has(n.id))]; });
      setEdges((old) => { const keep = fresh ? [] : old; const have = new Set(keep.map((e) => `${e.from}>${e.to}>${e.relation}`));
        return [...keep, ...g.edges.filter((e) => !have.has(`${e.from}>${e.to}>${e.relation}`)), ...more.map((m) => ({ from: id, to: m.id, relation: "more", more: true }))]; });
      setFields((f) => ({ ...f, [id]: g.center.fields }));
      setSelected(id);
    } catch (e) { setError(failure(e)); } finally { setBusy(false); }
  }

  const [placed, setPlaced] = useState(null);
  const layout = useMemo(() => {   // boxes already on screen start where they were, so opening a node does not shuffle the rest
    const at = Object.fromEntries((placed?.nodes || []).map((n) => [n.id, n]));
    return forceLayout(nodes.map((n) => ({ ...n, box: { w: boxOf(n.name && n.name.length > n.label.length ? n.name : n.label).w, h: n.name ? 56 : 44 },
      ...(at[n.id] ? { x: at[n.id].x + at[n.id].w / 2, y: at[n.id].y + at[n.id].h / 2 } : {}) })),
      edges.map((e) => ({ from: e.from, to: e.to })));
  }, [nodes, edges]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setPlaced(layout), [layout]);
  const graph = placed && placed.nodes.length === layout.nodes.length ? placed : layout;
  const at = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
  const sel = nodes.find((n) => n.id === selected);

  if (!run.saved_as) return <p className="pr-muted">示例结果没有数据行，上传自己的文件后可以看实例图谱。</p>;
  return <div className="ig">
    <aside className="ig-find">
      <label htmlFor="ig-type" className="sr-only">对象类型</label>
      <select id="ig-type" value={type} onChange={(e) => { setType(e.target.value); setQuery(""); }}>{types.map((t) => <option key={t.key} value={t.key}>{t.label || t.key}</option>)}</select>
      <label htmlFor="ig-q" className="sr-only">按名称或编号找</label>
      <input id="ig-q" value={query} placeholder="名称或编号" onChange={(e) => setQuery(e.target.value)} />
      {found && <p className="ig-count">{found.total.toLocaleString("zh-CN")} 个{found.total > found.items.length ? `，显示前 ${found.items.length}` : ""}</p>}
      <ul className="ig-results">{found?.items.map((i) => <li key={i.id}><button type="button" aria-pressed={selected === i.id} onClick={() => open(i.id, true)}>
        <i className={colour[type]} />{i.name ? <>{i.name}<small>{i.label}</small></> : i.label}</button></li>)}</ul>
    </aside>
    <div className="ig-canvas">
      {error && <p role="alert" className="pr-error">{error}</p>}
      {!nodes.length ? <div className="ig-empty"><span aria-hidden="true">◎</span><p>在左边选一个对象，这里画出它在数据里连着的一切。</p></div>
        : <PanZoom width={graph.width} height={graph.height} label="实例图谱" resetKey={nodes[0]?.id} onNodeDrag={(id, dx, dy) => setPlaced((g) => moveNode(g || layout, id, dx, dy))}>
          {edges.filter((e) => at[e.from] && at[e.to]).map((e, i) => { const p = edgePath(at[e.from], at[e.to], 0);
            return <g key={`${e.from}>${e.to}>${e.relation}>${i}`} className={`ig-edge${e.more ? " is-more" : ""}`}><path d={p.path} />{e.label && <text x={p.lx} y={p.ly} textAnchor="middle">{e.label}</text>}</g>; })}
          {graph.nodes.map((n) => <g key={n.id} data-node={n.id} transform={`translate(${n.x},${n.y})`}
            className={`ig-node ${colour[n.type] || ""}${n.more ? " is-more" : ""}${n.id === selected ? " is-selected" : ""}${fields[n.id] ? " is-open" : ""}`}
            role="button" tabIndex={0} aria-label={`${typeLabel(ontology, n.type)} ${n.label}${n.more ? "" : "，点开看它连着的"}`}
            onClick={() => open(n.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(n.id); } }}>
            <title>{n.more ? "太多了，没有全画出来；全部在这个对象的数据页里" : typeLabel(ontology, n.type)}</title>
            <rect width={n.w} height={n.h} rx={22} />{n.name ? <><text x={n.w / 2} y={24} textAnchor="middle" className="ig-num">{n.label}</text><text x={n.w / 2} y={42} textAnchor="middle" className="ig-name">{n.name}</text></>
              : <text x={n.w / 2} y={n.h / 2 + 5} textAnchor="middle">{n.label}</text>}</g>)}
        </PanZoom>}
      {nodes.length > 0 && <div className="ig-legend">{[...new Set(nodes.filter((n) => !n.more).map((n) => n.type))].map((t) => <span key={t}><i className={colour[t]} />{typeLabel(ontology, t)}</span>)}
        {busy && <span>读取中…</span>}<button type="button" className="pr-link" onClick={() => { setNodes([]); setEdges([]); setSelected(null); }}>清空</button></div>}
    </div>
    <aside className="ig-detail" aria-label="选中的对象">
      {sel && fields[sel.id] ? <><p className="ig-detail-type"><i className={colour[sel.type]} />{typeLabel(ontology, sel.type)}</p><h3>{sel.label}</h3>{sel.name && <p className="ig-detail-name">{sel.name}</p>}
        <dl className="os-facts">{Object.entries(fields[sel.id]).map(([k, v]) => <div key={k} className="ig-fact"><dt>{k}</dt><dd>{v}</dd></div>)}</dl></>
        : <p className="pr-muted">点一个节点看它的字段。</p>}
    </aside>
  </div>;
}
