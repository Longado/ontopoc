import { useEffect, useState } from "react";

import { RecallWorkspace } from "./RecallWorkspace.jsx";
import { PublicRecallReview } from "./PublicRecallReview.jsx";

const copy = {
  zh: { title: "召回范围研判工作台", landing: "产品首页", scenario: "工作场景",
        subtitle: { public: "公开数据 · 自动搭建本体 · 人工复核", recall: "公开历史召回 · 本地核对" },
        tabs: { public: "汽车召回范围研判（NHTSA）", recall: "事件 95876 核对清单" } },
  en: { title: "RECALL SCOPE WORKBENCH", landing: "PRODUCT HOME", scenario: "Scenario",
        subtitle: { public: "PUBLIC DATA · AUTO-BUILT ONTOLOGY · HUMAN REVIEW", recall: "PUBLIC HISTORICAL RECALL · LOCAL LOOKUP" },
        tabs: { public: "Vehicle recall scope (NHTSA)", recall: "Public recall lookup" } },
};

export function StandaloneDemo() {
  const [language, setLanguage] = useState("zh");
  const [scenario, setScenario] = useState("public");
  const [recallBusy, setRecallBusy] = useState(false);
  const t = copy[language];

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  return <main className="standalone-demo">
    <header className="standalone-demo-header">
      <a className="standalone-demo-brand" href="/landing" aria-label="OntoPoc product home">
        <img src="/assets/ontopoc-logo.png" alt="OntoPoc" />
      </a>
      <div className="standalone-demo-title">
        <strong>{t.title}</strong>
        <span>{t.subtitle[scenario]}</span>
      </div>
      <div className="standalone-demo-actions">
        <a href="/landing">{t.landing}</a>
        <div className="standalone-language-switch" aria-label="Language">
          <button type="button" className={language === "zh" ? "is-active" : ""} aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>中</button>
          <button type="button" className={language === "en" ? "is-active" : ""} aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
        </div>
      </div>
    </header>
    <nav className="recall-surface-switch" aria-label={t.scenario}>
      {Object.entries(t.tabs).map(([key, label]) => <button key={key} type="button" disabled={recallBusy} aria-pressed={scenario === key} onClick={() => setScenario(key)}>{label}</button>)}
    </nav>
    <section className="standalone-demo-workspace" aria-label={t.title}>
      {scenario === "public" ? <PublicRecallReview language={language} /> : <RecallWorkspace language={language} onBusyChange={setRecallBusy} />}
    </section>
  </main>;
}
