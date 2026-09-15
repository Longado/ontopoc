"""What an upload would send to the model, shown before it is sent. Built with the same functions the modeler and the
question round use, so the preview cannot drift from what actually leaves the machine."""
from __future__ import annotations

from ontology_poc_generator.company_documents import MAX_CHUNKS
from ontology_poc_generator.ontology_questions import CATEGORY_LIMIT
from ontology_poc_generator.public_ontology import field_catalog, resolve


def model_preview(bundle: dict) -> dict:
    if bundle.get('schema') == 'company_document_bundle.v1':
        return {'kind': 'document', 'paragraphs': len(bundle['paragraphs']), 'chars': sum(len(p) for p in bundle['paragraphs']),
                'chunks_sent': min(len(bundle['chunks']), MAX_CHUNKS), 'chunks_total': len(bundle['chunks'])}
    catalog = field_catalog(bundle)
    sources = []
    for name, entry in catalog.items():
        records = bundle['sources'][name]['records']
        fields = []
        for path, examples in entry['fields'].items():
            values = {str(v) for r in records for v in resolve(r, path) if v not in (None, '')}
            # the question round lists every value of a field with few of them (see categorical_values)
            fields.append({'path': path, 'examples': examples, **({'values': sorted(values)} if 0 < len(values) <= CATEGORY_LIMIT else {})})
        sources.append({'name': name, 'record_count': entry['record_count'], 'fields': fields})
    return {'kind': 'table', 'sources': sources}
