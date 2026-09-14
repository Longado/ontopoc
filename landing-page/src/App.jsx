import { useEffect, useState } from "react";
import "./Landing.css";

const copy = {
  zh: {
    nav: [["#problem", "问题"], ["#method", "做法"], ["#proof", "验证"], ["#limits", "边界"]],
    open: "打开工作台",
    kicker: "公开数据 · 召回范围研判",
    title: ["召回发布后，", "哪些同类问题落在范围外？"],
    lead: "把召回公告和车主投诉两份公开数据交给系统：它自动搭建本体，代码逐项核验，算出每个召回范围内外的同类投诉，模型读原文给出初判，最后由质量工程师逐条复核。",
    problemKicker: "问题",
    problemTitle: "范围外的同类投诉，靠人翻几百条很容易漏",
    problems: [
      ["名称对不上", "召回写 “SERVICE BRAKES, HYDRAULIC”，投诉写 “SERVICE BRAKES”，按名字连就是零条。"],
      ["日期格式不一样", "召回是日/月/年，投诉是月/日/年，并排看会把先后弄反。"],
      ["召回一次接一次", "同一缺陷五次召回互相引用，第几次修复后又出问题，得读原文才知道。"],
      ["初判不能当结论", "同样的输入重跑一次，Bolt 电池召回 287 条初判里有 53 条变了，多是“不是”和“说不清”互换；temperature 0 也一样，必须有人复核。"],
    ],
    methodKicker: "做法",
    methodTitle: "模型只做判断，每一步由代码核验，人做最后决定",
    steps: [
      ["自动搭建本体", "模型只看字段名和示例值，提出对象、身份字段、关系、时间字段、过滤条件；代码用全部记录核验 17 项，出错退回重做，最多三次。"],
      ["跨来源名称对应", "只出现在一个来源的名称交给模型提出对应，代码核验确实多连上记录才采纳，经对应连上的候选单独标出。"],
      ["范围与时间", "每个召回算出覆盖的车型年款和同部件投诉，分成范围内、其他召回已覆盖、所有召回之外；每条标召回前后与间隔天数。"],
      ["初判与复核", "模型判“同一故障”必须引用原文，代码核对引用真在原文里；质量工程师逐条复核，复核结果就是校准模型的标注。"],
    ],
    proofKicker: "验证",
    proofTitle: "两家车企的公开数据，同一套代码",
    proofNote: "从 NHTSA 取数：雪佛兰 Bolt EV / EUV 2017–2023，2026-09-13 取数，13 个召回、679 条投诉；现代 Kona Electric 2019–2021，2026-09-14 取数，4 个召回、112 条投诉（含 5 条车型名只写 KONA、按车架号认出的电动版投诉）。",
    facts: [["17", "类本体错误检查。Bolt 上模型第 1 次提交被退回、第 2 次通过；Kona 这次第 1 次就通过"], ["0 → 34", "Bolt 刹车召回的候选投诉，靠一条核验过的名称对应补回；同一条对应在 Kona 上补回 12 条"], ["43", "条 Bolt 电池投诉落在所有召回之外、都在召回之后。这是待复核的候选，模型初判 41 条不是同一缺陷、2 条说不清"], ["10", "条 Kona 2021 款电池投诉落在两个电池召回之外，因为这两个召回只覆盖 2019–2020 款"]],
    limitsKicker: "边界",
    limits: [
      "范围只到车型年款，召回公开数据没有车架号。",
      "模型初判仅供参考，还没有人工标注的回归样本。",
      "只在两份公开数据上验证过（雪佛兰 Bolt、现代 Kona）；四个角色是为召回与投诉的范围研判设计的，不是任意问题的本体平台。",
      "复核是本机记录，不代表缺陷已确认、车辆已召回或已处置。",
    ],
    cta: "打开工作台，从电池召回开始",
    footer: "Trace scope. Review evidence.",
    source: "数据来自 NHTSA 公开接口，2026-09-13 与 09-14 取数。OntoPoc 与 NHTSA、通用汽车、现代汽车无关联，页面内容不是官方结论，也不构成缺陷认定。",
  },
  en: {
    nav: [["#problem", "PROBLEM"], ["#method", "METHOD"], ["#proof", "EVIDENCE"], ["#limits", "LIMITS"]],
    open: "OPEN WORKBENCH",
    kicker: "PUBLIC DATA · RECALL SCOPE REVIEW",
    title: ["After a recall,", "which similar complaints fall outside its scope?"],
    lead: "Give the system two public sources, recall notices and owner complaints. It builds the ontology, verifies every piece in code, computes same-part complaints inside and outside each recall, lets a model read the complaint text for a first call, and leaves the decision to a quality engineer.",
    problemKicker: "PROBLEM",
    problemTitle: "Out-of-scope complaints are easy to miss by hand",
    problems: [
      ["Names differ", "Recalls say “SERVICE BRAKES, HYDRAULIC”, complaints say “SERVICE BRAKES”; an exact join finds nothing."],
      ["Date formats differ", "Recalls are day/month/year, complaints month/day/year; read side by side, before and after get swapped."],
      ["Recalls chain", "Five recalls for one defect reference each other; which repair failed is only in the prose."],
      ["First calls drift", "Rerun on identical inputs, 53 of 287 first calls on the Bolt battery recall changed, mostly between “not the same” and “unclear”, even at temperature 0; a human has to review."],
    ],
    methodKicker: "METHOD",
    methodTitle: "The model judges, code verifies every step, people decide",
    steps: [
      ["Auto-built ontology", "The model sees only field names and samples and proposes objects, identities, relations, time fields and filters; code checks 17 rules on all records and sends errors back, three attempts at most."],
      ["Cross-source aliases", "Values found in only one source go to the model for a mapping; code keeps a mapping only when it links more records, and marks candidates that depend on it."],
      ["Scope and time", "Each recall yields its covered model years and same-part complaints in three buckets, every complaint dated before or after the recall."],
      ["First call and review", "A “same defect” verdict must quote the complaint, and code checks the quote is really there; the engineer reviews each one, and those reviews become the calibration labels."],
    ],
    proofKicker: "EVIDENCE",
    proofTitle: "Two automakers' public data, one codebase",
    proofNote: "From NHTSA: Chevrolet Bolt EV / EUV 2017–2023, fetched 2026-09-13, 13 recalls and 679 complaints; Hyundai Kona Electric 2019–2021, fetched 2026-09-14, 4 recalls and 112 complaints (including 5 filed as plain KONA and recognised as electric by VIN).",
    facts: [["17", "kinds of ontology error checked; on Bolt the model was sent back once and passed on the second attempt, on Kona it passed first time"], ["0 → 34", "Bolt brake recall candidates recovered by one verified alias; the same alias recovers 12 on Kona"], ["43", "Bolt battery complaints outside every recall, all filed after it. They are candidates to review: the model's first call is 41 not the same defect, 2 unclear"], ["10", "Kona 2021 battery complaints outside both battery recalls, which cover only 2019–2020"]],
    limitsKicker: "LIMITS",
    limits: [
      "Scope stops at model year; public recall data has no VIN.",
      "Model verdicts are first calls; there is no human-labelled regression set yet.",
      "Verified on two public datasets (Chevrolet Bolt, Hyundai Kona); the four roles fit recall-versus-complaint scope, not arbitrary questions.",
      "Reviews are local records, not confirmation that a defect exists or a vehicle was recalled.",
    ],
    cta: "Open the workbench and start with the battery recall",
    footer: "Trace scope. Review evidence.",
    source: "Data from the NHTSA public API, fetched 2026-09-13 and 09-14. OntoPoc is not affiliated with NHTSA, General Motors or Hyundai; nothing here is an official finding or a defect determination.",
  },
};

export function App() {
  const [language, setLanguage] = useState("zh");
  const t = copy[language];
  useEffect(() => { document.documentElement.lang = language === "zh" ? "zh-CN" : "en"; }, [language]);

  return <div className="landing">
    <header className="landing-header">
      <a className="landing-brand" href="#top" aria-label="OntoPoc"><img src="/assets/ontopoc-logo.png" alt="OntoPoc" /></a>
      <nav aria-label="Sections">{t.nav.map(([href, label]) => <a key={href} href={href}>{label}</a>)}</nav>
      <div className="landing-actions">
        <div className="landing-language" aria-label="Language">
          <button type="button" className={language === "zh" ? "is-active" : ""} aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>中</button>
          <button type="button" className={language === "en" ? "is-active" : ""} aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
        </div>
        <a className="landing-open" href="/">{t.open}</a>
      </div>
    </header>

    <section className="landing-hero" id="top">
      <img className="landing-field" src="/assets/decision-field.png" alt="" aria-hidden="true" />
      <p className="landing-kicker">{t.kicker}</p>
      <h1>{t.title.map((line) => <span key={line}>{line}</span>)}</h1>
      <p className="landing-lead">{t.lead}</p>
      <a className="landing-cta" href="/">{t.cta}</a>
    </section>

    <section className="landing-section" id="problem">
      <p className="landing-kicker">{t.problemKicker}</p>
      <h2>{t.problemTitle}</h2>
      <div className="landing-grid">{t.problems.map(([head, body]) => <article key={head}><h3>{head}</h3><p>{body}</p></article>)}</div>
    </section>

    <section className="landing-section landing-dark" id="method">
      <p className="landing-kicker">{t.methodKicker}</p>
      <h2>{t.methodTitle}</h2>
      <ol className="landing-steps">{t.steps.map(([head, body], i) => <li key={head}><span>{String(i + 1).padStart(2, "0")}</span><h3>{head}</h3><p>{body}</p></li>)}</ol>
    </section>

    <section className="landing-section" id="proof">
      <p className="landing-kicker">{t.proofKicker}</p>
      <h2>{t.proofTitle}</h2>
      <p className="landing-note">{t.proofNote}</p>
      <div className="landing-facts">{t.facts.map(([n, label]) => <div key={label}><strong>{n}</strong><span>{label}</span></div>)}</div>
    </section>

    <section className="landing-section landing-limits" id="limits">
      <p className="landing-kicker">{t.limitsKicker}</p>
      <ul>{t.limits.map((line) => <li key={line}>{line}</li>)}</ul>
      <a className="landing-cta" href="/">{t.cta}</a>
    </section>

    <footer className="landing-footer"><img src="/assets/ontopoc-logo-light.png" alt="OntoPoc" /><p>{t.footer}</p><p className="landing-source">{t.source}</p><p>© 2026 OntoPoc</p></footer>
  </div>;
}
