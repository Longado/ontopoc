import { useEffect, useState } from "react";

import { TrialWorkspace } from "./TrialWorkspace.jsx";

const copy = {
  zh: {
    title: "本体建模工作台",
    boundary: "synthetic_demo · READ ONLY",
    landing: "产品首页",
  },
  en: {
    title: "ONTOLOGY MODELING WORKBENCH",
    boundary: "synthetic_demo · READ ONLY",
    landing: "PRODUCT HOME",
  },
};

export function StandaloneDemo() {
  const [language, setLanguage] = useState("zh");
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
        <span>{t.boundary}</span>
      </div>
      <div className="standalone-demo-actions">
        <a href="/landing">{t.landing}</a>
        <div className="standalone-language-switch" aria-label="Language">
          <button type="button" className={language === "zh" ? "is-active" : ""} aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>中</button>
          <button type="button" className={language === "en" ? "is-active" : ""} aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
        </div>
      </div>
    </header>
    <section className="standalone-demo-workspace" aria-label={t.title}>
      <TrialWorkspace language={language} />
    </section>
  </main>;
}
