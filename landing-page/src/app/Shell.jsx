import React, { useEffect, useRef, useState } from "react";
import { AccountPage } from "./AccountPage.jsx";
import { AgentsPage } from "./AgentsPage.jsx";
import { BoardEditor } from "./BoardEditor.jsx";
import { BoardPage, BoardsPage } from "./BoardsPage.jsx";
import { WORKSPACE_CHANGED, getNotices, getQueueCount } from "./api.js";
import { NoticesPage } from "./NoticesPage.jsx";
import { useAuth } from "./Auth.jsx";
import { canBuild, isAdmin, roleLabel } from "./authModel.js";
import { ConfirmGroupPage } from "./ConfirmGroupPage.jsx";
import { ConfirmPage } from "./ConfirmPage.jsx";
import { DatasetList } from "./DatasetList.jsx";
import { DatasetPage } from "./DatasetPage.jsx";
import { LineagePage } from "./LineagePage.jsx";
import { ObjectPage } from "./ObjectPage.jsx";
import { PermissionsPage } from "./PermissionsPage.jsx";
import { PipelinePage } from "./PipelinePage.jsx";
import { PipelineNew, PipelinesPage } from "./PipelinesPage.jsx";
import { QaPage } from "./QaPage.jsx";
import { SchedulesPage } from "./SchedulesPage.jsx";
import { SourcePage } from "./SourcePage.jsx";
import { SourcesPage } from "./SourcesPage.jsx";
import { RelationForm } from "./RelationForm.jsx";
import { RelationPage, RelationsPage } from "./RelationsPage.jsx";
import { countText } from "./relationModel.js";
import { TasksPage } from "./TasksPage.jsx";
import { TypeForm } from "./TypeForm.jsx";
import { TypePage } from "./TypePage.jsx";
import { TypesPage } from "./TypesPage.jsx";
import { UsersPage } from "./UsersPage.jsx";
import { ADMIN_NAV, NAV, PLANNED, mayOpen, navKeyOf, parseRoute } from "./routeModel.js";

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

/** How many items of 待确认 this person may confirm now; read again whenever the page changes, so a confirmation made anywhere is counted. */
function useQueueCount(route) {
  const { user } = useAuth();
  const [count, setCount] = useState(0);
  const [round, setRound] = useState(0);
  const mayBuild = canBuild(user);
  useEffect(() => {
    const again = () => setRound((n) => n + 1);
    window.addEventListener(WORKSPACE_CHANGED, again);
    return () => window.removeEventListener(WORKSPACE_CHANGED, again);
  }, []);
  useEffect(() => {
    if (!mayBuild) return undefined;
    let live = true;
    getQueueCount().then((n) => live && setCount(n), () => live && setCount(0));
    return () => {
      live = false;
    };
  }, [mayBuild, route.page, route.id, route.name, round]);
  return count;
}

/** How many of this person's notices are unread; read again whenever the page changes. */
function useNoticeCount(route) {
  const [count, setCount] = useState(0);
  const [round, setRound] = useState(0);
  useEffect(() => {
    const again = () => setRound((n) => n + 1);
    window.addEventListener(WORKSPACE_CHANGED, again);
    return () => window.removeEventListener(WORKSPACE_CHANGED, again);
  }, []);
  useEffect(() => {
    let live = true;
    getNotices().then((b) => live && setCount(b.unread), () => live && setCount(0));
    return () => {
      live = false;
    };
  }, [route.page, route.id, route.name, round]);
  return count;
}

function Navigation({ active, open, onPick, count, unread = 0 }) {
  const { user } = useAuth();
  return (
    <nav className={`nav${open ? " open" : ""}`} aria-label="主导航">
      {[...NAV, ...(isAdmin(user) ? ADMIN_NAV : [])].map((group, i) => (
        <div className="nav-group" key={group.label ?? i}>
          {group.label && <p className="nav-heading">{group.label}</p>}
          {group.items.filter((item) => !item.builders || canBuild(user)).map((item) => (
            <a key={item.key} href={item.href} className={`${item.built ? "" : "off"}${item.key === active ? " active" : ""}`.trim()}
              aria-current={item.key === active ? "page" : undefined} onClick={onPick}>
              {item.label}
              {item.key === "confirm" && countText(count) && <span className="count" aria-label={`${count} 项等你确认`}>{countText(count)}</span>}
              {item.key === "notices" && countText(unread) && <span className="count" aria-label={`${unread} 条未读消息`}>{countText(unread)}</span>}
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

/** What each page of routeModel.PAGES draws, one line each (routeModel.test.js checks the two hold the same pages). */
const VIEWS = {
  qa: (route) => <QaPage route={route} />,
  tasks: () => <TasksPage />,
  datasets: () => <DatasetList />,
  dataset: (route) => <DatasetPage route={route} />,
  pipelines: () => <PipelinesPage />,
  pipelinenew: () => <PipelineNew />,
  pipeline: (route) => <PipelinePage key={route.name} route={route} />,
  sources: () => <SourcesPage />,
  source: (route) => <SourcePage key={route.name} route={route} />,
  schedules: () => <SchedulesPage />,
  types: () => <TypesPage />,
  type: (route) => <TypePage route={route} />,
  typenew: () => <TypeForm key="new" />,
  typeedit: (route) => <TypeForm key={route.id} id={route.id} />,
  object: (route) => <ObjectPage key={`${route.id}/${route.n}`} route={route} />,
  relations: (route) => <RelationsPage route={route} />,
  relation: (route) => <RelationPage route={route} />,
  relationnew: () => <RelationForm key="new" />,
  relationedit: (route) => <RelationForm key={route.id} id={route.id} />,
  confirm: () => <ConfirmPage />,
  confirmgroup: (route) => <ConfirmGroupPage key={`${route.dataset}@${route.version}`} route={route} />,
  agents: () => <AgentsPage />,
  boards: () => <BoardsPage />,
  board: (route) => <BoardPage key={route.id} route={route} />,
  boardnew: () => <BoardEditor key="new" />,
  boardedit: (route) => <BoardEditor key={route.id} id={route.id} />,
  lineage: () => <LineagePage />,
  users: () => <UsersPage />,
  permissions: () => <PermissionsPage />,
  account: () => <AccountPage />,
  notices: () => <NoticesPage />,
  planned: (route) => <Planned route={route} />,
};

export function Shell() {
  const { user } = useAuth();
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const [menu, setMenu] = useState(false);
  const queueCount = useQueueCount(route);
  const unread = useNoticeCount(route);
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const first = useRef(true);
  useEffect(() => {
    window.scrollTo(0, 0);
    if (first.current) first.current = false;
    else document.querySelector("main h1")?.focus({ preventScroll: true });   // a followed link puts the reader at the new page's heading
  }, [route.page, route.name, route.key, route.id]);

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand-row">
          <strong className="brand">OntoPoc</strong>
          <button className="plain menu-button" onClick={() => setMenu(!menu)} aria-expanded={menu}>菜单</button>
        </div>
        <Navigation active={navKeyOf(route)} open={menu} onPick={() => setMenu(false)} count={queueCount} unread={unread} />
      </aside>
      {!VIEWS[route.page] ? <NotFound /> : mayOpen(route.page, user) ? VIEWS[route.page](route) : <Forbidden />}
    </div>
  );
}
