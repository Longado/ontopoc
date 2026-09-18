"""The ontology as DIP's object form wants it: one CSV per object, the form's columns in the form's order
(docs/DIP_INTERFACE_REFERENCE.md section 2). Key, type and length are read from the data (handover_form); the names,
descriptions and display field are what a person wrote or kept from the 字段释义员's draft. Only the form's shape is
trusted; the batch import contract is untested, so the package says so and carries no relation table."""
from __future__ import annotations

import csv
import io


def rows_csv(columns: list[str], rows: list[list[str]]) -> str:
    """CSV with a byte-order mark, so a spreadsheet opens Chinese and leading zeros as written."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(columns)
    writer.writerows(rows)
    return '\ufeff' + out.getvalue()

COLUMNS = ['主键', '展示', '中文名称', '英文名称', '描述', '类型', '长度', '属性类型']
DIP_TYPES = {'INTEGER': 'INT', 'DECIMAL': 'DOUBLE', 'VARCHAR': 'VARCHAR', 'DATE': 'DATE', 'DATETIME': 'DATETIME'}


def dip_files(ontology: dict, handover: dict, form: dict | None) -> dict[str, str]:
    """file name -> text: a CSV per object, and 说明.txt naming each object and what to check before importing."""
    written = (form or {}).get('types', {})
    labels = {t['key']: t.get('label') or t['key'] for t in ontology['object_types']}
    files, lines, splits = {}, [], []
    for t in handover.get('types', []):
        key, own = t['type'], written.get(t['type'], {})
        rows = []
        for f in t['fields']:
            mine = own.get('fields', {}).get(f['path'], {})
            rows.append(['是' if f['identity'] else '', '是' if own.get('display_field') == f['path'] else '', mine.get('label') or '',
                         f['path'], mine.get('description') or '', DIP_TYPES.get(f.get('type'), ''), str(f['length']) if f.get('type') else '',
                         '主键' if f['identity'] else '数据导入'])
        files[f'{key}.csv'] = rows_csv(COLUMNS, rows)
        parts = [f'{key}.csv', f"业务本体中文名称：{own.get('label') or labels.get(key, key)}", f'英文名称：{key}']
        if own.get('description'):
            parts.append(f"描述：{own['description']}")
        lines.append('\t'.join(parts))
        if t.get('needs_single_key'):
            splits.append(f"{key}.csv：靠 {' + '.join(t['identity_fields'])} 一起识别。DIP 每张表只收一个主键，导入前把它们合成一个字段，或改建模。")
    files['说明.txt'] = '\n'.join([
        'OntoPoc 导出的 DIP 对象表单，每个对象一张 CSV，列与 DIP 界面配置的属性表单一致。',
        '类型、长度、主键由代码逐行读数据得到；中文名称、描述、展示字段是人写的或人留下的起草稿，空着的要在 DIP 里补。',
        '导入前请实测：DIP 批量导入的文件格式、主键规则、关系表达方式都还没和产品技术确认过；关系表因此没有导出。',
        '', *lines, *([''] + splits if splits else [])]) + '\n'
    return files
