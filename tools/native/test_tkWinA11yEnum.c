/* COM enumerator contract tests, MIT. No windows or desktop automation. */
#include <windows.h>
#include <oleacc.h>
#include <oaidl.h>
#include <assert.h>
#include <stdio.h>
#define MYL_ENUM_ONLY 1
#include "tkWinA11yEnum.h"

typedef struct { IAccessibleVtbl *lpVtbl; LONG references; } TestOwner;
static ULONG STDMETHODCALLTYPE OwnerAddRef(IAccessible *self) {
    return InterlockedIncrement(&((TestOwner *)self)->references);
}
static ULONG STDMETHODCALLTYPE OwnerRelease(IAccessible *self) {
    return InterlockedDecrement(&((TestOwner *)self)->references);
}
static HRESULT STDMETHODCALLTYPE OwnerQuery(IAccessible *self, REFIID iid, void **result) {
    *result = NULL;
    if (!IsEqualIID(iid, &IID_IUnknown) && !IsEqualIID(iid, &IID_IAccessible)) return E_NOINTERFACE;
    *result = self; OwnerAddRef(self); return S_OK;
}
static IAccessibleVtbl ownerVtable = { OwnerQuery, OwnerAddRef, OwnerRelease };
static volatile LONG seen[401];
static DWORD WINAPI consume(void *data) {
    IEnumVARIANT *enumerator = data;
    VARIANT value; ULONG fetched;
    while (enumerator->lpVtbl->Next(enumerator, 1, &value, &fetched) == S_OK) {
        assert(value.vt == VT_I4 && value.lVal > 0 && value.lVal <= 400 && fetched == 1);
        assert(InterlockedIncrement(seen + value.lVal) == 1);
    }
    return 0;
}
int main(void) {
    TestOwner owner = { &ownerVtable, 1 };
    LONG ids[] = { 2, 7, 999 }, many[400];
    IEnumVARIANT *enumerator = (IEnumVARIANT *)MylNewEnum(3, ids, 0, (IAccessible *)&owner);
    IEnumVARIANT *clone;
    IUnknown *identity;
    VARIANT values[3]; ULONG fetched;
    HANDLE workers[16];
    assert(enumerator && owner.references == 2);
    assert(enumerator->lpVtbl->QueryInterface(enumerator, &IID_IUnknown, (void **)&identity) == S_OK);
    assert(identity == (IUnknown *)&owner && owner.references == 3);
    identity->lpVtbl->Release(identity);
    assert(enumerator->lpVtbl->Next(enumerator, 1, values, &fetched) == S_OK);
    assert(fetched == 1 && values[0].lVal == 2);
    assert(enumerator->lpVtbl->Clone(enumerator, &clone) == S_OK && owner.references == 3);
    assert(enumerator->lpVtbl->Skip(enumerator, 5) == S_FALSE);
    assert(enumerator->lpVtbl->Next(enumerator, 1, values, &fetched) == S_FALSE && fetched == 0);
    assert(clone->lpVtbl->Next(clone, 2, values, &fetched) == S_OK);
    assert(fetched == 2 && values[0].lVal == 7 && values[1].lVal == 999);
    assert(enumerator->lpVtbl->Reset(enumerator) == S_OK);
    assert(enumerator->lpVtbl->Next(enumerator, 2, values, NULL) == E_INVALIDARG);
    assert(enumerator->lpVtbl->Next(enumerator, 1, values, NULL) == S_OK && values[0].lVal == 2);
    assert(enumerator->lpVtbl->Next(enumerator, 1, NULL, &fetched) == E_INVALIDARG);
    assert(clone->lpVtbl->Release(clone) == 0);
    assert(enumerator->lpVtbl->Release(enumerator) == 0 && owner.references == 1);
    for (int i = 0; i < 400; i++) many[i] = i + 1;
    enumerator = (IEnumVARIANT *)MylNewEnum(400, many, 0, (IAccessible *)&owner);
    for (int i = 0; i < 16; i++) {
        workers[i] = CreateThread(NULL, 0, consume, enumerator, 0, NULL);
        assert(workers[i]);
    }
    assert(WaitForMultipleObjects(16, workers, TRUE, 5000) == WAIT_OBJECT_0);
    for (int i = 0; i < 16; i++) CloseHandle(workers[i]);
    for (int i = 1; i <= 400; i++) assert(seen[i] == 1);
    assert(enumerator->lpVtbl->Release(enumerator) == 0 && owner.references == 1);
    puts("{\"passed\":true,\"contract_cases\":8,\"concurrent_items\":400,\"owner_references\":1}");
    return 0;
}
