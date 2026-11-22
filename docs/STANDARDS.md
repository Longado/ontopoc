# OntoPoc 和 W3C 标准：OWL、SHACL、SKOS

[English](STANDARDS.en.md)

OntoPoc 的团队应用用自己的模型记团队的定义：带主键的对象类型、属性、代码列里每个代码的含义、关系、视图、派生属性；每一条都由代码对着数据检查，再由一位具名的人对着某一版数据确认。这个模型不是 OWL，OntoPoc 也不运行 OWL 推理机。它能做的是把已确认的定义写成两个文件，交给读这些标准的工具。这一页说明文件里有什么，每一部分在 OWL 和 SHACL 里是什么意思，以及哪些放不进去。

## 下载

- **地址。** `GET /api/workspace/agent/schema` 给一个 zip，里面是 `ontology.ttl` 和 `shapes.ttl`。`?file=ontology` 或 `?file=shapes` 只给其中一个 Turtle 文件。“AI 工具接入”页上，已确认定义的 CSV 旁边有下载链接。
- **谁能下载。** 登录的人都可以，包括查看者；令牌（只读或不是）以它的主人的身份下载。和 `GET /api/workspace/agent/standing?format=csv` 的 CSV 一样。
- **里面有什么。** 这个人能看到的已确认定义，和 CSV、MCP 工具 `describe_definitions` 是同一批、同样的写法。还在等确认的定义、这个人看不到的定义都不在里面，文件里也没有任何东西显示它存在：文件和一个根本没有这条定义的工作区生成的文件逐字节相同。对这个人隐藏的列不在里面。
- **不对模型开放的取值。** 建设者设成“取值不对模型开放”的代码列（在对象类型页上；`POST /api/workspace/types/privacy`），含义不写，和 CSV 里留空一样；确认本身（谁、什么时候、在哪版数据上）照 CSV 保留。读这种列的派生属性列出名字，不写它说的内容。
- **不影响“已确认”的改动。** 有些改动不会让定义离开“已确认”，例如类型改了说明、关系改了名字。文件按现在的写法写出这样的定义，和 CSV 一样。
- **人的名字。** 每条定义是谁确认的，照 CSV 给同一个人看到的写。文件不写下载它的人是谁。
- **没有数据。** 没有数据行，没有对象，没有数据的行数。只有结构。
- **是快照。** 文件写着生成时间。每条定义现在是不是还已确认，以 `GET /api/workspace/agent/standing` 为准。

## 每种定义写成什么

下表里“公理”指 OWL 里有逻辑含义的陈述。“注释”指 OWL 推理时当作不存在的陈述：OWL 2 规范说注释“对本体的逻辑方面没有影响”。注释里的文字是给人看的。

| OntoPoc 里的定义 | 在 `ontology.ttl` 里 | 是哪种陈述 | 在 `shapes.ttl` 里 |
|---|---|---|---|
| 对象类型 | `owl:Class`，带 `rdfs:label`（名字）和 `rdfs:comment`（说明） | 公理（声明一个类） | 一个带 `sh:targetClass` 的节点规则 |
| 主键 | `owl:hasKey ( … )`，列出主键列对应的属性 | 公理，但意思不同（见下文） | 每个主键列：`sh:minCount 1 ; sh:maxCount 1`。只有一列的主键：还检查同一个值不被两个对象用（对主键属性用 `sh:targetObjectsOf`、`sh:inversePath`、`sh:maxCount 1`）。几列组成的主键：不检查组合（见下文） |
| 属性（一列） | `owl:DatatypeProperty` 加 `owl:FunctionalProperty`，`rdfs:domain` 是所属类型，`rdfs:range` 是一个 XSD 数据类型（见下表），`rdfs:label` 是名字，`op:column` 是列名 | 公理；列名是注释 | — |
| 代码含义 | 每个代码列一个 `skos:ConceptScheme`，每个有含义的代码一个 `skos:Concept`（`skos:notation` 是代码，`skos:prefLabel` 是含义）。属性用 `op:codeList` 指向它的概念体系。数据里的值仍是普通的值，不把代码变成概念 | 关于概念体系和其中概念的断言（`skos:prefLabel` 是注释）；不是关于属性取值的公理 | `sh:in ( … )`：有含义的那些代码 |
| 关系 | `owl:ObjectProperty`，`rdfs:domain` 和 `rdfs:range` 是两头的类型。多对一：`owl:FunctionalProperty`。一对多：`owl:InverseFunctionalProperty`。一对一：两个都有。连接两边的那一对列写在 `op:definitionText` 里 | 公理；那一对列是注释 | 在起点类型上：`sh:class` 另一头的类型，多对一和一对一再加 `sh:maxCount 1`。一对多和一对一，在终点类型上：`sh:inversePath` 这个关系，`sh:maxCount 1` |
| 视图（取哪些行） | `owl:Class`，`rdfs:subClassOf` 所属类型，带 `op:definitionText`（OntoPoc 确认的那句话）和一句说明：这段话不是 OWL 公理 | “是子类”是公理；哪些行属于它只是文字 | — |
| 派生属性 | `owl:DatatypeProperty`，`rdfs:domain` 所属类型，`rdfs:range` 输出类型，带 `op:definitionText`（算式或统计的文字）和同样的说明 | 属性有声明；算法只是文字 | — |
| 谁确认、什么时候、在哪版数据上 | `op:definitionId`（CSV 里的编号）、`op:confirmedBy`、`op:confirmedAt`（`xsd:dateTime`）、`op:confirmedOnData`（例如 `订单 v1`） | 注释 | — |

`op:` 开头的是 OntoPoc 自己的注释属性，在文件开头以 `urn:ontopoc:vocab:` 声明。文件用到的 SKOS 词也在那里声明，类别照 SKOS 参考给的：`skos:Concept` 和 `skos:ConceptScheme` 是类，`skos:inScheme` 和 `skos:hasTopConcept` 是对象属性，`skos:notation` 是数据属性，`skos:prefLabel` 是注释属性。定义的另称（对象类型、属性、代码含义、视图、派生属性）写成 `skos:altLabel`，SKOS 也把它定为注释属性；只有文件里有另称时才声明它，所以没有另称的文件和以前一样。PROV-O 有记录谁在什么时候做了什么的词，但它们是给 `prov:Entity` 这类东西用的对象属性和数据属性（例子都用在个体上）；写在一个类上，就等于说这个类本身是这种东西。普通的注释属性只说要说的意思，不进入逻辑。

### 数据类型

OWL 2 有一张固定的数据类型表（“datatype map”），OWL 2 DL 本体不能用表外的 XSD 数据类型。`xsd:date` 和 `xsd:gYearMonth` 不在表里。所以：

| OntoPoc 类型 | 文件里的值域 | 文件里的说明 |
|---|---|---|
| 整数 | `xsd:integer` | — |
| 小数 | `xsd:decimal` | — |
| 文本 | `xsd:string` | — |
| 是否 | `xsd:boolean` | 数据里可能写成 是/否、Y/N；写成 `xsd:boolean` 是 true 或 false |
| 日期时间 | `xsd:dateTime` | 数据里可能用空格分开、不带秒；写成 `xsd:dateTime` 是 `YYYY-MM-DDThh:mm:ss` |
| 日期 | `xsd:dateTime` | 一天写成当天 00:00:00，例如 `2024-01-05T00:00:00` |
| 月份 | `xsd:string` | 写成 `YYYY-MM`，例如 `2024-01` |

规则文件不检查数据类型。

### 名字（IRI）

每个名字都以一个前缀开头：运行服务的人设了环境变量 `ONTOPOC_IRI_BASE` 就用它，没设就是 `urn:ontopoc:`。前缀写成 `https://主机名/路径/`（以 `/` 结尾）或 `urn:名字:`，只用字母、数字和 `. _ ~ -`；别的写法会让下载返回 409 并说明原因，不会悄悄换成默认值。前缀后面是固定的词，以及产品本来就限定只能用英文字母、数字和 `_` 的英文名：

- 类型是 `type/<英文名>`，关系是 `relation/<英文名>`，派生属性是 `type/<类型>/derived/<英文名>`；
- 属性是 `type/<类型>/column/<哈希>`，它的概念体系是 `…/codes`，视图是 `view/<哈希>`；`<哈希>` 是列名或视图名的 SHA-256 的前 16 位十六进制数；
- 规则文件里是 `shape/type/<类型>` 和 `shape/type/<类型>/key`；文件本身是 `ontology`。

人写的文字（名字、列名、说明）和代码取值只作为转义后的文字出现，从不进名字。代码对应的概念没有自己的名字（空白节点），在概念体系里靠 `skos:notation` 认出它，这正是 SKOS 对它的定义。换前缀，所有名字都会变。`urn:ontopoc:` 不是注册过的命名空间：这些名字在浏览器里打不开，而且每个工作区的默认值都一样，所以要把两个工作区的文件放到一起之前，先把前缀设成你们团队管的网址下面的地址。

## 为什么 OntoPoc 用规则检查，不跑推理机

OWL 按开放世界读文件：没写的是“不知道”，不是“不成立”。OntoPoc 会拒绝的地方，OWL 往往会推出新的结论：

- **主键重复。** OWL 2 说主键的意思是每个有名字的实例“由”这些值“唯一确定”，主键值相同的两个有名字的个体就是同一个个体。OntoPoc 会拒绝重复的主键。检查数据用 `shapes.ttl`。
- **多对一的关系连了两个。** 函数属性有两个值，OWL 推出的是这两个值是同一个个体，而不是数据错了。
- **连到一个不认识的东西。** 有了 `rdfs:range`，读的人可以推出关系指向的东西就是另一头类型的对象。

SHACL 检查的是写在那里的东西：缺的、重复的、不在列表里的值都会报出来。运行规则时要关掉推理（pyshacl 里是 `inference='none'`）：打开 RDFS 推理并加载本体文件时，关系的值域会在检查之前把不认识的那一头变成另一头类型的对象，`sh:class` 就不再报它。有测试分别演示了这两种情况。

## 规则文件不检查什么

- 核心 SHACL 写不出“几列合起来不重复”：由几列组成的主键，这里只检查每一列都填了、只有一个值，不检查组合有没有重复。

  SHACL-SPARQL 可以用查询写出来，但它是 SHACL 里可选的部分（每个实现至少要支持 SHACL Core），所以文件只用 Core。有一个测试把这一点固定下来：两个对象的主键两列都相同，规则仍然通过。
- 数据类型；OntoPoc 留下的证据（例如关系有多少行连上、哪些键没连上）；视图留下哪些行；派生属性的值；以及任何东西是不是已确认。这些都留在 OntoPoc 里。

## 哪些没有 OWL 的写法，哪些写成了文字

- **带“是”和“不是”的视图**都可以直接按数据里的值写成 OWL 的类表达式，不需要先把代码变成概念。“状态码是 2”是 `ObjectIntersectionOf(:Order DataHasValue(:status "2"^^xsd:integer))`，“状态码不是 2”是 `ObjectIntersectionOf(:Order DataSomeValuesFrom(:status DataComplementOf(DataOneOf("2"^^xsd:integer))))`。开放世界里，没写状态码的订单两边都归不进去。导出没有这样写：视图写成它确认过的那句话，并注明这段话不是 OWL 公理。
- **“每个编号只留最新的一行”**：要在行之间排序和分组（SQL 或 SPARQL），OWL 没有这些。
- **派生属性**：一行内的公式和沿关系的统计。OWL 没有算术，也没有汇总。
- **确认关口本身**：谁确认了什么写成注释，文件里没有任何东西、读文件的任何工具也不会保证“已确认”。数据一变，OntoPoc 会让定义回到“需再看”，文件不会跟着变。

## 哪些工具读过这两个文件

- **测试里，每次都跑**（`tests/test_owl_export.py`）：rdflib 解析两个文件，pyshacl 拿规则去检查测试里现写的几个对象。好的对象通过；一列主键重复、未知的代码、缺主键、多对一关系上一张订单连了两个客户、连到不是另一头类型的东西，各自都不通过。
- **手工跑过一次，不是测试跑的：** ROBOT 1.9.10（基于 OWL API），用测试数据生成的一个样例 `ontology.ttl`。SKOS 词还没声明时，它的 OWL 2 DL 检查说样例不属于 OWL 2 DL，原因只有一个：六个 SKOS 词没有声明；HermiT 推理机读它没有报错。声明之后，在这一版生成的样例上，HermiT 读它没有报错，语言子集检查说它属于 OWL 2 DL 和 OWL 2 RL，不属于 OWL 2 EL（因为函数属性和匿名个体）和 OWL 2 QL。

那次只检查了一个样例，不是工作区能生成的每一个文件，所以不声称你下载的文件属于哪个语言子集（profile）；文件开头也是这么写的。还没有本体编辑器打开过这两个文件。

## 早期界面的导出是另一回事

早期按运行组织的界面（`legacy.html`）有自己的 Turtle 导出（`ontology.ttl`、`data.ttl`、`shapes.ttl`），见 [LEGACY_SCREEN.md](LEGACY_SCREEN.md)。它针对一次建模运行，把数据行也写进去，保留所有没被判错的东西而不只是已确认的，日期列写成 `xsd:date`。它不是团队应用的导出，这次也没有改它。

## 出处

- OWL 2 结构规范：数据类型表（§4）、OWL 2 DL 允许的数据类型（§5.2）、函数属性和反函数属性（§9.2、§9.3）、主键（§9.5）、注释：https://www.w3.org/TR/owl2-syntax/
- SHACL：`sh:class`、`sh:minCount`、`sh:maxCount`、`sh:in`（文字必须完全相同才算匹配）、`sh:targetObjectsOf`、`sh:inversePath`、不要求推理、SHACL Core 是最低要求：https://www.w3.org/TR/shacl/
- SKOS 参考：概念体系、`skos:notation`、`skos:prefLabel`，以及规范不规定概念和 OWL 类之间的形式关系：https://www.w3.org/TR/skos-reference/
- RDF Schema：`rdfs:domain` 和 `rdfs:range`：https://www.w3.org/TR/rdf-schema/
- PROV-O：`prov:wasAttributedTo`（定义域 `prov:Entity`，值域 `prov:Agent`）：https://www.w3.org/TR/prov-o/
