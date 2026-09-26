/** Definitions use the existing graph without turning into an uploaded, verified run. */
export function libraryEntries(entries, query, category) {
  const needle = query.trim().toLocaleLowerCase();
  return entries.filter((e) => (!category || e.category === category) &&
    (!needle || [e.title, e.name, e.description, e.author, ...(e.tags || [])].join(" ").toLocaleLowerCase().includes(needle)));
}

export function definitionRun(definition) {
  const known = new Set(definition.entity_types.map((e) => e.id));
  return {
    schema: "ontology_definition.v1",
    ontology: {
      object_types: definition.entity_types.map((e) => ({ key: e.id, label: e.name, definition: e.description,
        populated_from: [], attributes: e.properties.map((p) => ({ path: p.name, definition: p })) })),
      relations: definition.relationships.filter((r) => known.has(r.from) && known.has(r.to)).map((r) => ({
        key: r.id, label: r.name, from: r.from, to: r.to, meaning: r.description, cardinality: r.cardinality,
        definition_attributes: r.attributes, source: definition.filename,
      })),
    },
    evaluation: {},
  };
}

export const DEFINITION_TYPES = { string: "文本", integer: "整数", decimal: "小数", double: "双精度小数", date: "日期", datetime: "日期时间", boolean: "布尔值", enum: "枚举" };
export const DEFINITION_CARDINALITIES = { "one-to-one": "一对一", "one-to-many": "一对多", "many-to-one": "多对一", "many-to-many": "多对多" };
