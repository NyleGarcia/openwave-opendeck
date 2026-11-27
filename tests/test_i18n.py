"""Translations: which file a language code picks, and that nothing is missing.

The scans at the bottom are the part that earns its keep. A string asked for
by a name that is in no file draws as that name on someone's key, and nothing
else in the suite would notice: every other test runs in English, against
text that is still there.
"""

import glob
import html
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(ROOT, "systems.garcia.openwave.sdPlugin")
sys.path.insert(0, BUNDLE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from owdeck import graph, i18n, render                # noqa: E402

import plugin as P                                    # noqa: E402
import validate_plugin                                # noqa: E402
from tests.test_plugin import PluginCase              # noqa: E402

KEY = r"[a-z0-9_]+(?:\.[a-z0-9_]+)+"
# Keys whose last part is chosen at run time, as f"key.fx.{effect}".
BUILT = ("theme.", "key.fx.", "key.output.")


def language_file(code):
    with open(os.path.join(BUNDLE, "lang", f"{code}.json"),
              encoding="utf-8") as handle:
        return json.load(handle)


def english():
    return language_file("en")["Localization"]


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def python_sources():
    return [os.path.join(BUNDLE, "plugin.py")] + sorted(glob.glob(
        os.path.join(BUNDLE, "owdeck", "*.py")))


def inspector_sources():
    return sorted(glob.glob(os.path.join(BUNDLE, "pi", "*.html"))
                  + glob.glob(os.path.join(BUNDLE, "pi", "*.js")))


class EnglishAfterwards(unittest.TestCase):
    """Every other test reads English off the keys; leave it that way."""

    def tearDown(self):
        i18n.set_language("en")
        super().tearDown()


class ResolveTests(EnglishAfterwards):
    def test_every_spelling_of_french_picks_french(self):
        for code in ("fr", "fr_FR", "fr-FR", "fr_FR.UTF-8", "FR", "fr_CA"):
            self.assertEqual(i18n.resolve(code), "fr", code)

    def test_an_unknown_or_missing_language_is_english(self):
        for code in ("xx", "", None, "C.UTF-8", "POSIX", 7):
            self.assertEqual(i18n.resolve(code), "en", code)

    def test_a_code_cannot_name_a_file_outside_lang(self):
        for code in ("../manifest", "../../etc/passwd", "en/../fr"):
            self.assertEqual(i18n.set_language(code), "en", code)
            self.assertEqual(i18n.t("key.muted"), "MUTED")

    def test_strings_follow_the_language(self):
        self.assertEqual(i18n.set_language("fr"), "fr")
        self.assertEqual(i18n.t("key.muted"), language_file("fr")[
            "Localization"]["key.muted"])
        self.assertNotEqual(i18n.t("key.muted"), "MUTED")
        i18n.set_language("en")
        self.assertEqual(i18n.t("key.muted"), "MUTED")

    def test_a_key_missing_from_a_language_is_shown_in_english(self):
        i18n.set_language("fr")
        saved = dict(i18n._strings)
        try:
            del i18n._strings["key.muted"]
            self.assertEqual(i18n.t("key.muted"), "MUTED")
            self.assertEqual(i18n.table("key.")["key.muted"], "MUTED")
        finally:
            i18n._strings.update(saved)

    def test_a_missing_key_shows_itself_or_its_default(self):
        self.assertEqual(i18n.t("no.such.key"), "no.such.key")
        self.assertEqual(i18n.t("no.such.key", default="x"), "x")

    def test_the_inspector_table_holds_only_inspector_strings(self):
        table = i18n.table("pi.")
        self.assertIn("pi.colours", table)
        self.assertFalse([key for key in table if not key.startswith("pi.")])

    def test_theme_names_are_translated(self):
        i18n.set_language("fr")
        labels = {choice["id"]: choice["label"]
                  for choice in render.theme_choices()}
        self.assertEqual(labels["light"], "Clair")


class PlaceholderTests(EnglishAfterwards):
    def test_placeholders_are_filled(self):
        self.assertEqual(i18n.t("key.group.mics", count=3), "3 mics")
        i18n.set_language("fr")
        self.assertEqual(i18n.t("key.group.mics", count=3), "3 micros")

    def test_a_placeholder_with_no_value_is_left_as_written(self):
        self.assertEqual(i18n.fill("{count} mics", {"other": 1}),
                         "{count} mics")

    def test_only_a_bare_name_is_a_placeholder(self):
        """Not str.format: a translation cannot reach into a value."""
        class Secret:
            hidden = "leaked"

        for text in ("{name.hidden}", "{name!r}", "{name:>10}", "{0}",
                     "{name[0]}", "{", "}", "{}", "{ name }"):
            self.assertEqual(i18n.fill(text, {"name": Secret()}), text)

    def test_a_value_with_braces_in_it_is_not_filled_again(self):
        self.assertEqual(
            i18n.fill("{name} into {mix}", {"name": "{mix}", "mix": "Chat"}),
            "{mix} into Chat")

    def test_a_device_named_like_a_placeholder_survives_the_key(self):
        svg = render.strip("Music", 50, False, context="{mix}")
        self.assertIn("into {mix}", svg)


class LanguageFromOpenDeckTests(unittest.TestCase):
    def setUp(self):
        self.saved = {name: os.environ.get(name)
                      for name in ("LC_ALL", "LANG")}

    def tearDown(self):
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_the_language_comes_from_the_info_argument(self):
        info = json.dumps({"application": {"language": "fr"}})
        self.assertEqual(P.opendeck_language(info), "fr")

    def test_bad_info_falls_back_to_the_environment(self):
        os.environ["LC_ALL"] = "fr_FR.UTF-8"
        for info in ("not json", None, "[]", '"fr"', "{}",
                     '{"application": []}',
                     '{"application": {"language": 3}}'):
            self.assertEqual(P.opendeck_language(info), "fr_FR.UTF-8", info)

    def test_lang_is_used_when_lc_all_is_unset(self):
        os.environ.pop("LC_ALL", None)
        os.environ["LANG"] = "fr_FR.UTF-8"
        self.assertEqual(P.opendeck_language(None), "fr_FR.UTF-8")


class TranslatedPluginTests(PluginCase):
    """The plugin end to end in a second language."""

    def setUp(self):
        super().setUp()
        i18n.set_language("fr")
        self.french = language_file("fr")["Localization"]

    def tearDown(self):
        i18n.set_language("en")
        super().tearDown()

    def test_a_muted_key_says_so_in_french(self):
        self.place("c", P.VOLUME, {"target": "mix:chat"})
        self.assertIn(f">{self.french['key.muted']}<",
                      self.plugin._drawn["c"])
        self.assertNotIn("MUTED", self.plugin._drawn["c"])

    def test_an_unconfigured_key_prompts_in_french(self):
        for action in (P.VOLUME, P.SOURCE_LEVEL, P.SEND_LEVEL, P.MIC_GROUP,
                       P.SCENE, P.FX_TOGGLE, P.OUTPUT_TOGGLE):
            self.place("c", action, {})
            self.assertNotIn("Pick", self.plugin._drawn["c"], action)
            self.assertNotIn(">key.", self.plugin._drawn["c"], action)

    def test_the_inspector_is_sent_its_strings_and_language(self):
        self.place("c", P.MIC_GROUP, {})
        self.plugin._handle({"event": "propertyInspectorDidAppear",
                             "context": "c", "action": P.MIC_GROUP})
        payload = self.events("sendToPropertyInspector")[-1]["payload"]
        self.assertEqual(payload["language"], "fr")
        self.assertEqual(payload["strings"]["pi.loading"],
                         self.french["pi.loading"])
        self.assertEqual(set(payload["strings"]),
                         {key for key in english() if key.startswith("pi.")})

    def test_a_request_from_the_inspector_is_answered_the_same_way(self):
        self.place("c", P.VOLUME, {})
        self.plugin._handle({"event": "sendToPlugin", "context": "c",
                             "payload": {"request": "targets",
                                         "action": P.VOLUME}})
        payload = self.events("sendToPropertyInspector")[-1]["payload"]
        self.assertIn("strings", payload)
        self.assertEqual(payload["hint"], self.french["pi.level.hint.mix"])
        self.assertEqual(payload["targets"][0]["group"],
                         self.french["pi.level.group.mixes"])

    def test_an_unplugged_device_keeps_a_bare_name_for_saving(self):
        """The panel saves a device's name; "(débranché)" is not part of it."""
        self._patch(graph, "output_devices", lambda: [])
        self._patch(P.ipc, "actions", lambda: ["set-output"])
        payload = self.plugin._inspector_payload(P.OUTPUT_TOGGLE, {
            "mix": "personal", "output1": "auto", "output2": "tv",
            "output_labels": {"tv": "Living Room TV"}})
        device = next(d for d in payload["devices"] if d["value"] == "tv")
        self.assertEqual(device["name"], "Living Room TV")
        self.assertEqual(device["label"], i18n.t(
            "pi.output.unplugged", name="Living Room TV"))
        self.assertNotEqual(device["label"], device["name"])


class CoverageTests(unittest.TestCase):
    """Every key the code asks for exists in English, and the reverse."""

    def _literals(self, paths, pattern):
        found = set()
        for path in paths:
            for key in re.findall(pattern, read(path)):
                found.add((os.path.basename(path), key))
        return found

    def _missing(self, found):
        known = english()
        return sorted(pair for pair in found if pair[1] not in known)

    def test_python_keys_exist(self):
        # Literal keys only; built ones are checked below.
        found = self._literals(python_sources(), r'\bt\(\s*"(' + KEY + r')"')
        self.assertTrue(found)
        self.assertEqual(self._missing(found), [])

    def test_inspector_keys_exist(self):
        paths = inspector_sources()
        marked = self._literals(paths, r'data-i18n="([^"]*)"')
        self.assertTrue(marked)
        self.assertEqual(self._missing(marked), [])
        # Any quoted pi.* name in a page, not just OpenWave.t("..."): some
        # are picked by a condition before being handed to it.
        named = self._literals(paths, r'"(pi\.[a-z0-9_.]+)"')
        self.assertTrue(named)
        self.assertEqual(self._missing(named), [])

    def test_built_keys_exist(self):
        known = english()
        for theme in render.THEMES:
            self.assertIn(f"theme.{theme}", known)
        for effect in ("lowcut", "gate", "comp", "mono"):
            self.assertIn(f"key.fx.{effect}", known)
        for choice in P.SPECIAL_OUTPUTS:
            self.assertIn(f"key.output.{choice}", known)
        for keys in P.PROMPTS.values():
            for key in keys:
                self.assertIn(key, known)
        for key in P.HINTS.values():
            self.assertIn(key, known)

    def test_no_string_is_left_unused(self):
        """A key nothing asks for is a translation someone does for nothing."""
        used = {key for _path, key in self._literals(
            python_sources() + inspector_sources(), r'"(' + KEY + r')"')}
        unused = sorted(key for key in english()
                        if key not in used and not key.startswith(BUILT))
        self.assertEqual(unused, [])

    def test_the_english_in_a_page_is_the_english_in_the_file(self):
        """The page's own text stands in until the strings arrive, so it
        must be the same sentence -- or the panel visibly rewords itself."""
        known = english()
        checked = 0
        for path in inspector_sources():
            for key, text in re.findall(
                    r'data-i18n="([^"]*)"[^>]*>([^<]*)<', read(path)):
                self.assertEqual(" ".join(html.unescape(text).split()),
                                 " ".join(known[key].split()),
                                 f"{os.path.basename(path)}: {key}")
                checked += 1
        self.assertGreater(checked, 20)

    def test_no_page_writes_text_as_markup(self):
        """Translated text goes in as text. innerHTML is only ever emptied."""
        for path in inspector_sources():
            for assigned in re.findall(r'innerHTML\s*\+?=\s*([^;]+);',
                                       read(path)):
                self.assertEqual(assigned.strip(), '""',
                                 os.path.basename(path))
            self.assertNotIn("insertAdjacentHTML", read(path))
            self.assertNotIn("document.write", read(path))

    def test_no_python_formats_a_translation(self):
        self.assertNotIn(".format(", read(os.path.join(
            BUNDLE, "owdeck", "i18n.py")))


class ValidatorTests(unittest.TestCase):
    """check_languages() against language files with one thing wrong."""

    def setUp(self):
        self.manifest = json.load(open(os.path.join(BUNDLE, "manifest.json")))
        self.english = language_file("en")
        self.saved = (validate_plugin.BUNDLE, validate_plugin.problems)

    def tearDown(self):
        validate_plugin.BUNDLE, validate_plugin.problems = self.saved

    def _problems(self, **files):
        with tempfile.TemporaryDirectory() as bundle:
            os.mkdir(os.path.join(bundle, "lang"))
            files.setdefault("en", self.english)
            for code, data in files.items():
                with open(os.path.join(bundle, "lang", f"{code}.json"), "w",
                          encoding="utf-8") as handle:
                    json.dump(data, handle)
            validate_plugin.BUNDLE = bundle
            validate_plugin.problems = []
            validate_plugin.check_languages(self.manifest)
            return validate_plugin.problems

    def _french(self, **changes):
        data = json.loads(json.dumps(language_file("fr")))
        for key, value in changes.items():
            if value is None:
                del data["Localization"][key]
            else:
                data["Localization"][key] = value
        return data

    def test_the_shipped_languages_pass(self):
        self.assertEqual(self._problems(fr=language_file("fr")), [])

    def test_a_missing_or_extra_key_fails(self):
        problems = self._problems(fr=self._french(**{
            "key.muted": None, "key.invented": "x"}))
        self.assertEqual(len(problems), 2, problems)

    def test_a_renamed_or_dropped_placeholder_fails(self):
        for text in ("{nombre} micros", "micros", "{count} {count} micros"):
            self.assertTrue(self._problems(
                fr=self._french(**{"key.group.mics": text})), text)

    def test_anything_but_a_bare_name_in_braces_fails(self):
        for text in ("{count.real} micros", "{count!r} micros",
                     "{count:>9} micros", "{count} micros }",
                     "{ {count} micros", "{count} mic{}s"):
            self.assertTrue(self._problems(
                fr=self._french(**{"key.group.mics": text})), text)

    def test_an_empty_or_non_string_value_fails(self):
        for value in ("", "  ", 3, ["MUET"]):
            self.assertTrue(self._problems(
                fr=self._french(**{"key.muted": value})), value)

    def test_an_action_without_a_name_fails(self):
        data = self._french()
        del data[P.SCENE]["Name"]
        self.assertTrue(self._problems(fr=data))

    def test_english_must_match_the_manifest(self):
        data = json.loads(json.dumps(self.english))
        data[P.SCENE]["Tooltip"] = "Something else."
        self.assertTrue(self._problems(en=data))

    def test_a_file_not_named_for_a_language_fails(self):
        self.assertTrue(self._problems(manifest=self.english))


if __name__ == "__main__":
    unittest.main()
