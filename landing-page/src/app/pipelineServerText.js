// The words the pipeline service itself uses (in Chinese), which the pages read or match. They are data from the service, not interface text, so they are not translated and
// this file is not in i18n/converted.js. Everything the person reads is built from the dictionaries (i18n/en/pipeline.js) in pipelineModel.js.

/** How the service orders the operator categories of its catalogue. */
export const CATEGORY_ORDER = ["常用", "清洗", "类型", "日期", "数值", "文本", "汇总"];

/** A column name that reads as a key: the ending of a Chinese or English key name. */
export const KEY_LIKE = /(号|编号|编码|代码|键|id|key)$/i;

/** The service's own default result name for a statistic ("求和_金额"). */
export const AGG_SERVER = { sum: "求和", count: "计数", count_distinct: "去重计数", avg: "平均", min: "最小", max: "最大", median: "中位数", p25: "P25", p75: "P75" };

/** The units of an AI summary, as the service stores them. */
export const UNIT_CHARS = "字";
export const UNIT_SENTENCES = "句";

/** The shapes of the service's messages that friendlyError reads: "步骤 t1 的第 1 个操作（filter）：没有列「」". */
export const SERVER_PATTERNS = {
  step: /步骤 ([^\s：，、（）。]+?)(?: 的第 (\d+) 个操作（(\w+)）)?(?=[：，、。 ）]|$)/g,
  noColumn: /没有列「」|(?<=：)没选列$/,
  datasetEmpty: /数据集「」(?:不存在|没有)?/,
  noneChosen: /没有(\S{0,4}?)「」/,
  emptyQuotes: /「」/g,
  inNoColumn: /里没有列\s*$/,
};

/** What the service says when the definition was saved by someone else meanwhile (the page then offers to reload). */
export const CHANGED_BY_OTHER = "被改了";
