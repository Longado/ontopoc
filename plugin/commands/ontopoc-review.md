---
description: 逐项确认一次 OntoPoc 运行：看对象、关系和体检，把用户的判断保存下来
argument-hint: "[saved_as]"
---

陪用户逐项确认一次 OntoPoc 运行。参数：$ARGUMENTS

1. 没给 saved_as 就调 `list_runs`，列出最近几次让用户选。
2. 调 `run_overview`（里面的 `open_items` 是要带去和客户确认的事）、`list_objects`（带 `include_wrong: true`，这样之前判过错的也能看到）、`list_relations`（同样带 `include_wrong: true`）和 `data_check`。
3. 先把 `open_items` 一条条讲给用户：每条的 `ask` 是能直接问客户的一句话，`facts` 是依据，`from_model` 为 true 的是模型的说法，要说明；`open_items` 是 null 说明本机服务是旧版本，照实说。问答的答案里有模型自己加的条件（`list_questions` 里 `evidence.filters` 的 `not_in_question`）时，说出条件和筛掉多少；用户要去掉才用 `drop_filter` 去掉重算（不调模型）；用户没定之前不要 `fix_question`。`open_items` 里带 `requeried: true` 的项是已经去掉条件重算过、验收题里存的还是旧答案：要问的是要不要用新答案替换验收题，不要再 `drop_filter`。
4. 按对象一个个给用户看：名称、来自哪张表、按什么识别、数据里有多少个、这次的判断（`verdict`），以及上次对这个文件的判断（`last_time`，重传时才有；上次判错的要特别说出来）。体检里跟这个对象有关的问题一并说。关系同样。已经判过的放后面，没判的先看。
5. 判断只能来自用户。**不要替用户判对错**，也不要根据体检结果替他打勾；用户没说的就是"没判"。用户可以改名，也可以补上漏掉的对象。
6. 用户说完之后，把他的判断整理成 `{"types": {...}, "relations": {...}, "added": [...]}` 念给他听，他确认了再调 `confirm_ontology` 保存。
7. 保存后告诉用户：这份判断会跟着这个文件走，下次再上传同一份或新版本时会自动预填，判错的对象不会再进问答和导出。
