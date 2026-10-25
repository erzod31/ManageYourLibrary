/* Read-only provider contract diagnostics on this process's Tk window only.
 * This is not an external assistive client or a speech test. MIT.
 */
typedef struct {
    LONG id, role, state;
    BSTR name, value;
    HRESULT childStatus;
} MylProbeChild;
typedef struct {
    IAccessible *provider;
    LONG declared;
    ULONG count;
    HRESULT status;
    MylProbeChild children[1024];
} MylProbeData;

static DWORD WINAPI
MylProbeWorker(void *data)
{
    MylProbeData *probe = (MylProbeData *)data;
    IAccessible *provider = probe->provider;
    IEnumVARIANT *enumerator = NULL;
    HRESULT status = provider->lpVtbl->get_accChildCount(provider, &probe->declared);
    if (FAILED(status)) { probe->status = status; return 0; }
    status = provider->lpVtbl->QueryInterface(provider, &IID_IEnumVARIANT, (void **)&enumerator);
    if (FAILED(status)) { probe->status = status; return 0; }
    while (probe->count < 1024) {
        VARIANT child, role, state;
        ULONG fetched = 0;
        IDispatch *object = NULL;
        MylProbeChild *result = probe->children + probe->count;
        VariantInit(&child); VariantInit(&role); VariantInit(&state);
        status = enumerator->lpVtbl->Next(enumerator, 1, &child, &fetched);
        if (status == S_FALSE && !fetched) break;
        if (FAILED(status) || child.vt != VT_I4) { probe->status = E_FAIL; break; }
        result->id = child.lVal;
        provider->lpVtbl->get_accName(provider, child, &result->name);
        provider->lpVtbl->get_accValue(provider, child, &result->value);
        provider->lpVtbl->get_accRole(provider, child, &role);
        provider->lpVtbl->get_accState(provider, child, &state);
        result->role = role.vt == VT_I4 ? role.lVal : -1;
        result->state = state.vt == VT_I4 ? state.lVal : -1;
        result->childStatus = provider->lpVtbl->get_accChild(provider, child, &object);
        if (object) object->lpVtbl->Release(object);
        probe->count++;
    }
    enumerator->lpVtbl->Release(enumerator);
    return 0;
}

static Tcl_Obj *
MylProbeString(BSTR string)
{
    Tcl_DString text;
    Tcl_Obj *result;
    if (!string) return Tcl_NewStringObj("", 0);
    Tcl_DStringInit(&text);
    result = Tcl_NewStringObj(Tcl_WCharToUtfDString(string, SysStringLen(string), &text), -1);
    Tcl_DStringFree(&text);
    return result;
}

static int
MylProviderProbe(void *unused, Tcl_Interp *interp, Tcl_Size objc, Tcl_Obj *const *objv)
{
    Tk_Window window;
    TkRootAccessible *provider;
    MylProbeData *probe;
    HANDLE thread;
    Tcl_Obj *result, *children;
    (void)unused;
    if (objc != 2) { Tcl_WrongNumArgs(interp, 1, objv, "toplevel"); return TCL_ERROR; }
    window = Tk_NameToWindow(interp, Tcl_GetString(objv[1]), Tk_MainWindow(interp));
    provider = window ? GetTkAccessibleForWindow(window) : NULL;
    if (!provider) { Tcl_SetObjResult(interp, Tcl_NewStringObj("No registered provider", -1)); return TCL_ERROR; }
    probe = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*probe));
    if (!probe) return TCL_ERROR;
    probe->provider = (IAccessible *)provider;
    TkRootAccessible_AddRef(probe->provider);
    thread = CreateThread(NULL, 0, MylProbeWorker, probe, 0, NULL);
    if (!thread) { TkRootAccessible_Release(probe->provider); HeapFree(GetProcessHeap(), 0, probe); return TCL_ERROR; }
    /* The test process has an outer deadline; only its own Tk event loop is
     * serviced here. No keyboard/mouse injection or other window is queried. */
    while (WaitForSingleObject(thread, 0) == WAIT_TIMEOUT) {
        if (!Tcl_DoOneEvent(TCL_ALL_EVENTS | TCL_DONT_WAIT)) Sleep(1);
    }
    CloseHandle(thread);
    TkRootAccessible_Release(probe->provider);
    result = Tcl_NewDictObj();
    children = Tcl_NewListObj(0, NULL);
    Tcl_DictObjPut(interp, result, Tcl_NewStringObj("declared", -1), Tcl_NewLongObj(probe->declared));
    Tcl_DictObjPut(interp, result, Tcl_NewStringObj("status", -1), Tcl_NewWideIntObj(probe->status));
    for (ULONG i = 0; i < probe->count; i++) {
        MylProbeChild *item = probe->children + i;
        Tcl_Obj *row = Tcl_NewListObj(0, NULL);
        Tcl_ListObjAppendElement(interp, row, Tcl_NewLongObj(item->id));
        Tcl_ListObjAppendElement(interp, row, MylProbeString(item->name));
        Tcl_ListObjAppendElement(interp, row, MylProbeString(item->value));
        Tcl_ListObjAppendElement(interp, row, Tcl_NewLongObj(item->role));
        Tcl_ListObjAppendElement(interp, row, Tcl_NewLongObj(item->state));
        Tcl_ListObjAppendElement(interp, row, Tcl_NewLongObj(item->childStatus));
        Tcl_ListObjAppendElement(interp, children, row);
        SysFreeString(item->name); SysFreeString(item->value);
    }
    Tcl_DictObjPut(interp, result, Tcl_NewStringObj("children", -1), children);
    HeapFree(GetProcessHeap(), 0, probe);
    Tcl_SetObjResult(interp, result);
    return TCL_OK;
}

static int
MylPatchVersion(void *unused, Tcl_Interp *interp, Tcl_Size objc, Tcl_Obj *const *objv)
{
    (void)unused;
    if (objc != 1) { Tcl_WrongNumArgs(interp, 1, objv, ""); return TCL_ERROR; }
    Tcl_SetObjResult(interp, Tcl_NewStringObj("myl-tk91-win-msaa-1", -1));
    return TCL_OK;
}
