"""Pruebas sin red ni escritorio: QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests"""
import ast
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()   # sin tocar los ajustes reales
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, ROOT)
import simplepostit as sp  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


class ParseTests(unittest.TestCase):
    def test_title_and_items(self):
        title, items = sp.parse("# Compras\n- [ ] pan\n- [x] leche\n\n- huevos\ntexto")
        self.assertEqual(title, "Compras")
        self.assertEqual([i[0] for i in items], ["todo", "done", "gap", "bullet", "text"])
        self.assertEqual(items[0][2], 1)  # nº de línea en la nota

    def test_markdown_blocks(self):
        _t, items = sp.parse("T\n## Sub\n```\nls -la\n```\nfin", md=True)
        self.assertEqual([i[0] for i in items], ["h", "code", "text"])
        self.assertEqual(items[1][1], "ls -la")

    def test_markdown_title_is_plain(self):
        self.assertEqual(sp.parse("# Hola **mundo**", md=True)[0], "Hola mundo")

    def test_md_inline(self):
        plain, spans, links = sp.md_inline("a **b** *c* `d` [e](https://x.y) https://z.w")
        self.assertEqual(plain, "a b c d e https://z.w")
        self.assertIn((2, 3, "b"), spans)
        self.assertIn((4, 5, "i"), spans)
        self.assertIn((6, 7, "code"), spans)
        self.assertIn((8, 9, "https://x.y"), links)
        self.assertIn((10, 21, "https://z.w"), links)

    def test_nested_link_in_bold(self):
        plain, _spans, links = sp.md_inline("**ver [doc](https://d.e)**")
        self.assertEqual(plain, "ver doc")
        self.assertEqual(links, [(4, 7, "https://d.e")])

    def test_toggle_todo(self):
        note = "T\n- [ ] uno\n  * [x] dos"
        self.assertEqual(sp.toggle_todo(note, 1), "T\n- [x] uno\n  * [x] dos")
        self.assertEqual(sp.toggle_todo(note, 2), "T\n- [ ] uno\n  * [ ] dos")

    def test_utf16_offsets(self):
        self.assertEqual(sp.u16("a😀b", 2), 3)  # el emoji ocupa dos unidades UTF-16


class CardTests(unittest.TestCase):
    def test_rows_counter_private(self):
        card = sp.Card("k", "Tareas\n- [ ] a\n- [x] b\n- [ ] c", ["privado"])
        self.assertEqual((card.done, card.total), (1, 3))
        self.assertTrue(card.private)
        self.assertEqual(len([r for r in card.rows if r[0] in ("todo", "done")]), 3)
        self.assertEqual(card.body_h, sp.CARD - card.body_top - sp.PAD - 14)  # sitio para etiquetas

    def test_url_at(self):
        card = sp.Card("k", "T\n[Docs](https://docs.example)", (), md=True)
        row = card.rows[0]
        self.assertEqual(card.url_at(row, sp.PAD + 10), "https://docs.example")
        self.assertIsNone(card.url_at(row, sp.CARD - 5))

    def test_collapsed_height(self):
        card = sp.Card("k", "Título\ncuerpo")
        card.collapsed = True
        self.assertLess(card.h, sp.CARD)
        self.assertIsNone(card.row_at(card.h - 1))

    def test_draw_all_kinds(self):
        img = QImage(400, 400, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(img)
        for note, tags, md in (("A\n- [ ] x\n- [x] y\nhttps://a.b", ["t"], False),
                               ("B\n## h\n```\ncode\n```\n**b** `c`", [], True),
                               ("C\nsecreto", ["privado"], False)):
            card = sp.Card("k" + note[0], note, tags, md)
            card.x = card.y = 50
            sp.draw_card(p, card, hover=False)
            sp.draw_card(p, card, hover=True, hover_del=True)
            card.collapsed = True
            sp.draw_card(p, card)
        p.end()

    def test_hit_testing(self):
        card = sp.Card("k", "T\n- [ ] tarea")
        card.x, card.y, card.tilt = 100, 100, 0.0
        row = card.rows[0]
        y = card.y + card.body_top + row[3] + 8
        self.assertIsNotNone(sp.on_checkbox(card, card.x + sp.PAD + 6, y))
        self.assertIsNone(sp.on_checkbox(card, card.x + sp.PAD + 80, y))
        self.assertTrue(sp.on_delete(card, card.x + sp.CARD + sp.DEL_X, card.y + sp.DEL_Y))
        self.assertTrue(sp.contains(card, card.x + 5, card.y + 5))
        self.assertFalse(sp.contains(card, card.x - 5, card.y))


class LayoutTests(unittest.TestCase):
    def test_free_spot_avoids_overlap(self):
        a = sp.Card("a", "a")
        a.x, a.y = sp.MARGIN + sp.BOARD_W - sp.CARD, sp.MARGIN
        x, y = sp.free_spot([a], 0)
        overlap = (min(x, a.x) + sp.CARD > max(x, a.x)) and (min(y, a.y) + sp.CARD > max(y, a.y))
        self.assertFalse(overlap)


class SessionTests(unittest.TestCase):
    def test_token_from_leveldb(self):
        with tempfile.TemporaryDirectory() as d:
            storage = os.path.join(d, "Local Storage", "leveldb")
            os.makedirs(storage)
            with open(os.path.join(storage, "000003.log"), "wb") as f:
                f.write(b'\x00junk_stored_user\x01{"accessToken":"0123456789abcdef0123456789abcdef","username":"x"}')
            with mock.patch.object(sp, "simplenote_profiles", return_value=[d]):
                self.assertEqual(sp.simplenote_token(), "0123456789abcdef0123456789abcdef")
            with mock.patch.object(sp, "simplenote_profiles", return_value=[os.path.join(d, "no")]):
                self.assertIsNone(sp.simplenote_token())

    def test_parse_records(self):
        raw = "id1\x1fT1\x1fa,b\x1fmd\x1eid2\x1fT2"
        self.assertEqual(sp.parse_records(raw), [("id1", "T1", ["a", "b"], True), ("id2", "T2", [], False)])


class SyncTests(unittest.TestCase):
    def test_fetch_pinned_sorted(self):
        sync = sp.Sync()
        index = {"index": [
            {"id": "a", "d": {"content": "A", "systemTags": ["pinned"], "modificationDate": 1}},
            {"id": "b", "d": {"content": "B", "systemTags": ["pinned", "markdown"], "tags": ["x"],
                              "modificationDate": 5}},
            {"id": "c", "d": {"content": "C", "systemTags": []}},
            {"id": "d", "d": {"content": "D", "systemTags": ["pinned"], "deleted": True}}]}
        with mock.patch.object(sync, "call", return_value=index):
            self.assertEqual(sync.fetch("t"), [("b", "B", ["x"], True), ("a", "A", [], False)])

    def test_apply_operations(self):
        sync = sp.Sync()
        stored = {"content": "old", "systemTags": ["pinned"], "tags": [], "deleted": False}
        posted = []

        def call(_token, path, body=None):
            if body is None:
                return dict(stored)
            posted.append((path, body))
        with mock.patch.object(sync, "call", side_effect=call):
            sync.apply("t", "edit", "n1", {"content": "new"})
            sync.apply("t", "tags", "n1", {"tags": ["privado"]})
            sync.apply("t", "unpin", "n1", {})
            sync.apply("t", "trash", "n1", {})
            sync.apply("t", "create", None, {"content": "hola", "md": True})
        self.assertEqual(posted[0][1]["content"], "new")
        self.assertEqual(posted[1][1]["tags"], ["privado"])
        self.assertEqual(posted[2][1]["systemTags"], [])
        self.assertTrue(posted[3][1]["deleted"])
        self.assertEqual(posted[4][1]["systemTags"], ["pinned", "markdown"])
        self.assertTrue(posted[4][0].startswith("i/"))

    def test_failed_request_is_kept(self):
        sync = sp.Sync()
        sync.request("trash", "n1")
        with mock.patch.object(sync, "apply", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                sync.flush("t")
        self.assertEqual(len(sync.pending), 1)  # se reintenta en la próxima vuelta


class SettingsTests(unittest.TestCase):
    def test_defaults_and_private_file(self):
        s = sp.load_settings()
        self.assertEqual(s["max_notes"], 12)
        sp.save_settings(s)
        if os.name == "posix":
            self.assertEqual(os.stat(sp.SETTINGS_FILE).st_mode & 0o777, 0o600)


class TranslationTests(unittest.TestCase):
    def test_catalog_complete(self):
        with open(os.path.join(ROOT, "simplepostit.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        keys = {n.args[0].value for n in ast.walk(tree)
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr"
                and n.args and isinstance(n.args[0], ast.Constant)} | set(sp.COLOR_NAMES)
        with open(os.path.join(ROOT, "i18n", "en.json"), encoding="utf-8") as f:
            catalog = json.load(f)
        self.assertEqual(sorted(keys - set(catalog)), [])
        for k, v in catalog.items():
            self.assertEqual(k.count("{0}"), v.count("{0}"), k)


if __name__ == "__main__":
    unittest.main()
