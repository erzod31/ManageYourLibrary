/* Project-maintained Tk 9.1 ATK repair. Distributed under the project MIT
 * license. This is provider contract support, not reader certification.
 * Included after TkAtkAccessible and its type/prototypes are defined. */
#ifndef MYL_TK_UNIX_A11Y_WINDOW_H
#define MYL_TK_UNIX_A11Y_WINDOW_H

typedef struct { TkAtkAccessible parent_instance; } MylTkAtkWindow;
typedef struct { TkAtkAccessibleClass parent_class; } MylTkAtkWindowClass;

/* Only native toplevels implement AtkWindow. The application root and ordinary
 * controls must retain their ordinary accessible interfaces. AtkWindow owns
 * the standard create/activate/deactivate/destroy signals used by AT-SPI. */
G_DEFINE_TYPE_WITH_CODE(MylTkAtkWindow, myl_tk_atk_window,
        TK_ATK_TYPE_ACCESSIBLE, G_IMPLEMENT_INTERFACE(ATK_TYPE_WINDOW, NULL))
static void myl_tk_atk_window_class_init(MylTkAtkWindowClass *klass) { (void)klass; }
static void myl_tk_atk_window_init(MylTkAtkWindow *self) { (void)self; }

static void MylTkAtkSetWindowParent(AtkObject *obj)
{
    if (ATK_IS_WINDOW(obj) && tk_root_accessible && obj != tk_root_accessible)
        atk_object_set_parent(obj, tk_root_accessible);
}

/* The same privacy check guards every provider value path, including text
 * change notifications. A failed Entry -show query must not reveal content. */
static gchar *MylTkAtkQuery(Tk_Window window, const char *first, const char *second)
{
    Tcl_Interp *interp;
    Tcl_InterpState saved;
    Tcl_Obj *args[3];
    gchar *result = NULL;
    if (!window) return NULL;
    interp = Tk_Interp(window);
    if (!interp) return NULL;
    Tcl_Preserve(interp);
    saved = Tcl_SaveInterpState(interp, TCL_OK);
    args[0] = Tcl_NewStringObj(Tk_PathName(window), -1);
    args[1] = Tcl_NewStringObj(first, -1);
    args[2] = Tcl_NewStringObj(second, -1);
    for (int i = 0; i < 3; i++) Tcl_IncrRefCount(args[i]);
    if (Tcl_EvalObjv(interp, 3, args, TCL_EVAL_GLOBAL) == TCL_OK)
        result = g_strdup(Tcl_GetStringResult(interp));
    for (int i = 0; i < 3; i++) Tcl_DecrRefCount(args[i]);
    Tcl_RestoreInterpState(interp, saved);
    Tcl_Release(interp);
    return result;
}

static gboolean MylTkAtkValueAllowed(Tk_Window window)
{
    gchar *show;
    gboolean allowed;
    if (!window) return FALSE;
    if (GetAtkRoleForWidget(window) != ATK_ROLE_ENTRY) return TRUE;
    show = MylTkAtkQuery(window, "cget", "-show");
    allowed = show && !show[0];
    g_free(show);
    return allowed;
}

static gchar *MylTkAtkTextValue(AtkText *text)
{
    TkAtkAccessible *acc = (TkAtkAccessible *)text;
    AtkRole role;
    gchar *value;
    if (!acc || acc->is_defunct || !acc->tkwin) return g_strdup("");
    role = GetAtkRoleForWidget(acc->tkwin);
    if (role != ATK_ROLE_ENTRY && role != ATK_ROLE_TEXT) return g_strdup("");
    value = GetAtkValueForWidget(acc->tkwin);
    return value ? value : g_strdup("");
}

static gchar *MylTkAtkText(AtkText *text, gint start, gint end)
{
    gchar *value, *result;
    glong length;
    const gchar *first, *last;
    if (start < 0 || end < -1 || (end != -1 && end < start)) return NULL;
    value = MylTkAtkTextValue(text);
    if (!g_utf8_validate(value, -1, NULL)) { g_free(value); return g_strdup(""); }
    length = MIN(g_utf8_strlen(value, -1), G_MAXINT);
    if (start >= length) { g_free(value); return g_strdup(""); }
    if (end == -1 || end > length) end = (gint)length;
    first = g_utf8_offset_to_pointer(value, start);
    last = g_utf8_offset_to_pointer(value, end);
    result = g_strndup(first, last - first);
    g_free(value);
    return result;
}

static gint MylTkAtkTextCount(AtkText *text)
{
    gchar *value = MylTkAtkTextValue(text);
    gint count = g_utf8_validate(value, -1, NULL)
            ? (gint)MIN(g_utf8_strlen(value, -1), G_MAXINT) : 0;
    g_free(value);
    return count;
}

static gchar *MylTkAtkTextAtOffset(AtkText *text, gint offset,
        AtkTextBoundary boundary, gint *start, gint *end)
{
    gchar *value = MylTkAtkTextValue(text), *result = NULL;
    const gchar *point, *first, *last, *cursor;
    glong length;
    if (start) *start = -1;
    if (end) *end = -1;
    if (!g_utf8_validate(value, -1, NULL)) goto done;
    length = MIN(g_utf8_strlen(value, -1), G_MAXINT);
    if (offset < 0 || offset > length) goto done;
    point = g_utf8_offset_to_pointer(value, offset);
    if (boundary == ATK_TEXT_BOUNDARY_CHAR) {
        first = point;
        last = offset < length ? g_utf8_next_char(point) : point;
    } else if (boundary == ATK_TEXT_BOUNDARY_LINE_START) {
        first = value;
        for (cursor = value; cursor < point; cursor = g_utf8_next_char(cursor))
            if (*cursor == '\n') first = cursor + 1;
        last = strchr(point, '\n');
        last = last ? last + 1 : value + strlen(value);
    } else goto done; /* Unsupported boundaries stay explicitly unavailable. */
    if (start) *start = (gint)g_utf8_pointer_to_offset(value, first);
    if (end) *end = (gint)g_utf8_pointer_to_offset(value, last);
    result = g_strndup(first, last - first);
done:
    g_free(value);
    return result;
}

static gint MylTkAtkTextCaret(AtkText *text)
{
    TkAtkAccessible *acc = (TkAtkAccessible *)text;
    gchar *value, *index;
    gint offset = -1, line, column;
    char extra;
    const gchar *point, *last;
    AtkRole role;
    if (!acc || acc->is_defunct || !acc->tkwin
            || TkGetFocusWin((TkWindow *)acc->tkwin) != (TkWindow *)acc->tkwin
            || !MylTkAtkValueAllowed(acc->tkwin)) return -1;
    role = GetAtkRoleForWidget(acc->tkwin);
    if (role != ATK_ROLE_ENTRY && role != ATK_ROLE_TEXT) return -1;
    index = MylTkAtkQuery(acc->tkwin, "index", "insert");
    if (!index) return -1;
    value = MylTkAtkTextValue(text);
    if (role == ATK_ROLE_ENTRY) {
        if (Tcl_GetInt(NULL, index, &offset) != TCL_OK) offset = -1;
    } else if (sscanf(index, "%d.%d%c", &line, &column, &extra) == 2 && line > 0 && column >= 0) {
        point = value;
        while (--line > 0 && (point = strchr(point, '\n')) != NULL) point++;
        if (point) {
            last = strchr(point, '\n');
            if (!last) last = value + strlen(value);
            if (column <= g_utf8_pointer_to_offset(point, last))
                offset = (gint)g_utf8_pointer_to_offset(value, point) + column;
        }
    }
    if (offset < 0 || offset > (gint)MIN(g_utf8_strlen(value, -1), G_MAXINT)) offset = -1;
    g_free(value);
    g_free(index);
    return offset;
}

static gboolean MylTkAtkWindowActive(Tk_Window window)
{
    TkWindow *focused;
    if (!window || !Tk_IsTopLevel(window) || !Tk_IsMapped(window)) return FALSE;
    focused = TkGetFocusWin((TkWindow *)window);
    return focused && GetToplevelOfWidget((Tk_Window)focused) == window;
}

static gint MylTkAtkIndexInParent(AtkObject *obj)
{
    TkAtkAccessible *acc = (TkAtkAccessible *)obj;
    Tk_Window parent;
    TkWindow *child;
    gint index = 0;
    if (!acc || !acc->tkwin || acc->is_defunct) return -1;
    if (Tk_IsTopLevel(acc->tkwin)) return g_list_index(toplevel_accessible_objects, obj);
    parent = Tk_Parent(acc->tkwin);
    if (!parent) return -1;
    for (child = ((TkWindow *)parent)->childList; child; child = child->nextPtr) {
        if (Tk_IsTopLevel((Tk_Window)child)) continue;
        if ((Tk_Window)child == acc->tkwin) return index;
        index++;
    }
    return -1;
}

static void MylTkAtkSyncActiveWindows(void)
{
    GList *item;
    for (item = toplevel_accessible_objects; item; item = item->next) {
        TkAtkAccessible *acc = (TkAtkAccessible *)item->data;
        gboolean active = !acc->is_defunct && MylTkAtkWindowActive(acc->tkwin);
        if (active != acc->is_active) {
            acc->is_active = active;
            atk_object_notify_state_change(ATK_OBJECT(acc), ATK_STATE_ACTIVE, active);
            if (ATK_IS_WINDOW(acc))
                g_signal_emit_by_name(acc, active ? "activate" : "deactivate");
        }
    }
}

/* DestroyNotify invalidates Tk pointers, not the still-exported GObject.
 * AT-SPI clients can retain a reference and must receive a DEFUNCT object
 * instead of touching a freed Tk_Window or a manually finalized GObject. */
static void MylTkAtkDetach(TkAtkAccessible *acc)
{
    Tk_Window window;
    AtkObject *obj;
    if (!acc || acc->is_defunct || !acc->tkwin) return;
    obj = ATK_OBJECT(acc);
    g_object_ref(obj);
    window = acc->tkwin;
    Tk_DeleteEventHandler(window, StructureNotifyMask, TkAtkAccessible_DestroyHandler, acc);
    Tk_DeleteEventHandler(window, FocusChangeMask, TkAtkAccessible_FocusHandler, acc);
    Tk_DeleteEventHandler(window, SubstructureNotifyMask, TkAtkAccessible_CreateHandler, acc);
    Tk_DeleteEventHandler(window, StructureNotifyMask, TkAtkAccessible_ConfigureHandler, acc);
    if (ATK_IS_WINDOW(obj)) {
        if (acc->is_active) g_signal_emit_by_name(obj, "deactivate");
        g_signal_emit_by_name(obj, "destroy");
    }
    UnregisterAtkObjectForTkWindow(window);
    acc->tkwin = NULL;
    acc->interp = NULL;
    acc->is_focused = false;
    acc->is_active = false;
    acc->is_defunct = true;
    atk_object_set_parent(obj, NULL);
    atk_object_notify_state_change(obj, ATK_STATE_FOCUSED, FALSE);
    atk_object_notify_state_change(obj, ATK_STATE_ACTIVE, FALSE);
    atk_object_notify_state_change(obj, ATK_STATE_SHOWING, FALSE);
    atk_object_notify_state_change(obj, ATK_STATE_DEFUNCT, TRUE);
    g_object_unref(obj);
}
#endif
