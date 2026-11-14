/** The object form columns only a person was left to fill, as the page edits them. */

const EMPTY = { label: "", description: "", display_field: null, drafted: false, fields: {} };

export function formOf(run, type) {
  const f = run.evaluation?.form?.types?.[type];
  return f ? { ...EMPTY, ...f, label: f.label || "", description: f.description || "", fields: { ...f.fields } } : { ...EMPTY, fields: {} };
}

/** One edit: to the object (path null) or one field; whatever a person touches is no longer the model's draft. */
export function editForm(form, path, key, value) {
  if (path === null) return { ...form, [key]: value, drafted: false };
  const field = { label: "", description: "", ...form.fields[path], [key]: value, drafted: false };
  return { ...form, fields: { ...form.fields, [path]: field } };
}
