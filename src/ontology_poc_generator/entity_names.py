"""Exact matching on a single name or on a column of explicitly listed aliases."""
import re
import unicodedata

_APOSTROPHES = str.maketrans('', '', "'’‘ʼ")


def name_key(value: str) -> str:
    text = unicodedata.normalize('NFKC', value).casefold()
    return ' '.join(text.translate(_APOSTROPHES).split())


def matches_name(value: str, wanted: str) -> bool:
    key = name_key(wanted)
    return bool(key) and (name_key(value) == key or
                          any(name_key(alias) == key for alias in re.split(r'[;；、|\n]', value)))
