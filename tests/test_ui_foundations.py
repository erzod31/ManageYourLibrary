import io
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from core.cover_service import CoverService
from core.library_view_model import (
    display_item,
    filter_items,
    item_is_favorite,
    library_stats,
    provenance_lines,
)
from rounded_widgets import RoundedButton, render_rounded_surface
from ui.icon_palette import render_icon
from ui.workspace import (
    TEXT,
    Workspace,
    full_display_path,
    interactive_cursor,
    wheel_units,
)


class VisualFoundationTests(unittest.TestCase):
    def test_primary_navigation_tooltips_are_translated(self):
        for language in TEXT.values():
            for key in (
                "library_tip", "authors_tip", "series_tip", "tags_tip",
                "favorites_tip", "import_tip", "reviews_tip",
            ):
                self.assertTrue(language[key])

    def test_icon_only_controls_have_translated_accessible_names(self):
        for language in TEXT.values():
            for key in ("covers", "table", "details", "covers_tip", "table_tip", "details_tip"):
                self.assertTrue(language[key])

    def test_interactive_detail_metadata_is_translated(self):
        for language in TEXT.values():
            for key in ("favorite_add", "favorite_active", "favorite_added", "favorite_removed"):
                self.assertTrue(language[key])

    def test_page_shortcuts_cover_primary_workflows(self):
        self.assertEqual(
            dict(Workspace.PAGE_SHORTCUTS),
            {
                "<Alt-Key-1>": "library",
                "<Alt-Key-2>": "import",
                "<Alt-Key-3>": "reviews",
                "<Alt-Key-4>": "activity",
                "<Alt-Key-5>": "settings",
            },
        )

    def test_rounded_button_keyboard_invoke_respects_disabled_state(self):
        calls = []
        button = object.__new__(RoundedButton)
        button.state = "normal"
        button.command = lambda: calls.append("called")

        button.invoke()
        button.state = "disabled"
        button.invoke()

        self.assertEqual(calls, ["called"])

    def test_editorial_icon_palette_is_crisp_and_complete(self):
        names = (
            "library", "author", "series", "tag", "favorite", "import", "reviews",
            "search", "grid", "list", "details", "settings", "sun", "moon", "open",
            "edit", "more", "folder", "sort", "undo", "activity",
        )

        for name in names:
            icon = render_icon(name, "#a9573e", size=24)
            self.assertEqual(icon.size, (24, 24))
            self.assertIsNotNone(icon.getchannel("A").getbbox(), name)

    def test_sidebar_scopes_filter_existing_catalog_fields(self):
        workspace = object.__new__(Workspace)
        items = [
            {"titulo": "A", "autor_mostrar": "Autora", "serie_mostrar": "Saga", "tags_mostrar": ["favorito"]},
            {"titulo": "B", "autor_mostrar": "Autor desconocido", "serie_mostrar": "", "tags_mostrar": []},
        ]

        workspace.library_scope = "authors"
        self.assertEqual([item["titulo"] for item in workspace._apply_library_scope(items)], ["A"])
        workspace.library_scope = "series"
        self.assertEqual([item["titulo"] for item in workspace._apply_library_scope(items)], ["A"])
        workspace.library_scope = "tags"
        self.assertEqual([item["titulo"] for item in workspace._apply_library_scope(items)], ["A"])
        workspace.library_scope = "favorites"
        self.assertEqual([item["titulo"] for item in workspace._apply_library_scope(items)], ["A"])

    def test_rounded_surface_uses_antialiased_edge_pixels(self):
        surface = render_rounded_surface(80, 38, 16, "#ffffff", "#a9573e", "#7f3f2e")

        self.assertEqual(surface.size, (80, 38))
        self.assertGreater(len(set(surface.get_flattened_data())), 3)
        self.assertEqual(surface.getpixel((0, 0)), (255, 255, 255))

    def test_details_path_is_absolute(self):
        shown = full_display_path(Path("books") / "sample.epub")

        self.assertTrue(Path(shown).is_absolute())
        self.assertTrue(shown.endswith(str(Path("books") / "sample.epub")))

    def test_mouse_wheel_delta_is_normalized_for_both_directions(self):
        self.assertEqual(wheel_units(120), -1)
        self.assertEqual(wheel_units(-120), 1)
        self.assertEqual(wheel_units(240), -2)
        self.assertEqual(wheel_units(1), -1)
        self.assertEqual(wheel_units(0), 0)

    def test_pointer_cursor_matches_interactive_state(self):
        self.assertEqual(interactive_cursor(True), "hand2")
        self.assertEqual(interactive_cursor(False), "arrow")

    def test_cover_relayout_reuses_existing_cards(self):
        class Card:
            def __init__(self):
                self.position = None

            def winfo_exists(self):
                return True

            def grid_configure(self, **kwargs):
                self.position = (kwargs["row"], kwargs["column"])

        class Grid:
            def __init__(self):
                self.weights = {}

            def grid_columnconfigure(self, column, weight):
                self.weights[column] = weight

        cards = [Card() for _ in range(7)]
        workspace = object.__new__(Workspace)
        workspace.dynamic_cards = cards
        workspace._cover_columns = 4
        workspace.cover_inner = Grid()
        workspace._schedule_cover_scrollregion = lambda: None

        workspace._relayout_cover_cards(3)

        self.assertEqual(workspace.dynamic_cards, cards)
        self.assertEqual([card.position for card in cards], [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0)])
        self.assertEqual(workspace.cover_inner.weights, {0: 1, 1: 1, 2: 1, 3: 0})


class LibraryViewModelTests(unittest.TestCase):
    def test_favorite_accepts_boolean_and_legacy_tag_records(self):
        self.assertTrue(item_is_favorite({"favorite": True}))
        self.assertTrue(item_is_favorite({"tags": ["ensayo", "favorito"]}))
        self.assertTrue(item_is_favorite({"favorite": "sí"}))
        self.assertFalse(item_is_favorite({"favorite": False, "tags": ["ensayo"]}))

    def test_display_filter_and_stats(self):
        items = [
            {
                "ruta": "C:/books/Clara Montes - El jardín invisible.epub",
                "nombre": "Clara Montes - El jardín invisible.epub",
                "extension": ".epub",
                "autor": "Clara Montes",
                "tamano_bytes": 1536,
            },
            {
                "ruta": "C:/books/Documento_sin_autor.pdf",
                "nombre": "Documento_sin_autor.pdf",
                "extension": ".pdf",
                "autor": "",
                "tamano_bytes": 2048,
            },
        ]
        shown = display_item(items[0])
        self.assertEqual(shown["titulo"], "El jardín invisible")
        self.assertEqual(shown["autor_mostrar"], "Clara Montes")
        self.assertEqual(shown["formato"], "EPUB")
        self.assertEqual([item["formato"] for item in filter_items(items, "JARDIN")], ["EPUB"])
        self.assertEqual([item["formato"] for item in filter_items(items, extension="pdf")], ["PDF"])
        self.assertEqual(
            library_stats(items),
            {"books": 2, "authors": 1, "formats": 2, "missing_author": 1},
        )

    def test_standard_filename_exposes_openlibrary_cover_link(self):
        item = display_item({
            "ruta": "C:/books/Clara Montes - El jardín invisible [9780307474728].epub",
            "nombre": "Clara Montes - El jardín invisible [9780307474728].epub",
            "extension": ".epub",
        })

        self.assertEqual(item["isbn"], "9780307474728")
        self.assertEqual(
            item["cover_url"],
            "https://covers.openlibrary.org/b/isbn/9780307474728-M.jpg?default=false",
        )

    def test_standard_filename_without_index_author_uses_author_first(self):
        item = display_item({
            "ruta": "C:/books/Clara Montes - El jardín invisible.epub",
            "nombre": "Clara Montes - El jardín invisible.epub",
        })

        self.assertEqual(item["autor_mostrar"], "Clara Montes")
        self.assertEqual(item["titulo"], "El jardín invisible")

    def test_search_uses_edition_fields_and_provenance_is_readable(self):
        row = {
            "ruta": "C:/books/book.epub", "nombre": "book.epub", "series": "Archivo Solar",
            "language": "es", "publisher": "Editorial Norte", "isbn": "9780307474728",
            "provenance": {"titulo": {"source": "EPUB", "confidence": 97}},
        }

        self.assertEqual(len(filter_items([row], "Editorial Norte")), 1)
        self.assertEqual(provenance_lines(row), ["titulo: EPUB · 97%"])


class CoverServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = CoverService(self.root / "cache", size=(80, 112))

    def tearDown(self):
        self.temporary.cleanup()

    def _image_bytes(self, path: Path, color="navy"):
        Image.new("RGB", (120, 180), color).save(path, format="PNG")
        return path.read_bytes()

    def test_direct_image_is_cached_at_requested_size(self):
        source = self.root / "cover.png"
        self._image_bytes(source)
        cached = self.service.thumbnail_path(source)
        self.assertTrue(cached.exists())
        with Image.open(cached) as image:
            self.assertEqual(image.size, (80, 112))
        self.assertEqual(self.service.thumbnail_path(source), cached)

    def test_cbz_uses_first_image(self):
        raw_path = self.root / "raw.png"
        raw = self._image_bytes(raw_path, "green")
        archive = self.root / "comic.cbz"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("002.png", raw)
            bundle.writestr("001.png", raw)
        cached = self.service.thumbnail_path(archive)
        self.assertTrue(cached.exists())

    def test_epub_resolves_declared_cover(self):
        raw_path = self.root / "raw.png"
        raw = self._image_bytes(raw_path, "maroon")
        epub = self.root / "book.epub"
        container = """<?xml version="1.0"?>
        <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
          <rootfiles><rootfile full-path="OPS/content.opf"/></rootfiles>
        </container>"""
        package = """<?xml version="1.0"?>
        <package xmlns="http://www.idpf.org/2007/opf">
          <metadata><meta name="cover" content="cover-id"/></metadata>
          <manifest><item id="cover-id" href="images/cover.png" media-type="image/png"/></manifest>
        </package>"""
        with zipfile.ZipFile(epub, "w") as bundle:
            bundle.writestr("META-INF/container.xml", container)
            bundle.writestr("OPS/content.opf", package)
            bundle.writestr("OPS/images/cover.png", raw)
        cached = self.service.thumbnail_path(epub)
        self.assertTrue(cached.exists())

    def test_remote_cover_is_lazy_cached_and_reused(self):
        source = self.root / "book.mobi"
        source.write_bytes(b"book")
        raw = io.BytesIO()
        Image.new("RGB", (120, 180), "teal").save(raw, format="JPEG")
        calls = []
        url = "https://covers.openlibrary.org/b/isbn/9780307474728-M.jpg?default=false"

        class Response:
            status = 200
            headers = {"Content-Type": "image/jpeg", "Content-Length": str(len(raw.getvalue()))}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return url

            def read(self, _limit):
                return raw.getvalue()

        def open_cover(_request, timeout):
            calls.append(timeout)
            return Response()

        service = CoverService(self.root / "remote-cache", size=(80, 112), urlopen_func=open_cover)
        cached = service.thumbnail_path(source, remote_url=url)

        self.assertTrue(cached.exists())
        self.assertEqual(cached.suffix, ".webp")
        self.assertEqual(service.thumbnail_path(source, remote_url=url), cached)
        self.assertEqual(len(calls), 1)

    def test_remote_cover_rejects_unknown_hosts_without_request(self):
        source = self.root / "book.mobi"
        source.write_bytes(b"book")
        calls = []
        service = CoverService(self.root / "remote-cache", urlopen_func=lambda *_args, **_kwargs: calls.append(True))

        self.assertIsNone(service.thumbnail_path(source, remote_url="https://example.com/cover.jpg"))
        self.assertEqual(calls, [])

    def test_disk_cache_prunes_oldest_files_to_bounded_size(self):
        cache = self.root / "bounded-cache"
        cache.mkdir()
        old = cache / "old.webp"
        new = cache / "new.webp"
        old.write_bytes(b"a" * 600)
        new.write_bytes(b"b" * 600)
        os.utime(old, (time.time() - 100, time.time() - 100))
        service = CoverService(cache, max_cache_bytes=1000)

        service.prune_cache()

        self.assertFalse(old.exists())
        self.assertTrue(new.exists())


if __name__ == "__main__":
    unittest.main()
