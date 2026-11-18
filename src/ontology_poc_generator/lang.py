"""The language of the person asking, for the sentences the service writes (refusals, generated phrases, card text).

Each request sets it from its Accept-Language header; code that writes a sentence says both versions:

    raise TypeRefused(tr(f'英文名“{x}”已经有了', f'The English name "{x}" is already taken'), 409)

With no header (the tests, scripts, the MCP tools) the language stays Chinese, so existing callers see what they saw before.
"""
import contextlib
import contextvars

_LANG = contextvars.ContextVar('ontopoc_lang', default='zh')


def from_header(value):
    """'en' when the first language the page asks for is English, else 'zh'."""
    first = (value or '').split(',')[0].strip().lower()
    return 'en' if first.startswith('en') else 'zh'


def use(lang):
    """Set the language for this request (a thread of the server); returns the token to reset it."""
    return _LANG.set('en' if lang == 'en' else 'zh')


def current():
    return _LANG.get()


def english():
    return _LANG.get() == 'en'


def tr(zh, en):
    """The sentence in the asker's language."""
    return en if _LANG.get() == 'en' else zh


class TrMap(dict):
    """A dictionary of display words kept as (Chinese, English) pairs: reading a key gives the word in the asker's language."""

    def __getitem__(self, key):
        return tr(*super().__getitem__(key))

    def get(self, key, default=None):
        return tr(*super().get(key)) if key in self else default

    def items(self):
        return [(key, self[key]) for key in self]

    def values(self):
        return [self[key] for key in self]


@contextlib.contextmanager
def speaking(code):
    """Write or compare text in one language for a moment (for example to find a stored sentence written in either language)."""
    token = use(code)
    try:
        yield
    finally:
        _LANG.reset(token)
