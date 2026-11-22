"""Other names of a definition: an object type, a property, a code meaning, a view or a derived property may carry up to MAX_COUNT other names (for example in
another language), each at most MAX_LENGTH characters. They are part of the definition's content, kept in its content as 'other_names' (a property's on the
property, a meaning's on each of its values); a definition with none has no such key, so a workspace made before they existed reads as one with none.

A question that says an other name is read as if it said the name, wherever code reads names in a question (workspace_questions._blockers and _waiting_lines,
answer_checks.definition_check, ontology_questions.flag_unasked_filters), and the model is told the other names of the definitions it is told about. That is
all: nothing here chooses rows. HEARD switches both off; then questions are read and the model is told exactly as before other names existed.

No clash: within a scope (types across the workspace; the properties of a type; the meanings of a column; the views and derived properties of a type) an other
name may not equal, ignoring case and width, a name or other name of another definition, nor its own name. A name with anything but ASCII in it is found in a
question as a substring (workspace_questions._named), so there one may not contain the other either. Across scopes, types against views and derived
properties: equal is refused, and so is a view's or derived property's name inside a type's, since a question that says the type would be heard as naming the
view; a type's name inside a view's is allowed (订单 inside 有效订单: a question about valid orders is about orders). Across kinds (check_across), an other name
may not equal a name of a definition of another kind, nor of a meaning of another column. No invisible character is kept.

In a question the longest name wins its place (workspace_questions._muted): a name found only inside a longer name of another definition, one of the two an
other name, is not heard there; 客户 inside the property's 客户号 does not name the type 客户. With no other names, names are heard as they always were."""
from __future__ import annotations

import json
import unicodedata

from ontology_poc_generator.lang import tr

HEARD = True   # whether questions are read for other names and the model is told them; off, both are as before other names existed
MAX_COUNT, MAX_LENGTH = 5, 40


def _refused(message: str, status: int):
    from ontology_poc_generator.object_types import TypeRefused   # object_types reads this module
    return TypeRefused(message, status)


def fold(text: str) -> str:
    """A name as it is compared: ignoring case and full or half width."""
    return unicodedata.normalize('NFKC', text).casefold()


def clean(raw, what: str) -> list[str] | None:
    """The other names a person wrote, trimmed, or None when none were given (an edit keeps the ones on file). TypeRefused (400) for more than MAX_COUNT, one longer
    than MAX_LENGTH or on two lines, or the same one twice."""
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(n, str) for n in raw):
        raise _refused(tr(f'{what}的另称要写成文字的列表', f'The other names of {what} must be a list of text'), 400)
    names = [n.strip() for n in raw if n.strip()]
    if len(names) > MAX_COUNT:
        raise _refused(tr(f'{what}最多有 {MAX_COUNT} 个另称', f'{what} can have at most {MAX_COUNT} other names'), 400)
    seen = set()
    for n in names:
        if len(n) > MAX_LENGTH or '\n' in n or '\r' in n:
            raise _refused(tr(f'另称“{n}”要写 1 到 {MAX_LENGTH} 个字，不能换行', f'The other name "{n}" must be 1 to {MAX_LENGTH} characters, on one line'), 400)
        if any(unicodedata.category(c).startswith('C') for c in n):   # a zero-width or direction mark: a name nobody can type back
            raise _refused(tr(f'另称“{n}”里有看不见的字符，请重新输入', f'The other name "{n}" holds an invisible character. Type it again'), 400)
        if fold(n) in seen:
            raise _refused(tr(f'另称“{n}”写了两次', f'The other name "{n}" is written twice'), 400)
        seen.add(fold(n))
    return names


def of(content: dict | None) -> list[str]:
    """The other names a definition carries (a property's or a meaning's value: the dict itself), whether or not they are heard."""
    return list((content or {}).get('other_names') or [])


def heard(content: dict | None) -> list[str]:
    """The other names a question is read for and the model is told: none while HEARD is off."""
    return of(content) if HEARD else []


def put(content: dict, names: list[str] | None) -> dict:
    """The content with these other names: the key only when there are some."""
    out = {k: v for k, v in content.items() if k != 'other_names'}
    return {**out, 'other_names': names} if names else out


def meaning_names(values: list[dict]) -> dict[str, list[str]]:
    """{label: its other names} of a code column's meanings, from its values (a label several codes share has the other names of all of them)."""
    out: dict[str, list[str]] = {}
    for e in values:
        if e.get('label') and e.get('other_names'):
            out[e['label']] = list(dict.fromkeys([*out.get(e['label'], []), *e['other_names']]))
    return out


def _substring(text: str) -> bool:
    return not text.isascii()


def _same(a: str, b: str) -> bool:
    return fold(a) == fold(b)


def _inside(a: str, b: str) -> bool:
    """a is found inside b in a question: one of them is matched as a substring and b holds a."""
    return (_substring(a) or _substring(b)) and fold(a) in fold(b) and not _same(a, b)


def _why_same():
    return tr('一样（不分大小写和全角半角）', 'they are the same, ignoring case and width')


def _why_inside():
    return tr('一个包含另一个（中文的名字在问题里按字面找，长的里面也会找到短的）', 'one contains the other (a name in Chinese is found inside longer words in a question)')


def refuse_clash(mine: list[tuple[str, bool]], theirs: list[tuple[str, bool, str]]) -> None:
    """Within one scope. `mine`: (name, is an other name) of the definition being saved; `theirs`: (name, is an other name, whose it is, in words) of the others in
    its scope. TypeRefused (409) for the first pair, one of them an other name, that is the same or (in Chinese) one inside the other; and for an other name that
    is already one of its own names."""
    own = [n for n, other in mine if not other]
    for name, other in mine:
        if other and any(_same(name, n) for n in own):
            raise _refused(tr(f'另称“{name}”已经是它自己的名字', f'The other name "{name}" is already its own name'), 409)
    for name, other in mine:
        for their, their_other, whose in theirs:
            if not (other or their_other):
                continue
            if _same(name, their) or _inside(name, their) or _inside(their, name):
                why = _why_same() if _same(name, their) else _why_inside()
                raise _refused(tr(f'“{name}”和{whose}的名字“{their}”撞了：{why}', f'"{name}" clashes with "{their}", a name of {whose}: {why}'), 409)


def refuse_across(type_names: list[tuple[str, bool, str]], view_names: list[tuple[str, bool, str]]) -> None:
    """Across scopes, types against views and derived properties, each (name, is an other name, whose it is): TypeRefused (409) for a pair, one of them an other
    name, that is the same or where the view's name is inside the type's. A type's name inside a view's is allowed."""
    for t, t_other, t_whose in type_names:
        for v, v_other, v_whose in view_names:
            if not (t_other or v_other):
                continue
            if _same(t, v):
                raise _refused(tr(f'{v_whose}的名字“{v}”和{t_whose}的名字“{t}”撞了：{_why_same()}', f'"{v}", a name of {v_whose}, clashes with "{t}", a name of {t_whose}: {_why_same()}'), 409)
            if _inside(v, t):
                raise _refused(tr(f'{v_whose}的名字“{v}”在{t_whose}的名字“{t}”里面：问到这个对象类型的问题会被当成在问{v_whose}',
                                  f'"{v}", a name of {v_whose}, is inside "{t}", a name of {t_whose}: a question about that object type would be heard as naming {v_whose}'), 409)


def whose(kind: str, name: str) -> str:
    """The words a refusal names a definition by: 对象类型“客户” / the object type "Customer"."""
    return {'type': tr(f'对象类型“{name}”', f'the object type "{name}"'), 'property': tr(f'属性“{name}”', f'the property "{name}"'),
            'meaning': tr(f'含义“{name}”', f'the meaning "{name}"'), 'view': tr(f'视图“{name}”', f'the view "{name}"'),
            'derived': tr(f'派生属性“{name}”', f'the derived property "{name}"')}[kind]


def type_names(content: dict) -> list[tuple[str, bool]]:
    return [(content['name'], False), (content['english_name'], False), *((n, True) for n in of(content))]


def view_names(content: dict) -> list[tuple[str, bool]]:
    """A view's or a derived property's names: its name (and a derived property's English name) and its other names."""
    return [(content['name'], False), *([(content['english_name'], False)] if content.get('english_name') else []), *((n, True) for n in of(content))]


def types_and_views(conn) -> tuple[list[tuple[str, bool, str, str]], list[tuple[str, bool, str, str, str]]]:
    """([(name, is an other name, whose, element id)] of every type; [(name, is an other name, whose, its type, element id)] of every view and derived property)."""
    types, views = [], []
    for element_id, content_json in conn.execute("SELECT element_id, content_json FROM element_state WHERE element_id LIKE 'objtype:%' OR element_id LIKE 'objview:%' "
                                                 "OR element_id LIKE 'derived:%'"):
        if not content_json:
            continue
        c = json.loads(content_json)
        if element_id.startswith('objtype:'):
            types += [(n, other, whose('type', c['name']), element_id) for n, other in type_names(c)]
        else:
            kind = 'view' if element_id.startswith('objview:') else 'derived'
            views += [(n, other, whose(kind, c['name']), c['type'], element_id) for n, other in view_names(c)]
    return types, views


def check_type(conn, content: dict) -> None:
    """A type's names and other names against the other types' and, across scopes, against every view's and derived property's (refuse_clash, refuse_across)."""
    types, views = types_and_views(conn)
    mine = type_names(content)
    me = f'objtype:{content["english_name"]}'
    refuse_clash(mine, [(n, o, w) for n, o, w, e in types if e != me])
    refuse_across([(n, o, whose('type', content['name'])) for n, o in mine], [(n, o, w) for n, o, w, _, _ in views])
    check_across(conn, entries_of(me, content), {me})


def check_view(conn, content: dict, element_id: str, kind: str) -> None:
    """A view's or derived property's names and other names against the other views and derived properties of its type and, across scopes, every type's."""
    types, views = types_and_views(conn)
    mine = view_names(content)
    refuse_clash(mine, [(n, o, w) for n, o, w, t, e in views if t == content['type'] and e != element_id])
    refuse_across([(n, o, w) for n, o, w, _ in types], [(n, o, whose(kind, content['name'])) for n, o in mine])
    check_across(conn, entries_of(element_id, content), {element_id})


def check_properties(properties: list[dict]) -> None:
    """Within one type: each property's other names against its own column and name and the other properties' columns, names and other names."""
    named = lambda p: [(p['column'], False), (p['name'], False), *((n, True) for n in of(p))]
    for p in properties:
        refuse_clash(named(p), [(n, o, whose('property', q['name'])) for q in properties if q is not p for n, o in named(q)])


def check_meanings(values: list[dict]) -> None:
    """Within one code column: each meaning's other names against its own label and the other meanings' labels and other names."""
    labels = list(dict.fromkeys(e['label'] for e in values if e.get('label')))
    others = meaning_names(values)
    named = lambda label: [(label, False), *((n, True) for n in others.get(label, []))]
    for label in labels:
        refuse_clash(named(label), [(n, o, whose('meaning', x)) for x in labels if x != label for n, o in named(x)])


# --- one name for one thing across kinds -------------------------------------------------------------------------------------------------------------------

def _entries(conn) -> list[dict]:
    """Every name and other name in the workspace: {'element', 'kind', 'key' (the definition it names), 'text', 'other', 'whose', 'column' (a meaning's
    (type, column))}."""
    out = []
    for element_id, content_json in conn.execute("SELECT element_id, content_json FROM element_state WHERE element_id LIKE 'objtype:%' OR element_id LIKE 'objview:%' "
                                                 "OR element_id LIKE 'derived:%' OR element_id LIKE 'enum:%'"):
        if content_json:
            out += entries_of(element_id, json.loads(content_json))
    return out


def entries_of(element_id: str, c: dict) -> list[dict]:
    """The names an element carries, as _entries lists them."""
    e = lambda kind, key, text, other, who, column=None: {'element': element_id, 'kind': kind, 'key': key, 'text': text, 'other': other, 'whose': who, 'column': column}
    if element_id.startswith('objtype:'):
        out = [e('type', ('type', c['english_name']), n, o, whose('type', c['name'])) for n, o in type_names(c)]
        for p in c['properties']:
            out += [e('property', ('property', c['english_name'], p['column']), n, o, whose('property', p['name'])) for n, o in [(p['column'], False), (p['name'], False), *((x, True) for x in of(p))]]
        return out
    if element_id.startswith('enum:'):
        column = (c['type'], c['column'])
        found = meaning_names(c['values'])
        return [e('meaning', ('meaning', *column, label), n, o, whose('meaning', label), column)
                for label in dict.fromkeys(v['label'] for v in c['values'] if v.get('label')) for n, o in [(label, False), *((x, True) for x in found.get(label, []))]]
    kind = 'view' if element_id.startswith('objview:') else 'derived'
    return [e(kind, (kind, element_id), n, o, whose(kind, c['name'])) for n, o in view_names(c)]


def check_across(conn, new: list[dict], replaced: set[str]) -> None:
    """One name for one thing: an other name may not equal (ignoring case and width) a name or other name of a definition of another kind (a type, a property, a
    meaning, a view, a derived property), nor of a meaning of another column. `new`: the entries being saved; `replaced`: the elements they replace. The scopes
    have their own rules (refuse_clash, refuse_across); a property may share an other name with another type's property (both say the same column's thing)."""
    if not any(n['other'] for n in new) and not any(x['other'] for x in _entries(conn)):
        return
    others = [x for x in _entries(conn) if x['element'] not in replaced]
    for a in new:
        for b in [*others, *new]:
            if a['key'] == b['key'] or not (a['other'] or b['other']) or not _same(a['text'], b['text']):
                continue
            if a['kind'] == b['kind'] and (a['kind'] != 'meaning' or a['column'] == b['column']):
                continue   # within one kind the scopes decide
            raise _refused(tr(f'“{a["text"]}”已经是{b["whose"]}的名字：问题里一个名字只能指一样东西', f'"{a["text"]}" is already a name of {b["whose"]}: a name in a question can only mean one thing'), 409)
