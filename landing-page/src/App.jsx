import { useEffect, useState } from "react";
import "./Landing.css";

const copy = {
  zh: {
    nav: [["#problem", "问题"], ["#method", "做法"], ["#proof", "验证"], ["#example", "示例场景"], ["#limits", "边界"]],
    open: "打开工作台",
    kicker: "上传建本体 · 自动评测",
    title: ["上传一份业务文件，", "得到公司本体，和它的体检报告"],
    lead: "交一份数据表（CSV、Excel）或业务文档（Markdown、Word、PDF）。模型提出本体里有哪些对象、按什么识别、彼此怎么关联，代码拿每一行数据核验；然后自动做三项评测：数据体检、业务问答、对照标准答案。",
    problemKicker: "问题",
    problemTitle: "本体画出来容易，知道它对不对难",
    problems: [
      ["靠人画，慢", "对着几张表开会、画图、改表，画完也说不清哪里跟数据对不上。"],
      ["让模型画，看着都对", "模型直接读表给出的本体头头是道，但字段是否都有去处、关系在数据里连不连得上，不逐行核验看不出来。"],
      ["数据本身有毛病", "同一个客户编号在两行里城市不同，订单引用了客户表里没有的客户；本体再好，也会被这些拖累。"],
      ["每次跑出来不一样", "同一份文件重跑，模型搭的本体会有出入。示例公司跑了两次（建模目的写得不一样），就差了一个对象和一条关系。"],
    ],
    methodKicker: "做法",
    methodTitle: "模型只提议，代码核验，每项评测都给证据",
    steps: [
      ["读文件", "表格自动找表头、跳过标题行；文档按段落切块，太长时写明只处理了前面多少。"],
      ["提出本体并核验", "模型看字段名和示例值提出对象、识别字段和关系；代码用全部数据检查，出错退回重做，最多三次。文档里的每个概念和关系都要引用原文，引用找不到就剔除。"],
      ["数据体检", "代码逐行计算：字段有没有去处、同一对象信息打不打架、编号写法是否统一、关系是否真连上、引用的对象找不找得到。每个问题都能在关系图上点到。"],
      ["业务问答与对照标准", "模型把业务问题写成查询，答案由代码在数据上算出，答不了就写明是本体缺了还是数据没有；上传一份人写的参考本体，代码逐项比出多了什么、少了什么。"],
    ],
    proofKicker: "验证",
    proofTitle: "示例公司：一份四张表的 Excel",
    proofNote: "demo_company.xlsx 是为演示合成的数据：客户 31 行、产品 12 行、订单 160 行、售后工单 45 行，里面故意埋了两个问题。工作台里可以直接打开这次的结果，也可以下载文件自己上传重跑。",
    facts: [["4 · 3", "个对象、条关系。模型第 1 次提交有字段没交代去处，被代码退回，第 2 次通过"], ["2", "处埋下的问题都被数据体检查出：客户 KH012 在两行里城市不同，订单引用的 KH099 不在客户表里"], ["5 / 6", "道模型出的业务问题由代码在数据上答出；剩下一道要同时按客户和产品分组，超出了查询写法，页面照实写明"], ["4 / 5", "个对象和人写的参考本体对上；少了“售后工程师”，因为数据里工程师只是一列姓名"]],
    exampleKicker: "示例场景",
    exampleTitle: "召回范围研判：同一套本体核验，用在公开数据上",
    exampleNote: "工作台里保留了一个完整的行业示例：从 NHTSA 取召回公告和车主投诉，自动搭本体、算出每个召回范围内外的同类投诉，模型读原文给出初判，由质量工程师逐条复核。雪佛兰 Bolt EV / EUV 2017–2023：13 个召回、679 条投诉；现代 Kona Electric 2019–2021：4 个召回、112 条投诉。",
    limitsKicker: "边界",
    limits: [
      "本体是模型的提议。结构核验通过只说明它和数据对得上，不说明它是业务上最好的划分；拿不准时上传参考本体比一比。",
      "同一份文件重跑，结果会有出入；页面会列出和上一次的差别。",
      "表格和文档现在分开建模，还不能把同一业务的表和文档合在一起。",
      "目前只在合成的示例公司和两份公开召回数据上验证过，还没有用真实公司的文件试过。",
      "上传的文件只存在本机；建模时字段名和少量示例值（文档则是正文）会发给配置的模型接口。",
    ],
    cta: "打开工作台，上传文件或先看示例公司",
    footer: "Trace scope. Review evidence.",
    source: "召回示例的数据来自 NHTSA 公开接口，2026-09-13 与 09-14 取数。OntoPoc 与 NHTSA、通用汽车、现代汽车无关联，页面内容不是官方结论，也不构成缺陷认定。示例公司是合成数据。",
  },
  en: {
    nav: [["#problem", "PROBLEM"], ["#method", "METHOD"], ["#proof", "EVIDENCE"], ["#example", "EXAMPLE"], ["#limits", "LIMITS"]],
    open: "OPEN WORKBENCH",
    kicker: "UPLOAD TO ONTOLOGY · AUTO EVALUATION",
    title: ["Upload one business file,", "get a company ontology and its health report"],
    lead: "Give it a table (CSV, Excel) or a business document (Markdown, Word, PDF). The model proposes the objects, how each is identified and how they relate; code checks the proposal against every row. Then three evaluations run on their own: a data check, business questions, and a comparison with a reference answer.",
    problemKicker: "PROBLEM",
    problemTitle: "Drawing an ontology is easy; knowing it is right is not",
    problems: [
      ["By hand, it is slow", "Meetings over a few tables, diagrams, revisions, and still no one can say where it disagrees with the data."],
      ["By model, it looks right", "A model reading the tables gives a convincing ontology, but whether every field is accounted for and every relation really links rows only shows up when you check each row."],
      ["The data has problems", "One customer ID with two cities, orders pointing at customers the customer table does not have; a good ontology still inherits these."],
      ["Every run differs", "Rerun on the same file and the model's ontology changes. The demo company's two runs (with differently worded purposes) differ by one object and one relation."],
    ],
    methodKicker: "METHOD",
    methodTitle: "The model proposes, code verifies, every evaluation shows its evidence",
    steps: [
      ["Read the file", "Tables get their header found and title rows skipped; documents are split by paragraph, and a cut is stated when a document is too long."],
      ["Propose and verify", "The model sees field names and example values and proposes objects, identity fields and relations; code checks all the data and sends errors back, three attempts at most. Every concept and relation from a document must quote the text, or it is dropped."],
      ["Data check", "Code computes, row by row, whether every field has a place, whether one object disagrees with itself, whether IDs are spelled one way, whether relations link and references resolve. Each finding opens on the graph."],
      ["Questions and reference", "The model writes business questions as queries and code computes the answers on the data, saying when the ontology or the data is missing something; upload a hand-written reference ontology and code lists what is extra and what is missing."],
    ],
    proofKicker: "EVIDENCE",
    proofTitle: "The demo company: one Excel file, four sheets",
    proofNote: "demo_company.xlsx is synthetic: 31 customers, 12 products, 160 orders, 45 after-sales tickets, with two problems planted on purpose. Open this run in the workbench, or download the file and upload it yourself.",
    facts: [["4 · 3", "objects and relations. Code sent the first proposal back for unaccounted fields; the second passed"], ["2", "planted problems both caught by the data check: customer KH012 has two cities, and orders reference KH099, which is not in the customer table"], ["5 / 6", "model-written questions answered by code on the data; the sixth groups by customer and product at once, beyond the query format, and the page says so"], ["4 / 5", "objects match the hand-written reference; the missing one is “after-sales engineer”, which the data holds only as a name column"]],
    exampleKicker: "EXAMPLE",
    exampleTitle: "Recall scope review: the same verification on public data",
    exampleNote: "The workbench keeps a full industry example: recall notices and owner complaints from NHTSA, an auto-built ontology, same-part complaints inside and outside each recall, a model's first call quoting the complaint, and a quality engineer's review. Chevrolet Bolt EV / EUV 2017–2023: 13 recalls, 679 complaints; Hyundai Kona Electric 2019–2021: 4 recalls, 112 complaints.",
    limitsKicker: "LIMITS",
    limits: [
      "The ontology is the model's proposal. Passing verification means it fits the data, not that it is the best business model; compare it with a reference when unsure.",
      "Reruns on the same file differ; the page lists the differences from the previous run.",
      "Tables and documents are modelled separately; one business's tables and documents cannot be combined yet.",
      "Verified only on the synthetic demo company and two public recall datasets, not yet on a real company's files.",
      "Uploaded files stay on this machine; field names and a few example values (for documents, the text) are sent to the configured model API.",
    ],
    cta: "Open the workbench: upload a file or start with the demo company",
    footer: "Trace scope. Review evidence.",
    source: "Recall example data from the NHTSA public API, fetched 2026-09-13 and 09-14. OntoPoc is not affiliated with NHTSA, General Motors or Hyundai; nothing here is an official finding or a defect determination. The demo company is synthetic.",
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

    <section className="landing-section" id="example">
      <p className="landing-kicker">{t.exampleKicker}</p>
      <h2>{t.exampleTitle}</h2>
      <p className="landing-note">{t.exampleNote}</p>
    </section>

    <section className="landing-section landing-limits" id="limits">
      <p className="landing-kicker">{t.limitsKicker}</p>
      <ul>{t.limits.map((line) => <li key={line}>{line}</li>)}</ul>
      <a className="landing-cta" href="/">{t.cta}</a>
    </section>

    <footer className="landing-footer"><img src="/assets/ontopoc-logo-light.png" alt="OntoPoc" /><p>{t.footer}</p><p className="landing-source">{t.source}</p><p>© 2026 OntoPoc</p></footer>
  </div>;
}
