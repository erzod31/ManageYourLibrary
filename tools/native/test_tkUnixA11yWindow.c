/* Actual ATK/GObject contract regression for the project helper. Only Tk's
 * window model is stubbed; no display, reader, sound, or desktop is started. */
#define ATK_DISABLE_DEPRECATION_WARNINGS
#include <atk/atk.h>
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { const char *show, *index; gchar *result; int status, preserved; } Tcl_Interp;
typedef gchar *Tcl_InterpState;
typedef struct { gchar *value; int refs; } Tcl_Obj;
#define TCL_OK 0
#define TCL_EVAL_GLOBAL 1
static void Tcl_Preserve(Tcl_Interp *i) { i->preserved++; }
static void Tcl_Release(Tcl_Interp *i) { assert(--i->preserved >= 0); }
static Tcl_InterpState Tcl_SaveInterpState(Tcl_Interp *i, int status)
{ (void)status; return g_strdup(i->result); }
static void Tcl_RestoreInterpState(Tcl_Interp *i, Tcl_InterpState state)
{ g_free(i->result); i->result = state; }
static Tcl_Obj *Tcl_NewStringObj(const char *value, int count)
{
    (void)count;
    Tcl_Obj *obj = g_new0(Tcl_Obj, 1);
    obj->value = g_strdup(value);
    return obj;
}
static void Tcl_IncrRefCount(Tcl_Obj *obj) { obj->refs++; }
static void Tcl_DecrRefCount(Tcl_Obj *obj)
{ if (!--obj->refs) { g_free(obj->value); g_free(obj); } }
static const char *Tcl_GetStringResult(Tcl_Interp *i) { return i->result; }
static int Tcl_EvalObjv(Tcl_Interp *i, int count, Tcl_Obj **args, int flags)
{
    assert(count == 3 && flags == TCL_EVAL_GLOBAL);
    const char *result;
    if (!strcmp(args[1]->value, "cget")) {
        assert(!strcmp(args[2]->value, "-show")); result = i->show;
    } else {
        assert(!strcmp(args[1]->value, "index") && !strcmp(args[2]->value, "insert"));
        result = i->index;
    }
    g_free(i->result); i->result = g_strdup(result ? result : "");
    return i->status;
}
static int Tcl_GetInt(Tcl_Interp *i, const char *value, int *result)
{
    char *last;
    (void)i;
    long parsed = strtol(value, &last, 10);
    if (!value[0] || last[0] || parsed < G_MININT || parsed > G_MAXINT) return 1;
    *result = (int)parsed; return TCL_OK;
}

typedef struct TkWindow TkWindow;
typedef TkWindow *Tk_Window;
typedef struct { int unused; } XEvent;
struct TkWindow {
    int top, mapped, app;
    TkWindow *parent, *childList, *nextPtr;
    AtkRole role;
    const char *value;
    Tcl_Interp *interp;
};
static TkWindow *focus[3];
#define Tk_IsTopLevel(w) ((w)->top)
#define Tk_IsMapped(w) ((w)->mapped)
#define Tk_Parent(w) ((w)->parent)
#define Tk_Interp(w) ((w)->interp)
#define Tk_PathName(w) ((void)(w), ".synthetic")
#define StructureNotifyMask 1
#define FocusChangeMask 2
#define SubstructureNotifyMask 4
static TkWindow *TkGetFocusWin(TkWindow *w) { return focus[w->app]; }
static Tk_Window GetToplevelOfWidget(Tk_Window w)
{
    while (w && !w->top) w = w->parent;
    return w;
}
static AtkRole GetAtkRoleForWidget(Tk_Window w) { return w->role; }
static gchar *GetAtkValueForWidget(Tk_Window w);

typedef struct _TkAtkAccessible {
    AtkObject parent;
    Tk_Window tkwin;
    Tcl_Interp *interp;
    bool is_focused, is_active, is_defunct;
    bool visibility_known, is_visible, is_showing;
} TkAtkAccessible;
typedef struct _TkAtkAccessibleClass { AtkObjectClass parent_class; } TkAtkAccessibleClass;
#define TK_ATK_TYPE_ACCESSIBLE (tk_atk_accessible_get_type())
static GList *toplevel_accessible_objects;
static AtkObject *tk_root_accessible;
static GHashTable *widget_map;
static int finalized, handlers_removed, active_signals, inactive_signals, defunct_signals;
static int visible_on, visible_off, showing_on, showing_off;
static AtkObject *GetAtkObjectForTkWindow(Tk_Window w)
{ return g_hash_table_lookup(widget_map, w); }
static void TkAtkAccessible_DestroyHandler(void *p, XEvent *e) { (void)p; (void)e; }
static void TkAtkAccessible_FocusHandler(void *p, XEvent *e) { (void)p; (void)e; }
static void TkAtkAccessible_CreateHandler(void *p, XEvent *e) { (void)p; (void)e; }
static void TkAtkAccessible_ConfigureHandler(void *p, XEvent *e) { (void)p; (void)e; }
static void Tk_DeleteEventHandler(Tk_Window w, int mask, void (*handler)(void *, XEvent *), void *data)
{
    assert(w != NULL && mask != 0 && handler != NULL && data != NULL);
    handlers_removed++;
}
static void UnregisterAtkObjectForTkWindow(Tk_Window w)
{
    AtkObject *obj = g_hash_table_lookup(widget_map, w);
    assert(obj != NULL);
    toplevel_accessible_objects = g_list_remove(toplevel_accessible_objects, obj);
    assert(g_hash_table_remove(widget_map, w));
}
static void text_iface_init(AtkTextIface *iface);
G_DEFINE_TYPE_WITH_CODE(TkAtkAccessible, tk_atk_accessible, ATK_TYPE_OBJECT,
        G_IMPLEMENT_INTERFACE(ATK_TYPE_TEXT, text_iface_init))
static void test_finalize(GObject *obj)
{
    finalized++;
    G_OBJECT_CLASS(tk_atk_accessible_parent_class)->finalize(obj);
}
static void tk_atk_accessible_class_init(TkAtkAccessibleClass *klass)
{
    G_OBJECT_CLASS(klass)->finalize = test_finalize;
}
static void tk_atk_accessible_init(TkAtkAccessible *self) { (void)self; }

#include "tkUnixA11yWindow.h"

static gchar *GetAtkValueForWidget(Tk_Window w)
{
    if (!MylTkAtkValueAllowed(w)) return g_strdup("");
    return w->value ? g_utf8_make_valid(w->value, -1) : NULL;
}
static void text_iface_init(AtkTextIface *iface)
{
    iface->get_text = MylTkAtkText;
    iface->get_character_count = MylTkAtkTextCount;
    iface->get_text_at_offset = MylTkAtkTextAtOffset;
    iface->get_caret_offset = MylTkAtkTextCaret;
}

static TkAtkAccessible *provider(Tk_Window w)
{
    TkAtkAccessible *acc = g_object_new(w && w->top ? myl_tk_atk_window_get_type()
                                                   : TK_ATK_TYPE_ACCESSIBLE, NULL);
    acc->tkwin = w;
    acc->interp = w ? w->interp : NULL;
    if (w) {
        g_hash_table_insert(widget_map, w, g_object_ref(acc));
        if (w->top) toplevel_accessible_objects = g_list_append(toplevel_accessible_objects, acc);
    }
    MylTkAtkSyncVisibility(ATK_OBJECT(acc)); /* Same unconditional creation baseline as provider. */
    return acc; /* Caller owns constructor reference, unlike build-only map API. */
}
static void activated(AtkWindow *obj, void *data)
{ (void)obj; (void)data; active_signals++; }
static void deactivated(AtkWindow *obj, void *data)
{ (void)obj; (void)data; inactive_signals++; }
static void state_changed(AtkObject *obj, const char *state, gboolean enabled, void *data)
{
    (void)obj; (void)data;
    if (g_strcmp0(state, "defunct") == 0 && enabled) defunct_signals++;
    if (g_strcmp0(state, "visible") == 0) { if (enabled) visible_on++; else visible_off++; }
    if (g_strcmp0(state, "showing") == 0) { if (enabled) showing_on++; else showing_off++; }
}
static void count_visibility(AtkObject *obj, const char *state, gboolean enabled, void *data)
{
    (void)obj; (void)enabled;
    if (!strcmp(state, "visible") || !strcmp(state, "showing")) (*(int *)data)++;
}

int main(void)
{
    Tcl_Interp entry_interp = {.show="", .index="3", .result=g_strdup("unchanged Entry result")};
    Tcl_Interp text_interp = {.index="2.1", .result=g_strdup("unchanged Text result")};
    const char *unicode = "A" "\xC3\xA9" "\xE4\xB9\xA6" "\xF0\x9F\x93\x9A" "Z";
    TkWindow main = {.top=1, .mapped=1, .app=1};
    TkWindow dialog = {.top=1, .mapped=1, .app=1, .parent=&main};
    TkWindow first = {.mapped=1, .app=1, .parent=&main, .nextPtr=&dialog,
                      .role=ATK_ROLE_ENTRY, .value=unicode, .interp=&entry_interp};
    TkWindow second = {.mapped=0, .app=1, .parent=&main, .role=ATK_ROLE_TEXT,
                       .value="A\n\xC3\xA9\xE4\xB9\xA6\nZ", .interp=&text_interp};
    TkWindow dialog_entry = {.mapped=1, .app=1, .parent=&dialog};
    TkWindow other_app = {.top=1, .mapped=1, .app=2};
    TkWindow other_entry = {.mapped=1, .app=2, .parent=&other_app};
    main.childList = &first;
    dialog.nextPtr = &second;
    dialog.childList = &dialog_entry;
    widget_map = g_hash_table_new_full(g_direct_hash, g_direct_equal, NULL, g_object_unref);
    TkAtkAccessible *app = provider(NULL);
    tk_root_accessible = ATK_OBJECT(app);
    TkAtkAccessible *a = provider(&main), *b = provider(&dialog);
    TkAtkAccessible *one = provider(&first), *two = provider(&second);
    assert(!ATK_IS_WINDOW(app) && !ATK_IS_WINDOW(one));
    assert(ATK_IS_WINDOW(a) && ATK_IS_WINDOW(b));
    MylTkAtkSetWindowParent(ATK_OBJECT(a));
    MylTkAtkSetWindowParent(ATK_OBJECT(b));
    assert(atk_object_get_parent(ATK_OBJECT(a)) == tk_root_accessible);
    assert(atk_object_get_parent(ATK_OBJECT(b)) == tk_root_accessible);
    assert(g_signal_lookup("activate", myl_tk_atk_window_get_type()) != 0);
    assert(MylTkAtkIndexInParent(ATK_OBJECT(a)) == 0);
    assert(MylTkAtkIndexInParent(ATK_OBJECT(b)) == 1);
    assert(MylTkAtkIndexInParent(ATK_OBJECT(one)) == 0);
    assert(MylTkAtkIndexInParent(ATK_OBJECT(two)) == 1);
    assert(MylTkAtkIndexInParent(ATK_OBJECT(app)) == -1);
    int map_events = 0;
    g_signal_connect(two, "state-change", G_CALLBACK(count_visibility), &map_events);
    assert(two->visibility_known && !two->is_visible && !two->is_showing);
    second.mapped = 1;
    MylTkAtkSyncVisibility(ATK_OBJECT(two));
    assert(two->is_visible && two->is_showing && map_events == 2);
    MylTkAtkSyncVisibility(ATK_OBJECT(two));
    assert(map_events == 2); /* Unmapped registration preserves the first real Map. */
    g_signal_connect(one, "state-change", G_CALLBACK(state_changed), NULL);
    assert(one->visibility_known && one->is_visible && one->is_showing);
    MylTkAtkSyncVisibility(ATK_OBJECT(one));
    assert(!visible_on && !showing_on && !visible_off && !showing_off);
    main.mapped = 0;
    MylTkAtkSyncVisibility(ATK_OBJECT(one));
    assert(one->visibility_known && one->is_visible && !one->is_showing);
    assert(!visible_on && !showing_on && showing_off == 1); /* Only real parent Hide. */
    main.mapped = 1;
    MylTkAtkSyncVisibility(ATK_OBJECT(a));
    assert(one->is_showing && showing_on == 1);
    for (int repeat = 0; repeat < 32; repeat++) MylTkAtkSyncVisibility(ATK_OBJECT(a));
    assert(!visible_on && showing_on == 1 && !visible_off && showing_off == 1);
    main.mapped = 0;
    MylTkAtkSyncVisibility(ATK_OBJECT(a));
    assert(one->is_visible && !one->is_showing && showing_off == 2 && !visible_off);
    MylTkAtkSyncVisibility(ATK_OBJECT(a));
    assert(showing_off == 2); /* Repeated Unmap/registration does not emit twice. */
    main.mapped = 1;
    MylTkAtkSyncVisibility(ATK_OBJECT(a));
    assert(one->is_showing && showing_on == 2);
    first.mapped = 0;
    MylTkAtkSyncVisibility(ATK_OBJECT(one));
    assert(!one->is_visible && !one->is_showing && visible_off == 1 && showing_off == 3);
    MylTkAtkSyncVisibility(ATK_OBJECT(one));
    assert(visible_off == 1 && showing_off == 3);
    first.mapped = 1;
    MylTkAtkSyncVisibility(ATK_OBJECT(one));
    assert(visible_on == 1 && showing_on == 3);
    g_signal_connect(a, "activate", G_CALLBACK(activated), NULL);
    g_signal_connect(a, "deactivate", G_CALLBACK(deactivated), NULL);
    g_signal_connect(b, "activate", G_CALLBACK(activated), NULL);
    g_signal_connect(b, "deactivate", G_CALLBACK(deactivated), NULL);
    focus[1] = &first;
    focus[2] = &other_entry;
    assert(MylTkAtkWindowActive(&main));
    assert(!MylTkAtkWindowActive(&dialog) && !MylTkAtkWindowActive(&first));
    gchar *selected = atk_text_get_text(ATK_TEXT(one), 0, -1);
    assert(!strcmp(selected, unicode)); g_free(selected);
    assert(atk_text_get_character_count(ATK_TEXT(one)) == 5);
    assert(atk_text_get_caret_offset(ATK_TEXT(one)) == 3);
    selected = atk_text_get_text(ATK_TEXT(one), 1, 4);
    assert(!strcmp(selected, "\xC3\xA9\xE4\xB9\xA6\xF0\x9F\x93\x9A")); g_free(selected);
    assert(atk_text_get_text(ATK_TEXT(one), -1, 3) == NULL);
    assert(atk_text_get_text(ATK_TEXT(one), 3, 1) == NULL);
    selected = atk_text_get_text(ATK_TEXT(one), 50, -1);
    assert(selected && !selected[0]); g_free(selected);
    gint start, end;
    selected = atk_text_get_text_at_offset(ATK_TEXT(one), 3, ATK_TEXT_BOUNDARY_LINE_START, &start, &end);
    assert(!strcmp(selected, unicode) && start == 0 && end == 5); g_free(selected);
    selected = atk_text_get_text_at_offset(ATK_TEXT(one), 3, ATK_TEXT_BOUNDARY_CHAR, &start, &end);
    assert(!strcmp(selected, "\xF0\x9F\x93\x9A") && start == 3 && end == 4); g_free(selected);
    assert(MylTkAtkTextAtOffset(ATK_TEXT(one), 99, ATK_TEXT_BOUNDARY_LINE_START, &start, &end) == NULL);
    assert(start == -1 && end == -1);
    selected = atk_text_get_text_at_offset(ATK_TEXT(two), 3, ATK_TEXT_BOUNDARY_LINE_START, &start, &end);
    assert(!strcmp(selected, "\xC3\xA9\xE4\xB9\xA6\n") && start == 2 && end == 5); g_free(selected);
    focus[1] = &second;
    assert(atk_text_get_caret_offset(ATK_TEXT(two)) == 3);
    focus[1] = &first;
    entry_interp.show = "*";
    selected = GetAtkValueForWidget(&first);
    assert(selected && !selected[0]); g_free(selected);
    selected = atk_text_get_text(ATK_TEXT(one), 0, -1);
    assert(selected && !selected[0]); g_free(selected);
    assert(atk_text_get_character_count(ATK_TEXT(one)) == 0);
    assert(atk_text_get_caret_offset(ATK_TEXT(one)) == -1);
    entry_interp.show = ""; entry_interp.status = 1;
    selected = atk_text_get_text(ATK_TEXT(one), 0, -1);
    assert(selected && !selected[0]); g_free(selected);
    entry_interp.status = TCL_OK;
    assert(!strcmp(entry_interp.result, "unchanged Entry result") && entry_interp.preserved == 0);
    assert(!strcmp(text_interp.result, "unchanged Text result") && text_interp.preserved == 0);
    MylTkAtkSyncActiveWindows();
    MylTkAtkSyncActiveWindows();
    assert(a->is_active && !b->is_active && active_signals == 1);
    focus[1] = &dialog_entry;
    assert(!MylTkAtkWindowActive(&main) && MylTkAtkWindowActive(&dialog));
    MylTkAtkSyncActiveWindows();
    assert(!a->is_active && b->is_active && active_signals == 2 && inactive_signals == 1);
    dialog.mapped = 0;
    assert(!MylTkAtkWindowActive(&dialog));
    MylTkAtkSyncActiveWindows();
    assert(!b->is_active && inactive_signals == 2);
    focus[1] = NULL;
    assert(!MylTkAtkWindowActive(&main)); /* Other app focus cannot activate us. */
    assert(!MylTkAtkWindowActive(NULL));

    /* Emulate a live external client after the Tk owner is destroyed. */
    GWeakRef weak;
    g_weak_ref_init(&weak, one);
    int old_finalized = finalized;
    MylTkAtkDetach(one);
    assert(finalized == old_finalized);
    assert(one->is_defunct && !one->tkwin && !one->interp);
    selected = atk_text_get_text(ATK_TEXT(one), 0, -1);
    assert(selected && !selected[0]); g_free(selected);
    assert(atk_text_get_character_count(ATK_TEXT(one)) == 0);
    assert(atk_text_get_caret_offset(ATK_TEXT(one)) == -1);
    assert(!one->is_active && !one->is_focused);
    assert(!g_hash_table_contains(widget_map, &first));
    assert(MylTkAtkIndexInParent(ATK_OBJECT(one)) == -1);
    assert(handlers_removed == 4 && defunct_signals == 1);
    MylTkAtkDetach(one); /* Idempotent, no second owner release. */
    assert(handlers_removed == 4 && defunct_signals == 1);
    g_object_unref(one); /* Client's final release now permits GObject finalize. */
    assert(finalized == old_finalized + 1);
    assert(g_weak_ref_get(&weak) == NULL);
    g_weak_ref_clear(&weak);
    MylTkAtkDetach(b);
    assert(g_list_index(toplevel_accessible_objects, b) == -1);
    assert(b->is_defunct && !b->tkwin);
    g_object_unref(b);
    MylTkAtkDetach(a);
    g_object_unref(a);
    MylTkAtkDetach(two);
    g_object_unref(two);
    g_object_unref(app);
    g_hash_table_destroy(widget_map);
    g_list_free(toplevel_accessible_objects);
    g_free(entry_interp.result);
    g_free(text_interp.result);
    puts("ATK window contract: passed");
    return 0;
}
