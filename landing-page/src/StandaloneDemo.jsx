import { useEffect, useState } from "react";

import { TrialWorkspace } from "./TrialWorkspace.jsx";
import { RecallWorkspace } from "./RecallWorkspace.jsx";
import { PublicRecallReview } from "./PublicRecallReview.jsx";

const copy = {
  zh: {
    title: "事件范围核对工作台",
    boundary: "synthetic_demo · SESSION ONLY",
    landing: "产品首页",
  },
  en: {
    title: "EVENT SCOPE WORKBENCH",
    boundary: "synthetic_demo · SESSION ONLY",
    landing: "PRODUCT HOME",
  },
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
        <span>{scenario === "public" ? (language === "zh" ? "公开数据 · 自动搭建本体 · 人工复核" : "PUBLIC DATA · AUTO-BUILT ONTOLOGY · HUMAN REVIEW") : scenario === "recall" ? (language === "zh" ? "公开历史召回 · 本地核对" : "PUBLIC HISTORICAL RECALL · LOCAL LOOKUP") : t.boundary}</span>
      </div>
      <div className="standalone-demo-actions">
        <a href="/landing">{t.landing}</a>
        <div className="standalone-language-switch" aria-label="Language">
          <button type="button" className={language === "zh" ? "is-active" : ""} aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>中</button>
          <button type="button" className={language === "en" ? "is-active" : ""} aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
        </div>
      </div>
    </header>
    <nav className="recall-surface-switch" aria-label={language === "zh" ? "工作场景" : "Scenario"}>
        <button type="button" disabled={recallBusy} aria-pressed={scenario === "public"} onClick={() => setScenario("public")}>{language === "zh" ? "汽车召回范围研判（NHTSA）" : "Vehicle recall scope (NHTSA)"}</button>
        <button type="button" disabled={recallBusy} aria-pressed={scenario === "recall"} onClick={() => setScenario("recall")}>{language === "zh" ? "事件 95876 核对清单" : "Public recall lookup"}</button>
        <button type="button" disabled={recallBusy} aria-pressed={scenario === "demo"} onClick={() => setScenario("demo")}>{language === "zh" ? "示例建模（只读）" : "Synthetic modeling demo"}</button>
    </nav>
    <section className="standalone-demo-workspace" aria-label={t.title}>
      {scenario === "public" ? <PublicRecallReview language={language} /> : scenario === "recall" ? <RecallWorkspace language={language} onBusyChange={setRecallBusy} /> : <TrialWorkspace language={language} />}
    </section>
  </main>;
}
