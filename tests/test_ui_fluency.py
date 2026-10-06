import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import ImageChops, ImageStat

from core.ui_events import UiEventQueue
from rounded_widgets import _render_full_surface, render_rounded_surface
from ui.workspace import Workspace


class Scheduler:
    def __init__(self):
        self.pending = {}
        self.counter = 0

    def after(self, delay, callback, *args):
        self.counter += 1
        self.pending[self.counter] = (callback, args)
        return self.counter

    def after_cancel(self, identifier):
        self.pending.pop(identifier, None)

    def run_all(self):
        while self.pending:
            identifier = next(iter(self.pending))
            callback, args = self.pending.pop(identifier)
            callback(*args)


class FluencyTests(unittest.TestCase):
    def test_event_drain_yields_with_backlog_and_keeps_order(self):
        queue = UiEventQueue()
        values = []
        for index in range(5):
            queue.post(values.append, index)
        with patch("core.ui_events.time.perf_counter", side_effect=[0, 0.009]):
            self.assertEqual(queue.drain(time_budget_ms=8), 1)
        self.assertFalse(queue.empty())
        self.assertEqual(queue.drain(), 4)
        self.assertEqual(values, list(range(5)))

    def test_resize_is_throttled_and_last_width_wins(self):
        workspace = object.__new__(Workspace)
        workspace.root = Scheduler()
        workspace.cover_canvas = SimpleNamespace(itemconfigure=lambda *args, **kwargs: None)
        workspace.cover_window = 1
        workspace._cover_columns = 4
        workspace.view_mode = "covers"
        workspace._cover_resize_after = None
        layouts = []
        workspace._relayout_cover_cards = layouts.append
        workspace._on_cover_resize(SimpleNamespace(width=520))
        workspace._on_cover_resize(SimpleNamespace(width=350))
        self.assertEqual(len(workspace.root.pending), 1)
        workspace.root.run_all()
        self.assertEqual(layouts, [2])

    def test_resize_returning_to_original_width_cancels_stale_layout(self):
        workspace = object.__new__(Workspace)
        workspace.root = Scheduler()
        workspace.cover_canvas = SimpleNamespace(itemconfigure=lambda *args, **kwargs: None)
        workspace.cover_window = 1
        workspace._cover_columns = 4
        workspace.view_mode = "covers"
        workspace._cover_resize_after = None
        workspace._on_cover_resize(SimpleNamespace(width=520))
        workspace._on_cover_resize(SimpleNamespace(width=690))
        self.assertEqual(workspace.root.pending, {})

    def make_table(self):
        workspace = object.__new__(Workspace)
        workspace.root = Scheduler()
        rows = {}
        workspace.tree = SimpleNamespace(get_children=lambda: list(rows),
                                        delete=lambda *keys: [rows.pop(key) for key in keys],
                                        insert=lambda *args, **kwargs: rows.update({kwargs["iid"]: kwargs["values"]}))
        workspace.item_by_iid = {}
        workspace._table_items = None
        workspace._table_after = None
        workspace._table_generation = 0
        workspace.filtered_items = [
            {"ruta": f"book_{index}", "titulo": str(index), "autor_mostrar": "Author",
             "formato": "EPUB", "tamano_mostrar": "1 MB"}
            for index in range(1000)
        ]
        return workspace, rows

    def test_table_populates_in_bounded_batches(self):
        workspace, rows = self.make_table()
        workspace._render_table()
        self.assertGreater(len(rows), 0)
        self.assertLessEqual(len(rows), 120)
        self.assertTrue(workspace.root.pending)
        workspace.root.run_all()
        self.assertEqual(len(rows), 1000)
        self.assertEqual(len(workspace.item_by_iid), 1000)

    def test_table_search_cancels_old_batches(self):
        workspace, rows = self.make_table()
        workspace._render_table()
        stale_generation = workspace._table_generation
        old_items = workspace._table_items
        workspace.filtered_items = workspace.filtered_items[-2:]
        workspace._render_table()
        workspace._append_table_batch(old_items, 120, stale_generation)
        workspace.root.run_all()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows["book-0"][0], "998")

    def test_unchanged_table_is_not_recreated(self):
        workspace, rows = self.make_table()
        workspace._render_table()
        generation = workspace._table_generation
        pending = dict(workspace.root.pending)
        workspace._render_table()
        self.assertEqual(workspace._table_generation, generation)
        self.assertEqual(workspace.root.pending, pending)

    def test_nine_slice_keeps_antialiased_edges_and_colors(self):
        colors = ("#f8f6f1", "#fffdf9", "#a9573e")
        optimized = render_rounded_surface(340, 600, 18, *colors)
        reference = _render_full_surface(340, 600, 18, *colors, 4)
        self.assertEqual(optimized.size, reference.size)
        self.assertEqual(optimized.getpixel((170, 300)), (255, 253, 249))
        self.assertLess(max(ImageStat.Stat(ImageChops.difference(optimized, reference)).mean), 0.1)

    def test_queued_obsolete_covers_are_not_loaded(self):
        workspace = object.__new__(Workspace)
        import threading
        workspace.cover_generation = 0
        workspace.cover_pending_lock = threading.Lock()
        workspace.cover_pending = set()
        workspace._cover_render_paths = ("new_book",)
        workspace.selected_item = None
        calls, jobs = [], []
        workspace.cover_executor = SimpleNamespace(submit=jobs.append)
        workspace.cover_service = SimpleNamespace(thumbnail_path=lambda *args, **kwargs: calls.append(args))
        workspace.app = SimpleNamespace(_encolar_ui=lambda *args: None)
        workspace._request_cover(None, "old_book")
        jobs[0]()
        self.assertEqual(calls, [])
        self.assertEqual(workspace.cover_pending, set())

    def test_pdf_cover_renders_only_thumbnail_pixels_and_closes_resources(self):
        from unittest.mock import Mock
        from PIL import Image
        from core.cover_service import CoverService
        bitmap = Mock()
        bitmap.to_pil.return_value = Image.new("RGB", (288, 412))
        page = Mock()
        page.get_size.return_value = (2000, 3000)
        page.render.return_value = bitmap
        class Document:
            closed = False
            def __len__(self):
                return 1
            def __getitem__(self, index):
                return page
            def close(self):
                self.closed = True
        document = Document()
        with patch.dict("sys.modules", {"pypdfium2": SimpleNamespace(PdfDocument=lambda path: document)}):
            image = CoverService._extract_pdf("fixture.pdf", (144, 206))
        self.assertIsNotNone(image)
        self.assertLessEqual(page.render.call_args.kwargs["scale"] * 3000, 412)
        bitmap.close.assert_called_once()
        page.close.assert_called_once()
        self.assertTrue(document.closed)

    def test_inspector_does_not_initialize_or_wait_on_catalog_writer(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        import library_core as core
        from core.catalog_store import CatalogStore
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "catalog.sqlite3"
            store = CatalogStore(database)
            path = str(Path(directory) / "book.epub")
            store.sync_index({"archivos": [{"ruta": path, "titulo": "Committed title"}]})
            connection = sqlite3.connect(database)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE works SET title='Not committed'")
                with patch.object(core, "CATALOG_DB", database), \
                        patch.object(CatalogStore, "_initialize", side_effect=AssertionError("Inspector must not initialize")):
                    record = core.registro_catalogo_para_ruta(path)
                self.assertEqual(record["title"], "Committed title")
            finally:
                connection.rollback()
                connection.close()

    def test_inspector_does_not_create_a_missing_database(self):
        import tempfile
        from pathlib import Path
        import library_core as core
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "not_created.sqlite3"
            with patch.object(core, "CATALOG_DB", database):
                self.assertIsNone(core.registro_catalogo_para_ruta("book.epub"))
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
