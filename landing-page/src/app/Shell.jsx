import React, { useEffect, useState } from "react";
import { DatasetList } from "./DatasetList.jsx";
import { DatasetPage } from "./DatasetPage.jsx";
import { NAV, navKeyOf, parseRoute } from "./routeModel.js";

function Navigation({ active, open, onPick }) {
  return (
    <nav className={`nav${open ? " open" : ""}`} aria-label="主导航">
      {NAV.map((group, i) => (
        <div className="nav-group" key={group.label ?? i}>
          {group.label && <p className="nav-heading">{group.label}</p>}
          {group.items.map((item) =>
            item.href ? (
              <a key={item.key} href={item.href} className={item.key === active ? "active" : ""} aria-current={item.key === active ? "page" : undefined} onClick={onPick}>
                {item.label}
              </a>
            ) : (
              <span key={item.key} className="off" aria-disabled="true">
                {item.label}
              </span>
            ),
          )}
        </div>
      ))}
    </nav>
  );
}

function NotFound() {
  return (
    <main className="page">
      <h1>没有这个页面</h1>
      <p className="muted"><a href="#/datasets">回到数据集</a></p>
    </main>
  );
}

export function Shell() {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    if (!window.location.hash) window.location.replace("#/datasets");
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.page, route.name]);

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand-row">
          <strong className="brand">OntoPoc</strong>
          <button className="plain menu-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>菜单</button>
        </div>
        <Navigation active={navKeyOf(route)} open={menu} onPick={() => setMenu(false)} />
      </aside>
      {route.page === "datasets" && <DatasetList />}
      {route.page === "dataset" && <DatasetPage route={route} />}
      {!["datasets", "dataset"].includes(route.page) && <NotFound />}
    </div>
  );
}
