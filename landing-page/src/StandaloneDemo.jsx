import { useEffect, useState } from "react";

import { RecallWorkspace } from "./RecallWorkspace.jsx";
import { PublicRecallReview } from "./PublicRecallReview.jsx";

const copy = {
  zh: { nav: "工作台导航", landing: "产品首页", lang: "EN",
        tabs: { public: "召回范围研判", recall: "事件 95876 核对" },
        hints: { public: "NHTSA 公开数据", recall: "openFDA · 需本机服务" } },
  en: { nav: "Workbench", landing: "Product home", lang: "中文",
        tabs: { public: "Recall scope review", recall: "Event 95876 lookup" },
        hints: { public: "NHTSA public data", recall: "openFDA · local service" } },
};

export function StandaloneDemo() {
  const [language, setLanguage] = useState("zh");
  const [scenario, setScenario] = useState("public");
  const [recallBusy, setRecallBusy] = useState(false);
  const t = copy[language];

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  return <main className="app-shell">
    <aside className="app-side">
      <a className="app-brand" href="/landing" aria-label="OntoPoc product home">
        <img src="/assets/ontopoc-logo.png" alt="OntoPoc" />
      </a>
      <nav className="app-nav" aria-label={t.nav}>
        {Object.entries(t.tabs).map(([key, label]) => <button key={key} type="button" disabled={recallBusy}
          aria-current={scenario === key ? "page" : undefined} onClick={() => setScenario(key)}>
          <i aria-hidden="true" /><span>{label}<small>{t.hints[key]}</small></span>
        </button>)}
        <a href="/landing"><i aria-hidden="true" /><span>{t.landing}</span></a>
      </nav>
      <button type="button" className="app-lang" onClick={() => setLanguage(language === "zh" ? "en" : "zh")}>{t.lang}</button>
    </aside>
    <section className="app-main" aria-label={t.tabs[scenario]}>
      {scenario === "public" ? <PublicRecallReview language={language} /> : <RecallWorkspace language={language} onBusyChange={setRecallBusy} />}
    </section>
  </main>;
}
