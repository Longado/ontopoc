import React, { useEffect, useRef, useState } from "react";
import { AccountPage } from "./AccountPage.jsx";
import { useAuth } from "./Auth.jsx";
import { isAdmin, roleLabel } from "./authModel.js";
import { DatasetList } from "./DatasetList.jsx";
import { DatasetPage } from "./DatasetPage.jsx";
import { TasksPage } from "./TasksPage.jsx";
import { UsersPage } from "./UsersPage.jsx";
import { ADMIN_NAV, NAV, PLANNED, navKeyOf, parseRoute } from "./routeModel.js";

function UserBox({ onPick }) {
  const { user, auth, signOut } = useAuth();
  if (!auth) return <p className="nav-user muted">本机，没有登录</p>;
  return (
    <div className="nav-user">
      <a href="#/account" onClick={onPick} title="我的账号">{user.display_name}</a>
      <span className="muted">{roleLabel(user.role)}</span>
      <button className="plain" onClick={signOut}>退出</button>
    </div>
  );
}

function Navigation({ active, open, onPick }) {
  const { user } = useAuth();
  return (
    <nav className={`nav${open ? " open" : ""}`} aria-label="主导航">
      {[...NAV, ...(isAdmin(user) ? ADMIN_NAV : [])].map((group, i) => (
        <div className="nav-group" key={group.label ?? i}>
          {group.label && <p className="nav-heading">{group.label}</p>}
          {group.items.map((item) => (
            <a key={item.key} href={item.href} className={`${item.built ? "" : "off"}${item.key === active ? " active" : ""}`.trim()}
              aria-current={item.key === active ? "page" : undefined} onClick={onPick}>
              {item.label}
            </a>
          ))}
        </div>
      ))}
      <UserBox onPick={onPick} />
    </nav>
  );
}

function Planned({ route }) {
  const [label, text] = PLANNED[route.key];
  return (
    <main className="page">
      <h1 tabIndex={-1}>{label}</h1>
      <p className="muted">{text}</p>
    </main>
  );
}

function Forbidden() {
  return (
    <main className="page">
      <h1 tabIndex={-1}>你的角色不能看这个页面</h1>
      <p className="muted"><a href="#/datasets">回到数据集</a></p>
    </main>
  );
}

function NotFound() {
  return (
    <main className="page">
      <h1 tabIndex={-1}>没有这个页面</h1>
      <p className="muted"><a href="#/datasets">回到数据集</a></p>
    </main>
  );
}

export function Shell() {
  const { user } = useAuth();
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    if (!window.location.hash) window.location.replace("#/datasets");
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const first = useRef(true);
  useEffect(() => {
    window.scrollTo(0, 0);
    if (first.current) first.current = false;
    else document.querySelector("main h1")?.focus({ preventScroll: true });   // a followed link puts the reader at the new page's heading
  }, [route.page, route.name, route.key]);

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
      {route.page === "tasks" && <TasksPage />}
      {route.page === "account" && <AccountPage />}
      {route.page === "users" && (isAdmin(user) ? <UsersPage /> : <Forbidden />)}
      {route.page === "planned" && <Planned route={route} />}
      {!["datasets", "dataset", "tasks", "account", "users", "planned"].includes(route.page) && <NotFound />}
    </div>
  );
}
