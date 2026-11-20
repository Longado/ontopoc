import React, { useEffect, useRef, useState } from "react";
import { AccountPage } from "./AccountPage.jsx";
import { AgentsPage } from "./AgentsPage.jsx";
import { BoardEditor } from "./BoardEditor.jsx";
import { BoardPage, BoardsPage } from "./BoardsPage.jsx";
import { WORKSPACE_CHANGED, getNotices, getQueueCount } from "./api.js";
import { NoticesPage } from "./NoticesPage.jsx";
import { useAuth } from "./Auth.jsx";
import { askOff } from "./demoModel.js";
import { useDemoAsk } from "./useDemoAsk.js";
import { t } from "./i18n/index.js";
import { canBuild, isGuest, roleLabel, searchPlaceholder } from "./authModel.js";
import { SettingsPage } from "./SettingsPage.jsx";
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
import { HomePage } from "./HomePage.jsx";
import { PLANNED, mayOpen, navFor, navKeyOf, navLabelOf, parseRoute } from "./routeModel.js";
import { recordVisit } from "./searchModel.js";
import { CommandPalette } from "./ui/CommandPalette.jsx";
import { Icon } from "./ui/Icon.jsx";
import { LanguageSwitch } from "./ui/LanguageSwitch.jsx";
import { usePopover } from "./ui/MoreMenu.jsx";

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

/** {unread, any}: how many of this person's notices are unread, and whether they have any at all; read again whenever the page changes. */
function useNoticeCount(route) {
  const [count, setCount] = useState({ unread: 0, any: false });
  const [round, setRound] = useState(0);
  useEffect(() => {
    const again = () => setRound((n) => n + 1);
    window.addEventListener(WORKSPACE_CHANGED, again);
    return () => window.removeEventListener(WORKSPACE_CHANGED, again);
  }, []);
  useEffect(() => {
    let live = true;
    getNotices().then((b) => live && setCount({ unread: b.unread, any: (b.notices ?? []).length > 0 }), () => live && setCount({ unread: 0, any: false }));
    return () => {
      live = false;
    };
  }, [route.page, route.id, route.name, round]);
  return count;
}

const store = {
  read: (key, fallback) => {
    try {
      return JSON.parse(window.localStorage.getItem(key)) ?? fallback;
    } catch {
      return fallback;
    }
  },
  write: (key, value) => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch { /* a private window may refuse: the choice is just not remembered */ }
  },
};

/** The avatar and its menu: the person's name and role, the language switch, My account, Sign out. */
function AvatarMenu() {
  const { user, auth, signOut, feedbackUrl } = useAuth();
  const [open, setOpen, ref] = usePopover();
  if (!auth) return <span className="top-local muted">{t("shell.avatar.local")}</span>;
  return (
    <span className="menu-wrap" ref={ref}>
      <button className="avatar" aria-label={t("shell.avatar.aria", { name: user.display_name })} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>{[...user.display_name][0]}</button>
      {open && (
        <div className="menu menu-right" role="menu">
          <div className="menu-who"><strong>{user.display_name}</strong><span className="muted small">{roleLabel(user.role)}</span></div>
          {!isGuest(user) && <a role="menuitem" className="menu-item" href="#/account" onClick={() => setOpen(false)}><Icon name="user" />{t("shell.avatar.account")}</a>}
          <LanguageSwitch />
          {feedbackUrl && <a role="menuitem" className="menu-item" href={feedbackUrl} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)}><Icon name="external" />{t("shell.avatar.feedback")}</a>}
          <button role="menuitem" className="menu-item" onClick={signOut}><Icon name="logout" />{t("shell.avatar.signOut")}</button>
        </div>
      )}
    </span>
  );
}

/** The slim line under the top bar for a demo guest: what this is, and a way out. */
function GuestBanner() {
  const { user, signOut } = useAuth();
  const demoAsk = useDemoAsk();
  const guest = isGuest(user);
  const at = useRef(null);
  useEffect(() => {
    const el = at.current;
    if (!el) return undefined;
    const root = document.documentElement;
    const measure = () => root.style.setProperty("--banner-h", `${el.offsetHeight}px`);   // the shell's heights and sticky offsets leave room for the banner
    measure();
    const watch = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    watch?.observe(el);
    return () => {
      watch?.disconnect();
      root.style.removeProperty("--banner-h");
    };
  }, [guest]);
  if (!guest) return null;
  const off = askOff(user, demoAsk);
  return (
    <div className="guest-banner" role="note" ref={at}>
      <span>{t("auth.guest.banner")}</span>
      {!off && <span>{t("auth.guest.try")}</span>}
      <span className="links">
        {off && <a href="#/boards">{t("auth.guest.openBoards")}</a>}
        <button className="plain" onClick={signOut}>{t("auth.guest.signOut")}</button>
      </span>
    </div>
  );
}

function TopBar({ onMenu, menuOpen, onSearch, count, unread }) {
  const { user } = useAuth();
  const mayBuild = canBuild(user);
  return (
    <header className="topbar">
      <button className="plain icon-button menu-button" onClick={onMenu} aria-expanded={menuOpen} aria-label={t("shell.menu")}><Icon name="menu" size={20} /></button>
      <a className="brand" href="#/home"><span className="brand-mark" aria-hidden="true" />OntoPoc</a>
      <span className="workspace-name" title={t("shell.workspace.title")}>{t("shell.workspace.name")}</span>
      <button className="searchbox" onClick={onSearch} aria-label={t("shell.search.aria")}>
        <Icon name="search" />
        <span className="searchbox-text">{searchPlaceholder(user)}</span>
        <kbd>⌘K</kbd>
      </button>
      <div className="top-right">
        {mayBuild && (
          <a className="top-count" href="#/confirm" title={t("shell.queue.title")} aria-label={t("shell.queue.aria", { count })}>
            <Icon name="check-circle" size={20} />{countText(count) && <span className="count-badge" data-tone="blue">{countText(count)}</span>}
          </a>
        )}
        <a className="top-count" href="#/notices" title={t("shell.notices.title")} aria-label={t("shell.notices.aria", { count: unread })}>
          <Icon name="bell" size={20} />{countText(unread) && <span className="count-badge" data-tone="red">{countText(unread)}</span>}
        </a>
        <AvatarMenu />
      </div>
    </header>
  );
}

function Navigation({ active, open, onPick, count, unread = 0, anyNotice = false, collapsed, onCollapse }) {
  const { user } = useAuth();
  const [closed, setClosed] = useState(() => store.read("ontopoc.nav.closed", {}));
  const toggle = (key) => {
    const next = { ...closed, [key]: !closed[key] };
    setClosed(next);
    store.write("ontopoc.nav.closed", next);
  };
  return (
    <nav className={`nav${open ? " open" : ""}${collapsed ? " icons" : ""}`} aria-label={t("shell.nav.aria")}>
      {navFor(user, { notices: anyNotice || active === "notices" }).map((group) => {
        const holdsActive = group.items.some((i) => i.key === active);
        const folded = group.label && closed[group.key] && !holdsActive && !collapsed;
        return (
          <div className="nav-group" key={group.key}>
            {group.label && (
              <button className="nav-heading" onClick={() => toggle(group.key)} aria-expanded={!folded} title={group.hint} aria-label={t("shell.nav.heading", { label: group.label, hint: group.hint })}>
                <span>{group.label}</span><Icon name={folded ? "chevron-right" : "chevron-down"} size={14} />
              </button>
            )}
            {!folded && group.items.map((item) => (
              <a key={item.key} href={item.href} title={collapsed ? item.label : undefined} className={item.key === active ? "active" : ""}
                aria-current={item.key === active ? "page" : undefined} aria-label={collapsed ? item.label : undefined} onClick={onPick}>
                <Icon name={item.icon} />
                <span className="nav-label">{item.label}</span>
                {item.key === "confirm" && countText(count) && <span className="count" aria-label={t("shell.nav.queueCount", { count })}>{countText(count)}</span>}
                {item.key === "notices" && countText(unread) && <span className="count" aria-label={t("shell.nav.noticeCount", { count: unread })}>{countText(unread)}</span>}
              </a>
            ))}
          </div>
        );
      })}
      <button className="nav-collapse" onClick={onCollapse} aria-label={collapsed ? t("shell.nav.expandSidebar") : t("shell.nav.collapseSidebar")}>
        <Icon name={collapsed ? "chevrons-right" : "chevrons-left"} /><span className="nav-label">{t("shell.nav.collapse")}</span>
      </button>
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
      <h1 tabIndex={-1}>{t("shell.forbidden.title")}</h1>
      <p className="muted">{t("shell.forbidden.text")} <a href="#/home">{t("common.backHome")}</a></p>
    </main>
  );
}

function NotFound() {
  return (
    <main className="page">
      <h1 tabIndex={-1}>{t("shell.notFound.title")}</h1>
      <p className="muted"><a href="#/home">{t("common.backHome")}</a></p>
    </main>
  );
}

/** What each page of routeModel.PAGES draws, one line each (routeModel.test.js checks the two hold the same pages). */
const VIEWS = {
  home: () => <HomePage />,
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
  settings: () => <SettingsPage />,
  users: () => <UsersPage />,
  permissions: () => <PermissionsPage />,
  account: () => <AccountPage />,
  notices: () => <NoticesPage />,
  planned: (route) => <Planned route={route} />,
};

/** A place's name for the recent list: the page's own heading once it has drawn, else the sidebar's word for it. */
const placeLabel = (route) => document.querySelector("main h1")?.textContent?.trim() || navLabelOf(route);

export function Shell() {
  const { user } = useAuth();
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const [menu, setMenu] = useState(false);
  const [collapsed, setCollapsed] = useState(() => store.read("ontopoc.nav.collapsed", false));
  const [palette, setPalette] = useState(false);
  const [recents, setRecents] = useState(() => store.read("ontopoc.recent", []));
  const queueCount = useQueueCount(route);
  const { unread, any: anyNotice } = useNoticeCount(route);
  useEffect(() => {
    const onChange = () => {
      setRoute(parseRoute(window.location.hash));
      setMenu(false);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  useEffect(() => {
    const key = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const first = useRef(true);
  useEffect(() => {
    window.scrollTo(0, 0);
    if (first.current) first.current = false;
    else document.querySelector("main h1")?.focus({ preventScroll: true });   // a followed link puts the reader at the new page's heading
  }, [route.page, route.name, route.key, route.id]);
  useEffect(() => {
    if (!VIEWS[route.page] || route.page === "home") return undefined;
    const href = window.location.hash;
    const timer = setTimeout(() => {
      setRecents((list) => {
        const next = recordVisit(list, { href, label: placeLabel(route) });
        store.write("ontopoc.recent", next);
        return next;
      });
    }, 700);   // after the page has drawn its heading
    return () => clearTimeout(timer);
  }, [route.page, route.name, route.key, route.id, route.n, route.tab]);
  const collapse = () => {
    store.write("ontopoc.nav.collapsed", !collapsed);
    setCollapsed(!collapsed);
  };

  return (
    <div className={`app${collapsed ? " app-collapsed" : ""}`}>
      <TopBar onMenu={() => setMenu(!menu)} menuOpen={menu} onSearch={() => setPalette(true)} count={queueCount} unread={unread} />
      <GuestBanner />
      <div className="shell">
        <aside className={`side${menu ? " open" : ""}`}>
          <Navigation active={navKeyOf(route)} open={menu} onPick={() => setMenu(false)} count={queueCount} unread={unread} anyNotice={anyNotice} collapsed={collapsed} onCollapse={collapse} />
        </aside>
        {menu && <div className="side-dim" onClick={() => setMenu(false)} />}
        {!VIEWS[route.page] ? <NotFound /> : mayOpen(route.page, user) ? VIEWS[route.page](route) : <Forbidden />}
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} user={user} recents={recents} />
    </div>
  );
}
