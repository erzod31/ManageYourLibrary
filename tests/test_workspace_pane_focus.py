"""Exercise pane keyboard routing without creating Tk windows or user profiles."""
import tkinter as tk
import unittest
from types import SimpleNamespace

from ui.workspace import Workspace


class FocusControl:
    def __init__(self, owner, *, mapped=True, state='normal', value='', ttk_disabled=False):
        self.owner = owner
        self.mapped = mapped
        self.state = state
        self.value = value
        self.ttk_disabled = ttk_disabled

    def winfo_ismapped(self):
        return self.mapped

    def winfo_exists(self):
        return True

    def cget(self, key):
        assert key == 'state'
        return self.state

    def instate(self, states):
        assert states == ('disabled',)
        return self.ttk_disabled

    def get(self):
        return self.value

    def focus_set(self):
        self.owner.focused = self


class PageCanvas:
    def __init__(self, *, top=0, height=200, bounds=(0, 0, 500, 1000), mapped=True):
        self.top = top
        self.height = height
        self.bounds = bounds
        self.mapped = mapped
        self.moves = []

    def winfo_ismapped(self):
        return self.mapped

    def bbox(self, tag):
        assert tag == 'all'
        return self.bounds

    def winfo_height(self):
        return self.height

    def winfo_rooty(self):
        return 100

    def canvasy(self, y):
        return self.top + y

    def yview_moveto(self, fraction):
        self.moves.append(fraction)


class PaneFocusTests(unittest.TestCase):
    def setUp(self):
        self.workspace = object.__new__(Workspace)
        self.focused = None
        self.workspace.root = SimpleNamespace(focus_get=lambda: self.focused)
        self.workspace.app = SimpleNamespace()
        self.workspace.current_page = 'library'
        self.workspace.view_mode = 'covers'
        self.workspace.selected_item = None
        self.nav = self.control()
        self.search = self.control()
        self.table = self.control()
        self.path = self.control(state='readonly', value='synthetic.epub')
        self.workspace.nav_buttons = {'library': self.nav}
        self.workspace.search_entry = self.search
        self.workspace.tree = self.table
        self.workspace.detail_path_entry = self.path
        self.workspace.entity_view = self.control(mapped=False)
        self.workspace.entity_tree = self.control()
        self.workspace.page_scroll_canvases = {}

    def control(self, **kwargs):
        return FocusControl(self, **kwargs)

    def cycle(self, backward=False):
        self.assertEqual(self.workspace._cycle_pane_focus(SimpleNamespace(state=int(backward))), 'break')
        return self.focused

    def test_empty_selection_does_not_focus_path(self):
        self.focused = self.search
        self.assertIs(self.cycle(), self.nav)

    def test_selected_book_with_empty_path_does_not_focus_path(self):
        self.workspace.selected_item = {'ruta': ''}
        self.path.value = '   '
        self.focused = self.search
        self.assertIs(self.cycle(), self.nav)

    def test_selected_book_allows_readonly_path(self):
        self.workspace.selected_item = {'ruta': 'synthetic.epub'}
        self.focused = self.search
        self.assertIs(self.cycle(), self.path)
        self.assertIs(self.cycle(), self.nav)
        self.assertIs(self.cycle(backward=True), self.path)

    def test_external_focus_enters_first_or_last_valid_anchor(self):
        self.focused = self.control()
        self.assertIs(self.cycle(), self.nav)
        self.focused = self.control()
        self.assertIs(self.cycle(backward=True), self.search)
        self.workspace.selected_item = {'ruta': 'synthetic.epub'}
        self.focused = self.control()
        self.assertIs(self.cycle(backward=True), self.path)

    def test_hidden_details_are_skipped(self):
        self.workspace.selected_item = {'ruta': 'synthetic.epub'}
        self.path.mapped = False
        self.focused = self.search
        self.assertIs(self.cycle(), self.nav)

    def test_disabled_details_are_skipped(self):
        self.workspace.selected_item = {'ruta': 'synthetic.epub'}
        self.path.ttk_disabled = True
        self.focused = self.search
        self.assertIs(self.cycle(), self.nav)

    def test_disabled_rounded_navigation_is_skipped(self):
        self.nav.state = 'disabled'
        self.focused = self.control()
        self.assertIs(self.cycle(), self.search)

    def test_table_and_entity_views_have_useful_anchors(self):
        self.workspace.view_mode = 'table'
        self.focused = self.nav
        self.assertIs(self.cycle(), self.table)
        self.workspace.current_page = 'authors'
        self.workspace.entity_view.mapped = True
        self.focused = self.nav
        self.assertIs(self.cycle(), self.workspace.entity_tree)

    def test_disabled_table_falls_back_to_search(self):
        self.workspace.view_mode = 'table'
        self.table.ttk_disabled = True
        self.focused = self.nav
        self.assertIs(self.cycle(), self.search)

    def test_ttk_table_does_not_need_a_state_option(self):
        def no_state_option(_key):
            raise tk.TclError('unknown option "-state"')
        self.workspace.view_mode = 'table'
        self.table.cget = no_state_option
        self.focused = self.nav
        self.assertIs(self.cycle(), self.table)

    def test_live_non_ttk_anchor_without_state_option_is_not_discarded(self):
        def no_state_option(_key):
            raise tk.TclError('unknown option "-state"')
        self.nav.instate = None
        self.nav.cget = no_state_option
        self.assertIs(self.cycle(), self.nav)

    def test_non_ttk_disabled_anchor_is_skipped(self):
        self.nav.instate = None
        self.nav.state = lambda: ()
        self.nav.cget = lambda _key: 'disabled'
        self.assertIs(self.cycle(), self.search)

    def test_import_page_uses_existing_library_path_field(self):
        self.workspace.current_page = 'import'
        self.workspace.app.entry_biblioteca = self.control()
        self.focused = self.nav
        self.assertIs(self.cycle(), self.workspace.app.entry_biblioteca)

    def test_review_page_skips_disabled_and_hidden_actions(self):
        self.workspace.current_page = 'reviews'
        self.workspace.scan_button = self.control(state='disabled')
        self.workspace.resume_reviews_button = self.control(mapped=False)
        self.workspace.app.btn_metadatos = self.control()
        self.focused = self.nav
        self.assertIs(self.cycle(), self.workspace.app.btn_metadatos)

    def test_activity_page_uses_existing_log(self):
        self.workspace.current_page = 'activity'
        self.workspace.app.texto = self.control()
        self.focused = self.nav
        self.assertIs(self.cycle(), self.workspace.app.texto)

    def test_settings_page_uses_enabled_existing_setting(self):
        self.workspace.current_page = 'settings'
        self.workspace.ocr_spinbox = self.control(state='disabled')
        self.workspace.offline_check = self.control()
        self.focused = self.nav
        self.assertIs(self.cycle(), self.workspace.offline_check)

    def test_non_library_page_never_focuses_stale_book_path(self):
        self.workspace.current_page = 'activity'
        self.workspace.selected_item = {'ruta': 'synthetic.epub'}
        self.workspace.app.texto = self.control()
        self.focused = self.control()
        self.assertIs(self.cycle(backward=True), self.workspace.app.texto)

    def test_no_valid_anchors_keeps_focus(self):
        self.nav.mapped = False
        self.search.mapped = False
        external = self.control()
        self.focused = external
        self.assertIs(self.cycle(), external)

    def test_destroyed_anchor_is_ignored(self):
        def destroyed():
            raise tk.TclError('bad window path name')
        self.nav.winfo_ismapped = destroyed
        self.assertIs(self.cycle(), self.search)

    def scrolled_page(self, page, *, target_top, target_height=30, **canvas_options):
        self.workspace.current_page = page
        canvas = PageCanvas(**canvas_options)
        self.workspace.page_scroll_canvases[page] = canvas
        target = self.control()
        target.master = SimpleNamespace(master=canvas)
        target.winfo_rooty = lambda: canvas.winfo_rooty() + target_top - canvas.top
        target.winfo_height = lambda: target_height
        if page == 'settings':
            self.workspace.ocr_spinbox = target
        elif page == 'import':
            self.workspace.app.entry_biblioteca = target
        self.focused = self.nav
        return canvas, target

    def test_f6_reveals_settings_anchor_above_scrolled_viewport(self):
        canvas, target = self.scrolled_page('settings', target_top=40, top=400)
        self.assertIs(self.cycle(), target)
        self.assertEqual(canvas.moves, [.032])

    def test_f6_reveals_import_anchor_below_small_viewport(self):
        canvas, target = self.scrolled_page('import', target_top=900)
        self.assertIs(self.cycle(), target)
        self.assertEqual(canvas.moves, [.738])

    def test_f6_retains_scroll_when_target_is_already_visible(self):
        canvas, target = self.scrolled_page('settings', target_top=140, top=100)
        self.assertIs(self.cycle(), target)
        self.assertEqual(canvas.moves, [])

    def test_reverse_f6_reveals_target_before_focusing_it(self):
        canvas, target = self.scrolled_page('settings', target_top=40, top=400)
        self.focused = self.control()
        def focus_after_scroll():
            self.assertTrue(canvas.moves)
            self.focused = target
        target.focus_set = focus_after_scroll
        self.assertIs(self.cycle(backward=True), target)

    def test_f6_navigation_does_not_scroll_page(self):
        canvas, target = self.scrolled_page('settings', target_top=40, top=400)
        self.focused = target
        self.assertIs(self.cycle(), self.nav)
        self.assertEqual(canvas.moves, [])

    def test_oversized_anchor_reveals_its_top(self):
        canvas, target = self.scrolled_page('import', target_top=400, target_height=300)
        self.assertIs(self.cycle(), target)
        self.assertEqual(canvas.moves, [.392])

    def test_scroll_is_clamped_to_declared_canvas_bounds(self):
        canvas, target = self.scrolled_page('settings', target_top=1030, bounds=(0, 50, 500, 1050))
        self.assertIs(self.cycle(), target)
        self.assertEqual(canvas.moves, [.8])

    def test_fitting_or_unmapped_page_does_not_scroll(self):
        for options in ({'bounds': (0, 0, 500, 100)}, {'mapped': False}):
            canvas, target = self.scrolled_page('settings', target_top=40, top=400, **options)
            self.assertIs(self.cycle(), target)
            self.assertEqual(canvas.moves, [])

    def test_destroyed_scroll_canvas_does_not_break_focus_cycle(self):
        canvas, target = self.scrolled_page('settings', target_top=40, top=400)
        def destroyed(_tag):
            raise tk.TclError('bad window path name')
        canvas.bbox = destroyed
        self.assertIs(self.cycle(), target)

    def test_tab_focus_reveals_current_target_after_geometry_settles(self):
        canvas, target = self.scrolled_page('settings', target_top=40, top=400)
        callbacks = []
        self.workspace.root.after_idle = callbacks.append
        self.focused = target
        self.workspace._on_page_focus_in(SimpleNamespace(widget=target))
        self.assertEqual(canvas.moves, [])
        callbacks.pop()()
        self.assertEqual(canvas.moves, [.032])

    def test_later_tab_focus_does_not_scroll_for_an_old_target(self):
        canvas, target = self.scrolled_page('settings', target_top=40, top=400)
        callbacks = []
        self.workspace.root.after_idle = callbacks.append
        self.workspace._on_page_focus_in(SimpleNamespace(widget=target))
        self.focused = self.nav
        callbacks.pop()()
        self.assertEqual(canvas.moves, [])

    def test_page_change_before_focus_idle_does_not_scroll_old_page(self):
        canvas, target = self.scrolled_page('settings', target_top=40, top=400)
        callbacks = []
        self.workspace.root.after_idle = callbacks.append
        self.focused = target
        self.workspace._on_page_focus_in(SimpleNamespace(widget=target))
        self.workspace.current_page = 'import'
        replacement = PageCanvas()
        self.workspace.page_scroll_canvases['import'] = replacement
        callbacks.pop()()
        self.assertEqual(canvas.moves, [])
        self.assertEqual(replacement.moves, [])


if __name__ == '__main__':
    unittest.main()
