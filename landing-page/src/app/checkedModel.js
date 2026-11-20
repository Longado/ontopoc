// Numbers the team has checked (checked_numbers.py): the words of a check on a board card or a saved answer, and which cards and answers can be checked.
// The service decides the mark (same, moved, refused, differs) by working the number out again; this only says it.
import { formatDate, t } from "./i18n/index.js";
import { formatNumber } from "./explorerModel.js";

/** The mark of a check, in a word: 一致, 变了, 拒答, 不一致. */
export const checkWord = (status) => t(`boards.check.word.${status}`);

/** Who checked it when, and for a builder first the team's number and its source: "团队的数 119,810 · 财务 10 月报表 · Bob · 2026年11月20日". A viewer is sent only who and when. */
export const checkLine = (check) => [check.trusted != null ? t("boards.check.trusted", { value: formatNumber(check.trusted) }) : "", check.note ?? "", check.by, formatDate(check.at)].filter(Boolean).join(" · ");

const movedText = (m) => (m.to == null ? t("boards.check.gone", { name: m.name }) : t("boards.check.version", { name: m.name, from: m.from, to: m.to }));

/** What a builder is told beyond the mark: what OntoPoc computed then and now and which versions moved, why it refuses, or that it never matched. "" for a match and for a viewer (no numbers sent). */
export function checkDetail(check) {
  if (check.trusted == null) return "";
  if (check.status === "refused") return t("boards.check.refused", { reason: check.reason ?? "" });
  if (check.status === "differs") return t("boards.check.differs", { now: formatNumber(check.now) });
  if (check.status !== "moved") return "";
  const head = t("boards.check.moved", { then: formatNumber(check.then), now: formatNumber(check.now) });
  return check.moved?.length ? t("boards.check.movedSince", { head, moved: check.moved.map(movedText).join(t("ask.sep")) }) : head;
}

/** The line at the top of a board: "3 个数核对过：1 一致、1 变了、0 拒答、1 不一致", or why the checks are not held against this read; "" when there is none. */
export const summaryText = (checked) => checked?.text ?? "";

/** The one number an answer works out (a total, or a count), or null: groups, a graph, a share, an unknown total, rows a rule limited. */
function oneNumber(record) {
  const a = record?.answer;
  if (!(record?.status === "answered" || record?.status === "no_data") || !a || a.groups || a.graph || a.share || record.limited_by_rule?.length) return null;
  if (a.measure) return a.measure.value ?? null;
  return a.total ?? null;
}

/** The number a board card shows that a builder can mark as checked: one number on confirmed definitions over all rows; null otherwise. */
export function cardNumber(component) {
  if (component.status !== "ok" || !component.result?.standing?.confirmed) return null;
  if (component.chart?.kind === "query") return oneNumber(component.result);
  if (component.chart?.kind !== "number" || component.result.rows_limited) return null;
  return component.result.value ?? null;
}

/** The number of a saved answer that its asker can mark as checked; null for anything else (a query that was not kept has no id). */
export const answerNumber = (record) => (record?.id ? oneNumber(record) : null);
