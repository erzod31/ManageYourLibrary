"""Fail-closed repair of the pinned Tk 9.1 Windows MSAA provider.

This is a project-maintained patch, not an upstream fix or accessibility
certification. Original archives remain unchanged and retained in provenance.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

PATCH_ID = 'myl-tk91-win-msaa-1'
INPUT_HASHES = {
    'tkWinAccessibility.c': 'a81918f91245de9d1c5f74efe722e40ae4cfb83e49481412377ce5b7b7b3a91e',
    'tkWinWm.c': 'fc5762ceab5aadbfb6229684d20b3d26adeb3d61374aa44595eafe9c34783723',
}
NATIVE = Path(__file__).parent / 'native'


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('Pinned Tk patch context mismatch: ' + before[:65])
    return source.replace(before, after, 1)


def replace_function(source, name, body):
    # Only known, brace-balanced function bodies in the hash-locked input.
    match = re.search(r'^(?:(?:static )?(?:void|int|HRESULT) )?' + re.escape(name)
                      + r'\([^;]*?^\{\n.*?^\}', source, re.M | re.S)
    if not match:
        raise ValueError('Missing pinned Tk function: ' + name)
    signature = match[0].split('{', 1)[0]
    return source[:match.start()] + signature + '{\n' + body.strip() + '\n}' + source[match.end():]


# COM calls may arrive on RPC threads: a lock alone does not make Tcl thread
# safe. Keep all Tk access on its owner thread, with caller-owned output slots
# live until the queued request completes (or is cancelled before starting).
METHODS = {
    'get_accName': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('BSTR *', 'name')],
    'get_accRole': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('VARIANT *', 'role')],
    'get_accState': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('VARIANT *', 'state')],
    'get_accValue': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('BSTR *', 'value')],
    'get_accParent': [('IAccessible *', 'self'), ('IDispatch **', 'parent')],
    'get_accChildCount': [('IAccessible *', 'self'), ('LONG *', 'count')],
    'get_accChild': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('IDispatch **', 'result')],
    'accLocation': [('IAccessible *', 'self'), ('LONG *', 'left'), ('LONG *', 'top'),
                    ('LONG *', 'width'), ('LONG *', 'height'), ('VARIANT', 'child')],
    'get_accDefaultAction': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('BSTR *', 'action')],
    'accDoDefaultAction': [('IAccessible *', 'self'), ('VARIANT', 'child')],
    'get_accHelp': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('BSTR *', 'help')],
    'get_accDescription': [('IAccessible *', 'self'), ('VARIANT', 'child'), ('BSTR *', 'description')],
    'get_accFocus': [('IAccessible *', 'self'), ('VARIANT *', 'focus')],
}


def marshal_methods(source):
    wrappers = []
    for method, arguments in METHODS.items():
        name = 'TkRootAccessible_' + method
        pattern = r'(static HRESULT STDMETHODCALLTYPE\s+)' + name + r'(\([^;]*?^\{)'
        source, count = re.subn(pattern, r'\1' + name + 'OnTkThread' + r'\2', source, count=1, flags=re.M | re.S)
        if count != 1:
            raise ValueError('Missing COM implementation: ' + name)
        fields = '; '.join(kind + ' ' + key for kind, key in arguments)
        declarations = ', '.join(kind + ' ' + key for kind, key in arguments)
        keys = ', '.join(key for _kind, key in arguments)
        passed = ', '.join('call->' + key for _kind, key in arguments)
        wrappers.append(f'''
typedef struct {{ {fields}; HRESULT status; }} MylCall_{method};
static void MylInvoke_{method}(int count, void **args) {{
    MylCall_{method} *call = (MylCall_{method} *)args[0];
    TkRootAccessible *provider = (TkRootAccessible *)call->self;
    Tcl_Interp *interp = provider->interp;
    Tcl_InterpState saved = interp ? Tcl_SaveInterpState(interp, TCL_OK) : NULL;
    (void)count;
    if (interp) Tcl_Preserve(interp);
    call->status = {name}OnTkThread({passed});
    if (interp) {{ Tcl_RestoreInterpState(interp, saved); Tcl_Release(interp); }}
}}
static HRESULT STDMETHODCALLTYPE {name}({declarations}) {{
    MylCall_{method} call = {{ {keys}, RPC_E_DISCONNECTED }};
    void *args[1] = {{ &call }};
    if (!self) return E_INVALIDARG;
    return MylDispatch(MylInvoke_{method}, 1, args) ? call.status : RPC_E_TIMEOUT;
}}
''')
    return source + '\n/* Owner-thread COM adapters: ' + PATCH_ID + ' */\n' + ''.join(wrappers)


def repair_provider(source):
    # Preserve this cleanup implementation for actual toplevel destruction.
    clear = re.search(r'^void ClearChildIdTableForToplevel\([^;]*?^\{.*?^\}', source, re.M | re.S)
    if not clear:
        raise ValueError('Missing native ID table cleanup')
    delete_ids = clear[0].replace('void ClearChildIdTableForToplevel', 'static void MylDeleteChildIds', 1)
    source = replace_once(source, '''typedef struct {
    Tcl_Event header;
    MainThreadFunc func;
    int num_args;
    void* args[6];
    HANDLE doneEvent;
} MainThreadSyncEvent;''', '/* Request/event ownership is defined in mylWinA11yDispatch.h. */')
    start = source.index('/* Event handler that executes on main thread. */')
    end = source.index('/* Initialize during Tcl startup. */', start)
    source = source[:start] + source[end:]
    source = replace_once(source, 'static volatile HRESULT mainThreadResult = E_FAIL;',
                          'static volatile HRESULT mainThreadResult = E_FAIL;\n'
                          '#define MYL_A11Y_ACTION_CLEANUP 1\n'
                          'static int MylDeleteActionEvent(Tcl_Event *, void *);\n'
                          '#include "mylWinA11yDispatch.h"')
    source = replace_once(source, '''    char *command;
    Tk_Window win;
} ActionEvent;''', '''    Tk_Window win;
    Tcl_Interp *interp;
} ActionEvent;''')
    source = replace_once(source, '/* Event proc which calls the ActionEventProc procedure. */',
                          '#include "mylWinA11yActions.h"\n\n/* Event proc which calls the ActionEventProc procedure. */')
    source = replace_function(source, 'ActionEventProc', '    return MylPerformAction((ActionEvent *)ev);')
    source = replace_function(source, 'TkDoDefaultAction', '''
    int childId = (int)PTR2INT(args[0]);
    Tk_Window toplevel = (Tk_Window)args[1];
    Tk_Window win = toplevel ? GetTkWindowForChildId(childId, toplevel) : NULL;
    ActionEvent *event;
    mainThreadResult = E_INVALIDARG;
    if (!win || !MylActionForWindow(win)) return;
    event = (ActionEvent *)Tcl_Alloc(sizeof(*event));
    event->header.proc = ActionEventProc;
    event->win = win;
    event->interp = Tk_Interp(win);
    Tcl_Preserve(event->interp);
    Tk_CreateEventHandler(win, StructureNotifyMask, MylCancelAction, event);
    Tcl_QueueEvent((Tcl_Event *)event, TCL_QUEUE_TAIL);
    mainThreadResult = S_OK;''')
    source = replace_once(source, '''TkRootAccessible_accDoDefaultAction(
    TCL_UNUSED(IAccessible *), /* this */''', '''TkRootAccessible_accDoDefaultAction(
    IAccessible *this,''')
    source = replace_once(source, 'RunOnMainThreadSync(func, 1, INT2PTR(childId));',
                          'RunOnMainThreadSync(func, 2, INT2PTR(childId),\n'
                          '                (void*)((TkRootAccessible *)this)->toplevel);')
    source = replace_once(source, '    mainThreadId = Tcl_GetCurrentThread();', '''    static int exitHandlerInstalled = 0;
    mainThreadId = Tcl_GetCurrentThread();
    if (!exitHandlerInstalled) {
        Tcl_CreateThreadExitHandler(MylDispatchThreadExit, NULL);
        exitHandlerInstalled = 1;
    }''')
    source = replace_function(source, 'TkAccChildCount', '''
    int nextId = 1;
    Tk_Window toplevel = GetToplevelOfWidget(win);
    if (!toplevel) return 0;
    ClearChildIdTableForToplevel(toplevel);
    AssignChildIdsRecursive(toplevel, &nextId, Tk_Interp(toplevel), toplevel);
    return nextId - 1;''')
    source = replace_once(source, '''    SetChildIdForTkWindow(win, *nextId, childIdTable);
    (*nextId)++;

    /* Initialize checked state for checkbuttons and radiobuttons. */
    ComputeAndCacheCheckedState(win, interp);''', '''    /* Child IDs are contiguous simple elements, excluding the toplevel.
     * Nested dialogs have their own provider and must not leak into this one. */
    if (win != toplevel) {
        if (Tk_IsTopLevel(win)) return;
        SetChildIdForTkWindow(win, *nextId, childIdTable);
        (*nextId)++;
    }''')
    source = replace_once(source, '''    LONG childId = GetChildIdForTkWindow(win, childIdTable);
    if (childId <= 0)''', '''    childIdTable = GetChildIdTableForToplevel(toplevel);
    LONG childId = win == toplevel ? CHILDID_SELF : GetChildIdForTkWindow(win, childIdTable);
    if (childId < 0)''')
    source = replace_once(source, '''    TkGlobalUnlock();
    return S_OK;
}

/* Function to get accessible frame to MSAA. */''', '''    TkGlobalUnlock();
    return S_FALSE; /* Valid simple child: no separate IDispatch object. */
}

/* Function to get accessible frame to MSAA. */''')
    source = replace_once(source, 'pvarRole->lVal = ROLE_SYSTEM_WINDOW;', 'pvarRole->lVal = ROLE_SYSTEM_CLIENT;')
    source = replace_once(source, '''	HWND hwnd = Tk_GetHWND(Tk_WindowId(tkAccessible->toplevel));
	int wlen''', '''	HWND hwnd = TkWinGetWrapperWindow(tkAccessible->toplevel);
	int wlen''')
    source = replace_function(source, 'TkRootAccessible_get_accParent', '''
    if (!ppdispParent) return E_INVALIDARG;
    *ppdispParent = NULL;
    TkRootAccessible *provider = (TkRootAccessible *)this;
    if (!provider->toplevel) return RPC_E_DISCONNECTED;
    HWND wrapper = TkWinGetWrapperWindow(provider->toplevel);
    if (!wrapper) return S_FALSE;
    return CreateStdAccessibleObject(wrapper, OBJID_WINDOW, &IID_IDispatch, (void **)ppdispParent);''')
    source = replace_once(source, '''TkRootAccessible_get_accParent(
    TCL_UNUSED(IAccessible *), /* this */''', '''TkRootAccessible_get_accParent(
    IAccessible *this,''')
    source = replace_once(source, '    TkRootAccessible_AddRef((IAccessible*)tkAccessible);\n    NotifyWinEvent',
                          '    /* One owner reference; COM adds its own references. */\n    NotifyWinEvent')
    source = replace_once(source, '''    if (count == 0) {
	TkGlobalLock();
	if (tkAccessible->win && tkAccessibleTableInitialized) {
	    Tcl_HashEntry *entry = Tcl_FindHashEntry(tkAccessibleTable, tkAccessible->win);
	    if (entry) {
		Tcl_DeleteHashEntry(entry);
	    }
	}''', '''    if (count == 0) {
	/* The Tk owner removes the table entry before releasing its reference.
	 * COM Release must never touch a Tcl hash table on an RPC thread. */
	TkGlobalLock();''')
    source = replace_once(source, '''    ClearChildIdTableForToplevel(tkAccessible->toplevel);
    TkRootAccessible_Release''', '''    ClearChildIdTableForToplevel(tkAccessible->toplevel);
    tkAccessible->win = NULL;
    tkAccessible->toplevel = NULL;
    tkAccessible->interp = NULL;
    tkAccessible->hwnd = NULL;
    TkRootAccessible_Release''')
    source = replace_once(source, '''    TkGlobalLock();
    TkRootAccessible *accessible = CreateRootAccessible(interp, hwnd, windowName);''', '''    TkGlobalLock();
    TkRootAccessible *accessible = GetTkAccessibleForWindow(toplevel);
    if (accessible) {
        TkGlobalUnlock();
        return TCL_OK; /* Re-mapping must not leak duplicate providers/handlers. */
    }
    accessible = CreateRootAccessible(interp, hwnd, Tk_PathName(toplevel));''')
    source = replace_once(source, '''    Tk_Window tkwin = Tk_HWNDToWindow(hwnd);

    /* Handle MSAA requests. */''', '''    Tk_Window tkwin = Tk_HWNDToWindow(hwnd);
    if (!tkwin || !Tk_IsTopLevel(tkwin)) return;

    /* Handle MSAA requests. */''')
    # A destroyed or hidden widget must not be dereferenced from stale IDs.
    source = replace_once(source, '''	if (PTR2INT(Tcl_GetHashValue(entry)) == id) {
	    Tk_Window win = (Tk_Window)Tcl_GetHashKey(childIdTable, entry);''', '''	if (PTR2INT(Tcl_GetHashValue(entry)) == id) {
	    Tk_Window win = (Tk_Window)Tcl_GetHashKey(childIdTable, entry);''')
    # Rebuild on each lookup: ID assignment and enumeration share one traversal.
    source = replace_once(source, '''    if (!toplevel) return NULL;
    /*
     * We are looking''', '''    if (!toplevel) return NULL;
    ClearChildIdTableForToplevel(toplevel);
    int nextId = 1;
    AssignChildIdsRecursive(toplevel, &nextId, Tk_Interp(toplevel), toplevel);
    /*
     * We are looking''')
    source = replace_function(source, 'ClearChildIdTableForToplevel', '''
    (void)toplevel; /* Query/focus refresh must never renumber existing IDs. */''')
    source = replace_once(source, '    LONG refCount;\n} TkRootAccessible;',
                          '    LONG refCount;\n    int nextChildId;\n} TkRootAccessible;')
    source = replace_once(source, '    tkAccessible->refCount = 1;',
                          '    tkAccessible->refCount = 1;\n    tkAccessible->nextChildId = 1;')
    source = replace_once(source, '''    ClearChildIdTableForToplevel(tkAccessible->toplevel);
    tkAccessible->win = NULL;''', '''    MylDeleteChildIds(tkAccessible->toplevel);
    tkAccessible->win = NULL;''')
    source = replace_function(source, 'AssignChildIdsRecursive', '''
    TkRootAccessible *provider;
    Tcl_HashTable *table;
    TkWindow *child;
    int id;
    if (!win || !interp || !toplevel || !Tk_IsMapped(win) || (((TkWindow *)win)->flags & TK_ALREADY_DEAD)
            || (win != toplevel && Tk_IsTopLevel(win))) return;
    provider = GetTkAccessibleForWindow(toplevel);
    if (!provider) return;
    table = GetChildIdTableForToplevel(toplevel);
    if (!table) return;
    if (win != toplevel && Tcl_FindHashEntry(TkAccessibilityObject, win)) {
        id = GetChildIdForTkWindow(win, table);
        if (id < 0 && provider->nextChildId < INT_MAX) {
            MylChildIdentity *identity = (MylChildIdentity *)Tcl_Alloc(sizeof(*identity));
            identity->win = win;
            identity->toplevel = toplevel;
            id = provider->nextChildId++;
            SetChildIdForTkWindow(win, id, table);
            Tk_CreateEventHandler(win, StructureNotifyMask, MylChildDestroyed, identity);
        }
        if (id > 0) (*nextId)++;
    }
    for (child = ((TkWindow *)win)->childList; child; child = child->nextPtr) {
        AssignChildIdsRecursive((Tk_Window)child, nextId, interp, toplevel);
    }''')
    source = replace_once(source, '''	    Tk_Window win = (Tk_Window)Tcl_GetHashKey(childIdTable, entry);
	    TkGlobalUnlock();
	    return win;''', '''	    Tk_Window win = (Tk_Window)Tcl_GetHashKey(childIdTable, entry);
	    TkGlobalUnlock();
	    return MylWindowVisible(win, toplevel) ? win : NULL;''')
    source = replace_once(source, '''static HRESULT STDMETHODCALLTYPE
TkRootAccessible_QueryInterface(''', delete_ids + '\n#include "mylWinA11yEnum.h"\n\nstatic HRESULT STDMETHODCALLTYPE\nTkRootAccessible_QueryInterface(')
    source = replace_once(source, '''    if (!ppvObject) return E_INVALIDARG;
    if (IsEqualIID''', '''    if (!ppvObject) return E_INVALIDARG;
    if (IsEqualIID(riid, &IID_IEnumVARIANT)) return MylQueryEnum(this, ppvObject);
    if (IsEqualIID''')
    source = replace_once(source, '''int TkWinAccessiblity_Init(
    Tcl_Interp *interp)''', '''#include "mylWinA11yProbe.h"

int TkWinAccessiblity_Init(
    Tcl_Interp *interp)''')
    source = replace_once(source, '''    /* Initialize Tcl commands. */
    Tcl_CreateObjCommand2''', '''    /* Initialize Tcl commands. */
    Tcl_CreateObjCommand2(interp, "::tk::accessible::myl_patch_version", MylPatchVersion, NULL, NULL);
    Tcl_CreateObjCommand2(interp, "::tk::accessible::myl_provider_probe", MylProviderProbe, NULL, NULL);
    Tcl_CreateObjCommand2''')
    return marshal_methods(source)


def apply_windows_patch(tree: Path):
    win = tree / 'win'
    receipt = tree / 'myl-accessibility-patch.json'
    if receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if (record.get('patch_id') != PATCH_ID
                or record.get('patcher_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
            raise ValueError('Different native accessibility patch already applied')
        for name, expected in record['output_hashes'].items():
            if hashlib.sha256((win / name).read_bytes()).hexdigest() != expected:
                raise ValueError('Modified patched native source: ' + name)
        for name in ('Dispatch', 'Actions', 'Enum', 'Probe'):
            expected = record['output_hashes']['mylWinA11y' + name + '.h']
            if hashlib.sha256((NATIVE / ('tkWinA11y' + name + '.h')).read_bytes()).hexdigest() != expected:
                raise ValueError('Different native accessibility helper: ' + name)
        return record
    inputs = {name: (win / name).read_bytes() for name in INPUT_HASHES}
    for name, raw in inputs.items():
        if hashlib.sha256(raw).hexdigest() != INPUT_HASHES[name]:
            raise ValueError('Unrecognized native source: ' + name)
    provider = repair_provider(inputs['tkWinAccessibility.c'].decode('utf-8'))
    wm = replace_once(inputs['tkWinWm.c'].decode('utf-8'), '''    switch (message) {
    case WM_KILLFOCUS:
    case WM_ERASEBKGND:''', '''    switch (message) {
    case WM_GETOBJECT:
        /* Publish the same client provider from the decorated window too. */
        if ((LONG)lParam == (LONG)-4) { /* OBJID_CLIENT, without oleacc.h */
            winPtr = GetTopLevel(hwnd);
            if (winPtr && winPtr->window != None) {
                return SendMessageW(Tk_GetHWND(winPtr->window), message, wParam, lParam);
            }
        }
        break;
    case WM_KILLFOCUS:
    case WM_ERASEBKGND:''')
    # All checks finish before changing the extracted build-only sources.
    for name, content in (('tkWinAccessibility.c', provider), ('tkWinWm.c', wm)):
        (win / name).write_text(content, encoding='utf-8', newline='\n')
    for name in ('Dispatch', 'Actions', 'Enum', 'Probe'):
        shutil.copy2(NATIVE / ('tkWinA11y' + name + '.h'), win / ('mylWinA11y' + name + '.h'))
    outputs = (*INPUT_HASHES, *(f'mylWinA11y{name}.h' for name in ('Dispatch', 'Actions', 'Enum', 'Probe')))
    record = {'patch_id': PATCH_ID, 'input_hashes': INPUT_HASHES,
              'output_hashes': {name: hashlib.sha256((win / name).read_bytes()).hexdigest() for name in outputs},
              'patcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    receipt.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record
