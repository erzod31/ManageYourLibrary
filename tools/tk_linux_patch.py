"""Hash-locked repair of the pinned Tk 9.1 Linux ATK provider.

The AT-SPI bridge consumes standard AtkWindow signals, not arbitrary Tk
window-* signals. Window state follows Tk's current focus for the application
and display, never a test-only override. This is not external-reader evidence.
Primary contracts: https://gnome.pages.gitlab.gnome.org/at-spi2-core/atk/iface.Window.html
and https://raw.githubusercontent.com/GNOME/at-spi2-core/main/atk-adaptor/event.c
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

PATCH_ID = 'myl-tk91-linux-atk-2'
INPUT_HASHES = {'tkUnixAccessibility.c': 'de0a9d9e6b3e9ea1d08dbb97927e49817fa4ef84adb34ee8bea6fb10e49d9f6a'}
NATIVE = Path(__file__).parent / 'native'
HELPER = 'tkUnixA11yWindow.h'
OUTPUT_HELPER = 'mylUnixA11yWindow.h'
RECEIPT = 'myl-linux-accessibility-patch.json'


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('Pinned Linux Tk patch context mismatch: ' + before[:65])
    return source.replace(before, after, 1)


def replace_function(source, name, body):
    match = re.search(r'^\s*(?:static )?(?:[A-Za-z_][A-Za-z_0-9]*\s*\*?\s+)?' + re.escape(name)
                      + r'\([^;]*?^\{\n.*?^\}', source, re.M | re.S)
    if not match:
        raise ValueError('Missing pinned Linux Tk function: ' + name)
    signature = match[0].split('{', 1)[0]
    return source[:match.start()] + signature + '{\n' + body.strip('\n') + '\n}' + source[match.end():]


def repair_provider(source):
    source = replace_once(source, '    bool is_focused;',
                          '    bool is_focused;\n    bool is_active;\n    bool is_defunct;\n'
                          '    bool visibility_known;\n    bool is_visible;\n    bool is_showing;')
    source = replace_once(source, '/* Configure event loop. */',
                          '#include "mylUnixA11yWindow.h"\n\n/* Configure event loop. */')
    source = replace_once(source, '''    if (!acc) {
	return state_set;
    }

    /* Always add these basic states. */''', '''    if (!acc) return state_set;
    if (acc->is_defunct) {
        atk_state_set_add_state(state_set, ATK_STATE_DEFUNCT);
        return state_set;
    }
    if (MylTkAtkWindowActive(acc->tkwin))
        atk_state_set_add_state(state_set, ATK_STATE_ACTIVE);

    /* Always add these basic states. */''')
    source = replace_once(source, '    if (acc->is_focused) {',
                          '    if (acc->tkwin && TkGetFocusWin((TkWindow *)acc->tkwin) == (TkWindow *)acc->tkwin) {')
    source = replace_once(source, '    atk_class->ref_child = tk_ref_child;',
                          '    atk_class->ref_child = tk_ref_child;\n    atk_class->get_index_in_parent = MylTkAtkIndexInParent;')
    source = replace_once(source, '''    if (Tk_IsTopLevel(tkwin)) {
	parentAcc = tk_root_accessible;

	if (!g_list_find''', '''    if (Tk_IsTopLevel(tkwin)) {
	parentAcc = tk_root_accessible;
        MylTkAtkSetWindowParent(accessible);

	if (!g_list_find''')
    source = replace_once(source, '''static gchar *GetAtkValueForWidget(Tk_Window win)
{
    if (!win) return NULL;''', '''static gchar *GetAtkValueForWidget(Tk_Window win)
{
    if (!win) return NULL;
    if (!MylTkAtkValueAllowed(win)) return g_strdup("");''')
    source = replace_once(source, '''static gchar *tk_text_get_text(
    TCL_UNUSED(AtkText *),
    TCL_UNUSED(gint),
    TCL_UNUSED(gint))
{
    return NULL;
}''', '''static gchar *tk_text_get_text(AtkText *text, gint start, gint end)
{
    return MylTkAtkText(text, start, end);
}''')
    source = replace_once(source, '''static gint tk_text_get_character_count(
    TCL_UNUSED(AtkText *))
{
    return 0;
}''', '''static gint tk_text_get_character_count(AtkText *text)
{
    return MylTkAtkTextCount(text);
}''')
    source = replace_once(source, '''static gint tk_text_get_caret_offset(
    TCL_UNUSED(AtkText *))
{
    return -1;
}''', '''static gint tk_text_get_caret_offset(AtkText *text)
{
    return MylTkAtkTextCaret(text);
}''')
    source = replace_once(source, '    iface->get_text_at_offset = NULL;',
                          '    iface->get_text_at_offset = MylTkAtkTextAtOffset;')
    source = replace_once(source, '''    TkAtkAccessible *acc = (TkAtkAccessible *)g_object_new(TK_ATK_TYPE_ACCESSIBLE, NULL);
    acc->interp = interp;''', '''    TkAtkAccessible *acc = (TkAtkAccessible *)g_object_new(
            Tk_IsTopLevel(tkwin) ? myl_tk_atk_window_get_type() : TK_ATK_TYPE_ACCESSIBLE, NULL);
    acc->interp = interp;''')
    # The hash owns each native widget provider. Toplevel lists are borrowed
    # indexes of the same providers; AT-SPI may hold separate client refs.
    source = replace_once(source, '    g_object_ref(accessible);\n\n    AtkObject *parentAcc = NULL;',
                          '    /* Toplevel list borrows the widget-map reference. */\n    AtkObject *parentAcc = NULL;')
    source = replace_once(source, '''    TkAtkAccessible_RegisterEventHandlers(tkwin, acc);

    return obj;''', '''    TkAtkAccessible_RegisterEventHandlers(tkwin, acc);
    g_object_unref(obj); /* Transfer the constructor reference to the map. */
    return GetAtkObjectForTkWindow(tkwin); /* Borrowed, as for an existing object. */''')
    # The bridge listens to AtkWindow's own interface signals. These unrelated
    # custom signal definitions would never produce a window:activate event.
    start = source.index('    /* Register custom AT-SPI signals. */')
    end = source.index('    gobject_class->finalize', start)
    source = source[:start] + source[end:]
    source = replace_once(source, '''/* Signal IDs for custom AT-SPI signals. */
static guint window_create_signal_id;
static guint window_activate_signal_id;
static guint window_deactivate_signal_id;

''', '')
    source = replace_once(source, 'g_signal_emit_by_name(tk_root_accessible, "children-changed::add", index, accessible);',
                          'g_signal_emit_by_name(tk_root_accessible, "children-changed::add", index, accessible);\n'
                          '            if (ATK_IS_WINDOW(accessible)) g_signal_emit_by_name(accessible, "create");')
    source = replace_function(source, 'tk_get_n_children', '''
    if (obj == tk_root_accessible) return g_list_length(toplevel_accessible_objects);
    TkAtkAccessible *acc = (TkAtkAccessible *)obj;
    gint count = 0;
    if (!acc || !acc->tkwin || acc->is_defunct) return 0;
    for (TkWindow *child = ((TkWindow *)acc->tkwin)->childList; child; child = child->nextPtr)
        if (!Tk_IsTopLevel((Tk_Window)child)) count++;
    return count;''')
    source = replace_once(source, '''	 childPtr = childPtr->nextPtr, index++) {

	if (index == i)''', '''	 childPtr = childPtr->nextPtr) {
        if (Tk_IsTopLevel((Tk_Window)childPtr)) continue;
	if (index++ == i)''')
    source = replace_once(source, '''		    gint childCount = atk_object_get_n_accessible_children(obj);
		    g_signal_emit_by_name(obj, "children-changed::add", childCount - 1, child_obj);''',
                          '                    g_signal_emit_by_name(obj, "children-changed::add", i, child_obj);')
    source = replace_once(source, '''	gint child_count = atk_object_get_n_accessible_children(parentAcc);
	g_signal_emit_by_name(parentAcc, "children-changed::add", child_count, accessible);''',
                          '        g_signal_emit_by_name(parentAcc, "children-changed::add", MylTkAtkIndexInParent(accessible), accessible);')
    source = replace_once(source, '''		gint child_index = atk_object_get_n_accessible_children(parentAcc);
		g_signal_emit_by_name(parentAcc, "children-changed::add", child_index, acc);''',
                          '                g_signal_emit_by_name(parentAcc, "children-changed::add", MylTkAtkIndexInParent(acc), acc);')
    source = replace_once(source, '''			gint childCount = atk_object_get_n_accessible_children(parentAcc);
			g_signal_emit_by_name(parentAcc, "children-changed::add", childCount - 1, acc);''',
                          '                    g_signal_emit_by_name(parentAcc, "children-changed::add", MylTkAtkIndexInParent(acc), acc);')
    start = source.index('    /* After registering all children, emit one more children-changed')
    end = source.index('\n}', start)
    source = source[:start] + '    /* Registration emits real children once; no NULL pseudo-child refresh. */' + source[end:]
    start = source.index('\t/* If this widget currently has focus, update focus state. */')
    end = source.index('\n    }\n\n    /* Recursively register all children. */', start)
    source = source[:start] + '''        /* Only the actual focus widget emits focus; ordinary parents do not
         * manage descendants and must not report fake insertions. */
        if (TkGetFocusWin((TkWindow *)tkwin) == (TkWindow *)tkwin)
            UpdateAtkFocusChain(tkwin);''' + source[end:]
    source = replace_function(source, 'UpdateAtkFocusChain', '''
    if (!focused) return;
    Tcl_Interp *interp = Tk_Interp(focused);
    if (!interp || TkGetFocusWin((TkWindow *)focused) != (TkWindow *)focused) return;
    EnsureWidgetInAtkHierarchy(interp, focused);
    AtkObject *obj = GetAtkObjectForTkWindow(focused);
    if (!obj) return;
    TkAtkAccessible *acc = (TkAtkAccessible *)obj;
    acc->is_focused = true;
    MylTkAtkSyncActiveWindows();
    atk_object_notify_state_change(obj, ATK_STATE_FOCUSED, TRUE);
    g_signal_emit_by_name(obj, "focus-event", TRUE);
    /* Ordinary focus is not a child insertion or managed-descendant change. */''')
    source = replace_function(source, 'TkAtkAccessible_FocusHandler', '''
    TkAtkAccessible *acc = (TkAtkAccessible *)clientData;
    if (!acc || !acc->tkwin || acc->is_defunct || !eventPtr
            || (eventPtr->type != FocusIn && eventPtr->type != FocusOut)) return;
    gboolean focused = TkGetFocusWin((TkWindow *)acc->tkwin) == (TkWindow *)acc->tkwin;
    MylTkAtkSyncActiveWindows();
    if (focused != acc->is_focused) {
        acc->is_focused = focused;
        atk_object_notify_state_change(ATK_OBJECT(acc), ATK_STATE_FOCUSED, focused);
        g_signal_emit_by_name(acc, "focus-event", focused);
    }''')
    source = replace_function(source, 'tk_grab_focus', '''
    TkAtkAccessible *acc = (TkAtkAccessible *)component;
    if (!acc || !acc->tkwin || !acc->interp || acc->is_defunct) return FALSE;
    Tcl_Interp *interp = acc->interp;
    g_object_ref(acc);
    Tcl_Preserve(interp);
    Tcl_Obj *args[3] = {Tcl_NewStringObj("focus", -1), Tcl_NewStringObj("-force", -1),
                        Tcl_NewStringObj(Tk_PathName(acc->tkwin), -1)};
    Tcl_InterpState saved = Tcl_SaveInterpState(interp, TCL_OK);
    for (int i = 0; i < 3; i++) Tcl_IncrRefCount(args[i]);
    int result = Tcl_EvalObjv(interp, 3, args, TCL_EVAL_GLOBAL);
    for (int i = 0; i < 3; i++) Tcl_DecrRefCount(args[i]);
    Tcl_RestoreInterpState(interp, saved);
    gboolean focused = result == TCL_OK && !acc->is_defunct && acc->tkwin
            && TkGetFocusWin((TkWindow *)acc->tkwin) == (TkWindow *)acc->tkwin;
    if (focused) UpdateAtkFocusChain(acc->tkwin);
    Tcl_Release(interp);
    g_object_unref(acc);
    return focused;''')
    source = replace_once(source, '''    Tk_Window parentWin = (Tk_Window)clientData;
    if (!parentWin) return;''', '''    TkAtkAccessible *parent = (TkAtkAccessible *)clientData;
    Tk_Window parentWin = parent ? parent->tkwin : NULL;
    if (!parentWin || parent->is_defunct) return;''')
    source = replace_once(source, '''    AtkObject *childAcc = TkCreateAccessibleAtkObject(interp, childWin, Tk_PathName(childWin));
    if (!childAcc) return;

    AtkObject *parentAcc''', '''    AtkObject *childAcc = TkCreateAccessibleAtkObject(interp, childWin, Tk_PathName(childWin));
    if (!childAcc) return;
    if (Tk_IsTopLevel(childWin)) {
        RegisterToplevelWindow(interp, childWin, childAcc);
        return;
    }

    AtkObject *parentAcc''')
    source = replace_once(source, '''    Tk_Window tkwin = (Tk_Window)clientData;
    if (!tkwin) {''', '''    TkAtkAccessible *provider = (TkAtkAccessible *)clientData;
    Tk_Window tkwin = provider ? provider->tkwin : NULL;
    if (!tkwin || provider->is_defunct) {''')
    source = replace_once(source, '    Tk_CreateEventHandler(tkwin, ConfigureNotify,',
                          '    Tk_CreateEventHandler(tkwin, StructureNotifyMask,')
    source = replace_function(source, 'TkAtkAccessible_DestroyHandler', '''
    if (eventPtr && eventPtr->type == DestroyNotify)
        MylTkAtkDetach((TkAtkAccessible *)clientData);''')
    # Preserve both the child-list index and exact accessible object in native
    # create events. A count is already one past the last valid child index.
    source = replace_once(source, '''    gint idx = atk_object_get_n_accessible_children(parentAcc);
    g_signal_emit_by_name(parentAcc, "children-changed::add", idx, childAcc);''',
                          '    g_signal_emit_by_name(parentAcc, "children-changed::add", MylTkAtkIndexInParent(childAcc), childAcc);')
    # Mapping/geometry changes are not child insertions. Queries already use
    # live mapped state; refresh only state and active-window transitions.
    start = source.index('\t/* For child widgets of a non-root toplevel, also nudge')
    end = source.index('\n    } else {', start)
    source = source[:start] + source[end:]
    source = replace_once(source, '''    if (!eventPtr || eventPtr->type != ConfigureNotify) {''',
                          '''    if (!eventPtr || (eventPtr->type != ConfigureNotify
            && eventPtr->type != MapNotify && eventPtr->type != UnmapNotify)) {''')
    source = replace_once(source, '''    /* Update geometry on configure. */''',
                          '    MylTkAtkSyncActiveWindows();\n    /* Update geometry on configure. */')
    source = replace_function(source, 'TkAtkAccessible_ConfigureHandler', '''
    TkAtkAccessible *acc = (TkAtkAccessible *)clientData;
    if (!eventPtr || !acc || !acc->tkwin || acc->is_defunct) return;
    if (eventPtr->type == ConfigureNotify) {
        gint x, y, width, height;
        tk_get_extents(ATK_COMPONENT(acc), &x, &y, &width, &height, ATK_XY_SCREEN);
        return; /* Geometry alone does not change visible/showing state. */
    }
    if (eventPtr->type == MapNotify || eventPtr->type == UnmapNotify) {
        MylTkAtkSyncActiveWindows();
        MylTkAtkSyncVisibility(ATK_OBJECT(acc));
    }''')
    source = replace_once(source, '''    if (acc->tkwin && Tk_IsMapped(acc->tkwin)) {
	atk_state_set_add_state(state_set, ATK_STATE_VISIBLE);
	atk_state_set_add_state(state_set, ATK_STATE_SHOWING);
    }''', '''    if (acc->tkwin && Tk_IsMapped(acc->tkwin))
        atk_state_set_add_state(state_set, ATK_STATE_VISIBLE);
    if (MylTkAtkShowing(acc->tkwin))
        atk_state_set_add_state(state_set, ATK_STATE_SHOWING);''')
    # All registration/ancestor/Init sites share transition-only state events.
    # The input is hash-locked; require the exact remaining notification count.
    pattern = (r'atk_object_notify_state_change\((ATK_OBJECT\(accessible\)|acc|pAcc|childAcc|top), '
               r'ATK_STATE_(?:VISIBLE|SHOWING), TRUE\);')
    source, count = re.subn(pattern, r'MylTkAtkSyncVisibility(\1);', source)
    if count != 11:
        raise ValueError('Unexpected pinned Tk visibility notification count: ' + str(count))
    source = re.sub(r'(MylTkAtkSyncVisibility\([^;]+\);)\n[ \t]*\1', r'\1', source)
    return source


def apply_linux_patch(tree: Path):
    unix = tree / 'unix'
    receipt = tree / RECEIPT
    recipe = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    helper = NATIVE / HELPER
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if (record.get('patch_id') != PATCH_ID or record.get('patcher_sha256') != recipe
                or record.get('input_hashes') != INPUT_HASHES
                or set(record.get('output_hashes', {})) != {*INPUT_HASHES, OUTPUT_HELPER}):
            raise ValueError('Different native Linux accessibility patch already applied')
        for name, expected in record['output_hashes'].items():
            if hashlib.sha256((unix / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Modified patched native Linux source: ' + name)
        if hashlib.sha256(helper.read_bytes()).hexdigest() != record['output_hashes'][OUTPUT_HELPER]:
            raise ValueError('Different native Linux accessibility helper')
        return record
    source = unix / 'tkUnixAccessibility.c'
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_HASHES[source.name]:
        raise ValueError('Unrecognized native Linux source: ' + source.name)
    repaired = repair_provider(raw.decode('utf-8'))
    # Verify every input/context/helper before modifying build-only sources.
    helper_bytes = helper.read_bytes()
    source.write_text(repaired, encoding='utf-8', newline='\n')
    (unix / OUTPUT_HELPER).write_bytes(helper_bytes)
    record = {'patch_id': PATCH_ID, 'input_hashes': dict(INPUT_HASHES),
              'output_hashes': {name: hashlib.sha256((unix / name).read_bytes()).hexdigest()
                                for name in (*INPUT_HASHES, OUTPUT_HELPER)},
              'patcher_sha256': recipe}
    receipt.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record
