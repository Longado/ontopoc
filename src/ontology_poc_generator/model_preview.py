"""What an upload would send to the model, shown before it is sent. Built with the same functions the modeler and the
question round use, so the preview cannot drift from what actually leaves the machine."""
from __future__ import annotations

from ontology_poc_generator.company_documents import MAX_CHUNKS
from ontology_poc_generator.public_ontology import CATEGORY_LIMIT, field_catalog, resolve


def model_preview(bundle: dict) -> dict:
    if bundle.get('schema') == 'company_document_bundle.v1':
        return {'kind': 'document', 'paragraphs': len(bundle['paragraphs']), 'chars': sum(len(p) for p in bundle['paragraphs']),
                'chunks_sent': min(len(bundle['chunks']), MAX_CHUNKS), 'chunks_total': len(bundle['chunks'])}
    sources = []
    for name, entry in field_catalog(bundle).items():
        records = bundle['sources'][name]['records']
        fields = []
        for path, examples in entry['fields'].items():
            counts = {k: v for k, v in entry['facts'][path].items() if k != 'values'}
            # the question round lists every value, whole, of a field with few of them (see categorical_values); the
            # modeler gets the category-like ones cut at 140 characters. Whichever list is sent covers the other
            raw = sorted({str(v) for r in records for v in resolve(r, path) if v not in (None, '')})
            values = raw if 0 < len(raw) <= CATEGORY_LIMIT else entry['facts'][path].get('values')
            fields.append({'path': path, 'examples': examples, **counts, **({'values': values} if values else {})})
        sources.append({'name': name, 'record_count': entry['record_count'], 'fields': fields,
                        **{k: entry[k] for k in ('unique_columns', 'unique_pairs', 'links') if k in entry}})
    return {'kind': 'table', 'sources': sources}
