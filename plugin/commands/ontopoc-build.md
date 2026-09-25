---
description: 用 OntoPoc 把业务表格或一份文档建成本体草案（模型提出，代码逐行核验）
argument-hint: "[文件路径…] [想弄清的问题]"
---

用 OntoPoc 的 MCP 工具为用户建本体。参数：$ARGUMENTS

1. 先调 `health`。连不上就告诉用户：在 OntoPoc 仓库里运行 `PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server` 启动服务，然后停下。
2. 从参数里取出文件路径和想弄清的问题。缺文件就问用户要；问题可以没有。数据表（.csv .xlsx）可以一次传几张；文档（.md .txt .docx .pdf）一次一份。
3. 同一个文件以前建过（`list_runs` 里能找到同名文件），问用户这是不是那份的新版本；是的话把那次的 saved_as 作为 `previous` 传入。
4. 文档要按组织来读（公司组织、岗位、分工）时，问用户一句，是的话传 `mode: "org"`。
5. 先调 `preview_upload` 告诉用户会发给模型哪些字段名和示例值，再调 `build_ontology`。它要等建完才返回，常常要半分钟到几分钟，先跟用户说一声。
6. 建完用 `run_overview` 给用户看：几个对象、几条关系、体检过了几项、建模目的里的问题答没答出来。不要自己下结论说本体对不对，那是用户的判断。最后告诉用户可以用 `/ontopoc:ontopoc-review` 逐项确认，或者在浏览器打开 OntoPoc 页面。
