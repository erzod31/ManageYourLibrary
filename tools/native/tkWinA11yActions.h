/* ManageYourLibrary Windows accessibility repair, MIT (see LICENSE).
 * An asynchronous action belongs to one widget in one toplevel. Its destroy
 * handler invalidates the borrowed window before Tk frees it. The preserved
 * interpreter is released on execution, cancellation, and thread exit.
 */
static void
MylCancelAction(void *data, XEvent *event)
{
    if (event->type == DestroyNotify) {
        ((ActionEvent *)data)->win = NULL;
    }
}

static void
MylReleaseAction(ActionEvent *event)
{
    if (event->win) {
        Tk_DeleteEventHandler(event->win, StructureNotifyMask,
                MylCancelAction, event);
    }
    Tcl_Release(event->interp);
}

static int
MylDeleteActionEvent(Tcl_Event *ev, void *unused)
{
    (void)unused;
    if (ev->proc != ActionEventProc) return 0;
    MylReleaseAction((ActionEvent *)ev);
    return 1;
}

static Tcl_Obj *
MylActionForWindow(Tk_Window win)
{
    Tcl_HashEntry *entry;
    Tcl_HashTable *attributes;
    Tcl_Obj *action;
    if (!win || !MylWindowVisible(win, GetToplevelOfWidget(win))) return NULL;
    entry = Tcl_FindHashEntry(TkAccessibilityObject, win);
    if (!entry) return NULL;
    attributes = (Tcl_HashTable *)Tcl_GetHashValue(entry);
    entry = Tcl_FindHashEntry(attributes, "state");
    if (entry && strcmp(Tcl_GetString(Tcl_GetHashValue(entry)), "disabled") == 0) {
        return NULL;
    }
    entry = Tcl_FindHashEntry(attributes, "action");
    if (!entry) return NULL;
    action = (Tcl_Obj *)Tcl_GetHashValue(entry);
    return Tcl_GetCharLength(action) ? action : NULL;
}

static int
MylPerformAction(ActionEvent *event)
{
    Tcl_Interp *interp = event->interp;
    Tcl_Obj *action = !Tcl_InterpDeleted(interp)
            ? MylActionForWindow(event->win) : NULL;
    if (action) {
        Tcl_InterpState saved = Tcl_SaveInterpState(interp, TCL_OK);
        int result;
        Tcl_IncrRefCount(action);
        /* No window pointer is used after evaluation (it may destroy it). */
        result = Tcl_EvalObjEx(interp, action, TCL_EVAL_GLOBAL);
        if (result != TCL_OK) Tcl_BackgroundException(interp, result);
        Tcl_DecrRefCount(action);
        Tcl_RestoreInterpState(interp, saved);
    }
    MylReleaseAction(event);
    return 1; /* The Tcl queue, not this callback, frees event. */
}
