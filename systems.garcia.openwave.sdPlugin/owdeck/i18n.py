"""The words on the keys and in the inspectors, in OpenDeck's language.

One file per language in lang/, named by its code (en.json, fr.json). Each
is laid out the way OpenDeck expects a plugin's <code>.json: the plugin's and
the actions' Name and Tooltip at the top level, which OpenDeck shows in its
action list, and every other string under "Localization", which is what this
module serves. The packaging copies the files next to manifest.json, the only
place OpenDeck looks for them.

English is the reference: a key missing from another language falls back to
it, and a key missing from English shows as itself, so a forgotten string is
visible rather than blank.
"""

import json
import os
import re

LANG_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "lang")
DEFAULT = "en"
# The only thing a translation may ask to have filled in: a bare {word}.
# Deliberately not str.format, which would let a language file reach into
# the values it is handed ({name.__class__}, {0[0]}) or break a key with a
# stray brace.
PLACEHOLDER = re.compile(r"\{(\w+)\}")

_reference = {}
_strings = {}
_language = DEFAULT
# Set by the first load, so a bundle with no readable en.json is not re-read
# from disk for every string drawn.
_loaded = False


def _load(code):
    try:
        with open(os.path.join(LANG_DIR, f"{code}.json"),
                  encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    strings = data.get("Localization") if isinstance(data, dict) else None
    if not isinstance(strings, dict):
        return None
    return {key: value for key, value in strings.items()
            if isinstance(value, str)}


def available():
    try:
        names = os.listdir(LANG_DIR)
    except OSError:
        return [DEFAULT]
    return sorted(name[:-5] for name in names if name.endswith(".json"))


def resolve(code):
    """The language file to use for a code OpenDeck or the system gave.

    "fr", "fr_FR", "fr-FR" and "fr_FR.UTF-8" all mean French; a region with
    no file of its own uses the base language, and anything unknown English.
    Only ever returns a name that is in lang/, so the code -- which arrives
    from outside -- never becomes part of a path on its own.
    """
    code = str(code or "").split(".")[0].replace("-", "_")
    known = available()
    for candidate in (code, code.split("_")[0].lower()):
        if candidate in known:
            return candidate
    return DEFAULT


def set_language(code):
    """Load the strings for `code`. Returns the language actually in use.

    Module state, like the theme: drawing happens only on the plugin's
    event-loop thread, and the language is set once, before the first key.
    """
    global _reference, _strings, _language, _loaded
    _loaded = True
    _reference = _load(DEFAULT) or {}
    _language = resolve(code)
    _strings = (_load(_language) or {}) if _language != DEFAULT else {}
    return _language


def language():
    return _language


def fill(text, values):
    """`text` with each {name} that `values` has replaced, in one pass.

    One pass, so a value that itself contains braces -- a device called
    "{mix}" -- is not expanded a second time. A placeholder with no value is
    left as written rather than raising: a key showing "{count} mics" is a
    bug to fix, a plugin that stopped drawing is a dead deck.
    """
    if not values:
        return text
    return PLACEHOLDER.sub(
        lambda match: (str(values[match.group(1)])
                       if match.group(1) in values else match.group(0)),
        text)


def t(key, default=None, **values):
    """The string for `key`, with {placeholders} filled from `values`.

    `default` is used when no language has the key; without one the key
    itself is shown.
    """
    if not _loaded:
        set_language(_language)
    text = _strings.get(key) or _reference.get(key) or default or key
    return fill(text, values)


def table(prefix=""):
    """Every string whose key starts with `prefix`, for the inspectors."""
    if not _loaded:
        set_language(_language)
    merged = dict(_reference)
    merged.update((key, value) for key, value in _strings.items() if value)
    return {key: value for key, value in merged.items()
            if key.startswith(prefix)}
