"""The Convert page is a bare tk.Frame, not a _Page subclass.

_Page packs its own frame inside __init__; ConvertPage used to rely on the same
behaviour and never called pack(), so the page rendered completely blank while
every other page worked. The report also had two retranslate methods, and the
colour-only one shadowed the one that redrew the rows, so switching language
left the old text on screen. Both contracts are pinned here, in one App: Tk
cannot be torn down and rebuilt twice inside a single test process.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))


class TestConvertPage(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "needs a Windows Tk display")
    def test_page_is_visible_and_the_report_follows_the_language(self):
        from gtav_asset_repair import gui

        app = gui.App()
        try:
            app.show_page("convert")
            app.update_idletasks()
            holder = app.pages["convert"]
            kids = holder.winfo_children()
            self.assertTrue(kids, "the convert page built no widgets")
            self.assertEqual(kids[0].winfo_manager(), "pack",
                             "ConvertPage must pack itself, otherwise it renders blank")
            self.assertGreater(kids[0].winfo_reqheight(), 50,
                               "the convert page has no visible content")

            page = kids[0]
            page._rows = [(1, 1, {"rel": "a.ytd", "action": "converted", "src": 1,
                                  "dst": 2, "note": "", "note_key": "",
                                  "problems": []})]
            page._counts = ({"converted": 1}, 0)

            app.lang = "en"
            page.retranslate()
            english = page.text.get("1.0", "end")
            app.lang = "zh"
            page.retranslate()
            chinese = page.text.get("1.0", "end")

            self.assertIn("converted,", english, english)
            self.assertNotIn("converted,", chinese, chinese)
            self.assertIn("个已重建", chinese, chinese)
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
