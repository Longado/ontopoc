# OntoPoc and the W3C standards: OWL, SHACL, SKOS

[中文](STANDARDS.md)

OntoPoc's team app keeps its own model of a team's definitions: object types with a key, properties, what the codes in a code column mean, relations, views and derived properties, each checked by code against the data and confirmed by a named person on a given data version. That model is not OWL, and OntoPoc does not run an OWL reasoner. What it can do is hand the confirmed definitions to tools that read the standards, as two files. This page says what is in them, what each part means in OWL and SHACL terms, and what does not fit.

## The download

- **Where.** `GET /api/workspace/agent/schema` gives a zip with `ontology.ttl` and `shapes.ttl`. `?file=ontology` or `?file=shapes` gives one of them as Turtle. The AI tool access page has a link beside the CSV of confirmed definitions.
- **Who.** Anyone signed in, viewers included, and a token, read-only or not, acting as its person: the same as the CSV at `GET /api/workspace/agent/standing?format=csv`.
- **What is in it.** The confirmed definitions that person may see, the same set and the same words as the CSV and the MCP tool `describe_definitions`. A definition that is waiting for confirmation, or that the person may not see, is not in it, and nothing in the file shows that it exists: the file is byte for byte the file of a workspace without it. A column hidden from the person is not in it.
- **Values kept from models.** For a code column a builder marked "don't send values" (on the object type page; `POST /api/workspace/types/privacy`), the meanings are left out, as the CSV leaves them blank; the confirmation itself (who, when, on which data) stays, as in the CSV. A derived property that reads such a column is listed without what it says.
- **No edit keeps a definition confirmed.** Any change to a confirmed definition (a new description of a type, a new name of a relation, a new other name) sends it back until a second person who did not make the change confirms it, so the file and the CSV never carry words nobody else confirmed. A pipeline's description is the one exception; pipelines are not in the file.
- **Names of people.** Who confirmed each definition is written as the CSV shows it to the same person. The file does not name the person who downloaded it.
- **No data.** No row of data, no object, no count of the data. It is a schema only.
- **A snapshot.** The file says when it was made. Whether each definition is still confirmed is read live at `GET /api/workspace/agent/standing`.

## What each kind of definition becomes

"Axiom" below means a statement with a logical meaning in OWL. "Annotation" means a statement OWL treats as not being there for reasoning: the OWL 2 specification says annotations "have no effect on the logical aspects of an ontology". Text in an annotation is for people.

| Definition in OntoPoc | In `ontology.ttl` | What kind of statement | In `shapes.ttl` |
|---|---|---|---|
| Object type | `owl:Class`, with `rdfs:label` (its name) and `rdfs:comment` (its description) | Axiom (a declared class) | A node shape with `sh:targetClass` |
| Key | `owl:hasKey ( … )` over the key columns' properties | Axiom, with a different meaning (see below) | Each key column: `sh:minCount 1 ; sh:maxCount 1`. A key of one column: also no value held by two objects (`sh:targetObjectsOf` the key property, `sh:inversePath`, `sh:maxCount 1`). A key of several columns: the combination is not checked (see below) |
| Property (a column) | `owl:DatatypeProperty` and `owl:FunctionalProperty`, `rdfs:domain` the type, `rdfs:range` an XSD datatype (table below), `rdfs:label` its name, `op:column` the column | Axioms; the column name is an annotation | — |
| Code meanings | One `skos:ConceptScheme` per code column, with one `skos:Concept` per code that has a meaning (`skos:notation` the code, `skos:prefLabel` the meaning). The property points to its scheme with `op:codeList`. The values stay plain values; a code is not turned into a concept in the data | Assertions about the scheme and its concepts (`skos:prefLabel` is an annotation); no axiom about the property's values | `sh:in ( … )`: the codes that have a meaning |
| Relation | `owl:ObjectProperty`, `rdfs:domain` and `rdfs:range` the two types. Many to one: `owl:FunctionalProperty`. One to many: `owl:InverseFunctionalProperty`. One to one: both. The pair of columns that connects rows is in `op:definitionText` | Axioms; the column pair is an annotation | On the "from" type: `sh:class` the other type, and `sh:maxCount 1` for many to one and one to one. On the "to" type, for one to many and one to one: `sh:inversePath` the relation, `sh:maxCount 1` |
| View (which rows count) | `owl:Class`, `rdfs:subClassOf` its type, with `op:definitionText` (the sentence OntoPoc confirms) and a note that the text is not an OWL axiom | Being a subclass is an axiom; which rows belong is text only | — |
| Derived property | `owl:DatatypeProperty`, `rdfs:domain` its type, `rdfs:range` its output type, with `op:definitionText` (its formula or statistic in words) and the same note | The property is declared; its formula is text only | — |
| Who confirmed it, when, on which data | `op:definitionId` (the id in the CSV), `op:confirmedBy`, `op:confirmedAt` (`xsd:dateTime`), `op:confirmedOnData` (for example `订单 v1`) | Annotations | — |

The `op:` terms are OntoPoc's own annotation properties, declared at the top of the file under `urn:ontopoc:vocab:`. The SKOS terms the file uses are declared there too, with the kinds the SKOS Reference gives them: `skos:Concept` and `skos:ConceptScheme` as classes, `skos:inScheme` and `skos:hasTopConcept` as object properties, `skos:notation` as a datatype property, and `skos:prefLabel` as an annotation property. A definition's other names (an object type, a property, a code meaning, a view, a derived property) are written as `skos:altLabel`, which SKOS also makes an annotation property; it is declared only in a file that has one, so a file without other names is as before. PROV-O has terms for who did what and when, but they are object and datatype properties for things such as `prov:Entity` (its examples attach them to individuals); written on a class they would say the class itself is such a thing. Plain annotation properties say only what is meant and stay out of the logic.

### Datatypes

OWL 2 has a fixed list of datatypes (the "datatype map"), and an OWL 2 DL ontology may not use other XSD datatypes. `xsd:date` and `xsd:gYearMonth` are not in that list. So:

| OntoPoc type | Range in the file | Note in the file |
|---|---|---|
| integer | `xsd:integer` | — |
| decimal | `xsd:decimal` | — |
| text | `xsd:string` | — |
| yes/no | `xsd:boolean` | The data may write it as 是/否 or Y/N; as `xsd:boolean` it is true or false |
| date and time | `xsd:dateTime` | The data may use a space and leave out seconds; as `xsd:dateTime` it is `YYYY-MM-DDThh:mm:ss` |
| date | `xsd:dateTime` | Write a day as that day at 00:00:00, for example `2024-01-05T00:00:00` |
| month | `xsd:string` | Written `YYYY-MM`, for example `2024-01` |

The shapes file does not check datatypes.

### Names (IRIs)

Every name starts with a base: the value of the environment variable `ONTOPOC_IRI_BASE` when the person running the service sets it, otherwise `urn:ontopoc:`. A base is written `https://host/path/` (ending in `/`) or `urn:name:`, with letters, digits and `. _ ~ -` only; any other value makes the download answer 409 with the reason, rather than quietly use the default. After the base come fixed words and names the product already restricts to English letters, digits and `_`:

- `type/<English name>` for a type, `relation/<English name>` for a relation, `type/<type>/derived/<English name>` for a derived property;
- `type/<type>/column/<hash>` for a property and `…/codes` for its concept scheme, `view/<hash>` for a view, where `<hash>` is the first 16 hexadecimal digits of the SHA-256 of the column name or the view name;
- `shape/type/<type>` and `shape/type/<type>/key` in the shapes file; `ontology` for the file itself.

What people typed (names, column names, descriptions) and the codes are only ever written as escaped text, never as part of a name. A concept for a code has no name of its own (a blank node); `skos:notation` is what identifies it within its scheme, as SKOS defines it. Changing the base renames everything. `urn:ontopoc:` is not a registered namespace: the names do not open in a browser, and the default is the same in every workspace, so set a base under a web address your team controls before putting files from two workspaces together.

## Why OntoPoc checks with rules and does not run a reasoner

OWL reads a file under an open world: what is not stated is unknown, not false. Where OntoPoc refuses, OWL tends to infer:

- **A repeated key.** OWL 2 says a key means each named instance "is uniquely identified by" those values, and that two named individuals with the same key values are the same individual. OntoPoc refuses a key that repeats. Validate data with `shapes.ttl`.
- **Many to one with two ends.** A functional property with two values makes OWL conclude the two values are one individual, not that the data is wrong.
- **A link to something unknown.** `rdfs:range` lets a reader conclude that whatever a relation points to is an object of the other type.

SHACL checks what is there: a value that is missing, repeated or not on the list is reported. Run the shapes with inference off (in pyshacl, `inference='none'`): with RDFS inference on and the ontology file loaded, the range of a relation makes the unknown end an object of the other type before the check, and `sh:class` no longer reports it. A test shows both.

## What the shapes do not check

- Core SHACL cannot say "no two objects share these values together": for a key of several columns, these shapes check only that each column is filled with one value, not that the combination is unique.

  SHACL-SPARQL could say it with a query, but it is an optional part of SHACL (every implementation must support at least SHACL Core), so the file keeps to Core. A test pins this: two objects with the same pair of key values pass the shapes.
- Datatypes, the evidence OntoPoc keeps (such as how many rows of a relation connect and which keys miss), the rows a view keeps, the values of derived properties, and whether anything is confirmed. These stay in OntoPoc.

## What has no OWL form, and what is written as text

- **Views with "is" and "is not"** can be written as OWL class expressions over the values as they are, without turning codes into concepts. "Status is 2" is `ObjectIntersectionOf(:Order DataHasValue(:status "2"^^xsd:integer))`, and "status is not 2" is `ObjectIntersectionOf(:Order DataSomeValuesFrom(:status DataComplementOf(DataOneOf("2"^^xsd:integer))))`. Under an open world, an order whose status is not stated is classified as neither. The export does not write these: a view is written as its confirmed sentence, with a note that the text is not an OWL axiom.
- **"Keep only the latest row per key"**: needs ordering and grouping across rows (SQL or SPARQL), which OWL does not have.
- **Derived properties**: formulas and statistics through relations. OWL has no arithmetic or aggregates.
- **The confirmation gate**: who confirmed what is written as annotations, and nothing in the file, or in any reader of it, enforces "confirmed". When data changes, OntoPoc sends a definition back for another look; the file does not change with it.

## Which tools have read the files

- **In the test suite** (`tests/test_owl_export.py`), every run: rdflib parses both files, and pyshacl runs the shapes over a few objects written inside the tests. Good objects pass, and a repeated one-column key, an unknown code, a missing key, an order with two customers on a many-to-one relation, and a link to something that is not of the other type each fail.
- **Once, by hand, not by the test suite:** ROBOT 1.9.10 (on the OWL API) on a sample `ontology.ttl` made from the tests' data. Before the SKOS terms were declared, its OWL 2 DL check put the sample outside OWL 2 DL for one reason, six undeclared SKOS terms, and the HermiT reasoner read it without error. With the declarations, on a sample from this version, HermiT read it without error and the profile check put it in OWL 2 DL and OWL 2 RL, and not in OWL 2 EL (functional properties, anonymous individuals) or OWL 2 QL.

That run covered one sample, not every file a workspace can produce, so no profile is claimed for a file you download; the file's header says the same. No ontology editor has opened the files.

## The earlier screen's export is something else

The earlier run-based screen (`legacy.html`) has its own Turtle export (`ontology.ttl`, `data.ttl`, `shapes.ttl`), described in [LEGACY_SCREEN.en.md](LEGACY_SCREEN.en.md). It works on one modelling run, includes the rows as data, keeps everything not judged wrong rather than only what was confirmed, and writes a date column as `xsd:date`. It is not the team app's export and is not changed by it.

## Sources

- OWL 2 Structural Specification: datatype map (§4), datatypes allowed in OWL 2 DL (§5.2), functional and inverse-functional properties (§9.2, §9.3), keys (§9.5), annotations: https://www.w3.org/TR/owl2-syntax/
- SHACL: `sh:class`, `sh:minCount`, `sh:maxCount`, `sh:in` (literals match exactly), `sh:targetObjectsOf`, `sh:inversePath`, entailment not required, SHACL Core as the minimum: https://www.w3.org/TR/shacl/
- SKOS Reference: concept schemes, `skos:notation`, `skos:prefLabel`, and no stated formal relation between concepts and OWL classes: https://www.w3.org/TR/skos-reference/
- RDF Schema: `rdfs:domain` and `rdfs:range`: https://www.w3.org/TR/rdf-schema/
- PROV-O: `prov:wasAttributedTo` (domain `prov:Entity`, range `prov:Agent`): https://www.w3.org/TR/prov-o/
