/* Stable MSAA simple-child IDs and per-query IEnumVARIANT snapshots.
 * ManageYourLibrary repair, MIT. All tree access runs on the Tk owner thread.
 */
typedef struct {
    IEnumVARIANTVtbl *lpVtbl;
    LONG references;
    CRITICAL_SECTION lock;
    ULONG count, position;
    LONG *ids;
    IAccessible *owner;
} MylAccessibleEnum;

static IEnumVARIANTVtbl MylEnumVtable;

static MylAccessibleEnum *
MylNewEnum(ULONG count, const LONG *ids, ULONG position, IAccessible *owner)
{
    MylAccessibleEnum *object = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*object));
    if (!object) return NULL;
    object->lpVtbl = &MylEnumVtable;
    object->references = 1;
    object->count = count;
    object->position = position;
    object->owner = owner;
    if (count) {
        object->ids = HeapAlloc(GetProcessHeap(), 0, sizeof(LONG) * count);
        if (!object->ids) { HeapFree(GetProcessHeap(), 0, object); return NULL; }
        memcpy(object->ids, ids, sizeof(LONG) * count);
    }
    InitializeCriticalSection(&object->lock);
    if (owner) owner->lpVtbl->AddRef(owner);
    return object;
}

static ULONG STDMETHODCALLTYPE MylEnumAddRef(IEnumVARIANT *self) {
    return InterlockedIncrement(&((MylAccessibleEnum *)self)->references);
}
static ULONG STDMETHODCALLTYPE MylEnumRelease(IEnumVARIANT *self) {
    MylAccessibleEnum *object = (MylAccessibleEnum *)self;
    ULONG count = InterlockedDecrement(&object->references);
    if (!count) {
        DeleteCriticalSection(&object->lock);
        if (object->ids) HeapFree(GetProcessHeap(), 0, object->ids);
        if (object->owner) object->owner->lpVtbl->Release(object->owner);
        HeapFree(GetProcessHeap(), 0, object);
    }
    return count;
}
static HRESULT STDMETHODCALLTYPE MylEnumQuery(IEnumVARIANT *self, REFIID iid, void **result) {
    if (!result) return E_INVALIDARG;
    *result = NULL;
    if (!IsEqualIID(iid, &IID_IEnumVARIANT)) {
        MylAccessibleEnum *object = (MylAccessibleEnum *)self;
        if (object->owner) return object->owner->lpVtbl->QueryInterface(object->owner, iid, result);
        if (!IsEqualIID(iid, &IID_IUnknown)) return E_NOINTERFACE;
    }
    *result = self; MylEnumAddRef(self); return S_OK;
}
static HRESULT STDMETHODCALLTYPE MylEnumNext(IEnumVARIANT *self, ULONG count, VARIANT *values, ULONG *fetched) {
    MylAccessibleEnum *object = (MylAccessibleEnum *)self;
    ULONG copied = 0;
    if (fetched) *fetched = 0;
    if (!values || (!fetched && count != 1)) return E_INVALIDARG;
    EnterCriticalSection(&object->lock);
    while (copied < count && object->position < object->count) {
        VariantInit(values + copied);
        values[copied].vt = VT_I4;
        values[copied++].lVal = object->ids[object->position++];
    }
    LeaveCriticalSection(&object->lock);
    if (fetched) *fetched = copied;
    return copied == count ? S_OK : S_FALSE;
}
static HRESULT STDMETHODCALLTYPE MylEnumSkip(IEnumVARIANT *self, ULONG count) {
    MylAccessibleEnum *object = (MylAccessibleEnum *)self;
    ULONG skipped;
    EnterCriticalSection(&object->lock);
    skipped = min(count, object->count - object->position);
    object->position += skipped;
    LeaveCriticalSection(&object->lock);
    return skipped == count ? S_OK : S_FALSE;
}
static HRESULT STDMETHODCALLTYPE MylEnumReset(IEnumVARIANT *self) {
    MylAccessibleEnum *object = (MylAccessibleEnum *)self;
    EnterCriticalSection(&object->lock); object->position = 0; LeaveCriticalSection(&object->lock);
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE MylEnumClone(IEnumVARIANT *self, IEnumVARIANT **result) {
    MylAccessibleEnum *object = (MylAccessibleEnum *)self;
    if (!result) return E_INVALIDARG;
    EnterCriticalSection(&object->lock);
    *result = (IEnumVARIANT *)MylNewEnum(object->count, object->ids, object->position, object->owner);
    LeaveCriticalSection(&object->lock);
    return *result ? S_OK : E_OUTOFMEMORY;
}
static IEnumVARIANTVtbl MylEnumVtable = {
    MylEnumQuery, MylEnumAddRef, MylEnumRelease, MylEnumNext,
    MylEnumSkip, MylEnumReset, MylEnumClone
};

#ifndef MYL_ENUM_ONLY

static int
MylWindowVisible(Tk_Window win, Tk_Window toplevel)
{
    while (win) {
        if (!Tk_IsMapped(win) || (((TkWindow *)win)->flags & TK_ALREADY_DEAD)) return 0;
        if (win == toplevel) return 1;
        if (Tk_IsTopLevel(win)) return 0;
        win = Tk_Parent(win);
    }
    return 0;
}

typedef struct { Tk_Window win, toplevel; } MylChildIdentity;
static void
MylChildDestroyed(void *data, XEvent *event)
{
    MylChildIdentity *identity = (MylChildIdentity *)data;
    Tcl_HashEntry *entry;
    Tcl_HashTable *table;
    if (event->type != DestroyNotify) return;
    entry = toplevelChildTables ? Tcl_FindHashEntry(toplevelChildTables, identity->toplevel) : NULL;
    if (entry) {
        table = (Tcl_HashTable *)Tcl_GetHashValue(entry);
        entry = Tcl_FindHashEntry(table, identity->win);
        if (entry) Tcl_DeleteHashEntry(entry);
    }
    Tcl_Free(identity);
}

static void
MylCollectVisibleIds(Tk_Window win, Tk_Window toplevel, LONG *ids, ULONG capacity, ULONG *count)
{
    TkWindow *child;
    int id;
    if (!win || !Tk_IsMapped(win) || (win != toplevel && Tk_IsTopLevel(win))) return;
    id = GetChildIdForTkWindow(win, GetChildIdTableForToplevel(toplevel));
    if (id > 0 && *count < capacity) ids[(*count)++] = id;
    for (child = ((TkWindow *)win)->childList; child; child = child->nextPtr) {
        MylCollectVisibleIds((Tk_Window)child, toplevel, ids, capacity, count);
    }
}

typedef struct { TkRootAccessible *provider; IEnumVARIANT *result; HRESULT status; } MylEnumCall;
static void
MylCreateEnumOnTkThread(int count, void **args)
{
    MylEnumCall *call = (MylEnumCall *)args[0];
    Tk_Window toplevel = call->provider->toplevel;
    LONG *ids;
    ULONG copied = 0;
    int children;
    (void)count;
    if (!toplevel) { call->status = RPC_E_DISCONNECTED; return; }
    children = TkAccChildCount(toplevel);
    ids = children ? HeapAlloc(GetProcessHeap(), 0, children * sizeof(LONG)) : NULL;
    if (children && !ids) { call->status = E_OUTOFMEMORY; return; }
    MylCollectVisibleIds(toplevel, toplevel, ids, children, &copied);
    call->result = (IEnumVARIANT *)MylNewEnum(copied, ids, 0, (IAccessible *)call->provider);
    if (ids) HeapFree(GetProcessHeap(), 0, ids);
    call->status = call->result ? S_OK : E_OUTOFMEMORY;
}

static HRESULT
MylQueryEnum(IAccessible *self, void **result)
{
    MylEnumCall call = { (TkRootAccessible *)self, NULL, RPC_E_DISCONNECTED };
    void *args[1] = { &call };
    *result = NULL;
    if (!MylDispatch(MylCreateEnumOnTkThread, 1, args)) return RPC_E_TIMEOUT;
    *result = call.result;
    return call.status;
}
#endif
