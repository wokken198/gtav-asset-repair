import json
import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def project_version():
    return re.search(r'^version = "([^"]+)"', read_text("pyproject.toml"), re.M).group(1)


class VersionTest(unittest.TestCase):
    def test_gui_version_matches_pyproject(self):
        from gtatools import gui

        self.assertEqual(gui.VERSION, project_version())

    def test_plugin_version_matches_pyproject(self):
        pkg = json.loads(read_text("dsh-plugin", "package.json"))
        self.assertEqual(pkg["version"], project_version())


class GuiImportTest(unittest.TestCase):
    def test_gui_module_imports_without_display(self):
        from gtatools import gui

        self.assertTrue(callable(gui.main))
        self.assertIn("en", gui.LANG)
        self.assertIn("zh", gui.LANG)
        for theme in ("light", "dark"):
            self.assertIn(theme, gui.THEMES)

    def test_language_tables_have_same_keys(self):
        from gtatools import gui

        self.assertEqual(set(gui.LANG["en"]), set(gui.LANG["zh"]))

    def test_theme_tables_have_same_keys(self):
        from gtatools import gui

        self.assertEqual(set(gui.THEMES["light"]), set(gui.THEMES["dark"]))

    def test_help_text_covers_every_parameter(self):
        from gtatools import gui

        wanted = {"en": ("Strength", "Blur", "Alpha"), "zh": ("强度", "模糊", "Alpha")}
        for lang, words in wanted.items():
            text = gui.LANG[lang]["help.params"]
            for word in words:
                self.assertIn(word, text, "%s help is missing %s" % (lang, word))

    def test_log_lines_are_english(self):
        from gtatools import gui

        for lang in ("en", "zh"):
            for key, value in gui.LANG[lang].items():
                if key.startswith("log."):
                    self.assertTrue(value.isascii(), "%s is not English" % key)


if __name__ == "__main__":
    unittest.main()
