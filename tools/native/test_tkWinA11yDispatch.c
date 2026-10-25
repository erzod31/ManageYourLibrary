/* Native regression harness, MIT. No Tk window, desktop automation or books.
 * The actual repaired dispatcher is compiled against a small Tcl queue model.
 * Run with MSVC AddressSanitizer to catch request/event lifetime errors.
 */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <assert.h>

typedef DWORD Tcl_ThreadId;
typedef struct Tcl_Event Tcl_Event;
struct Tcl_Event { int (*proc)(Tcl_Event *, int); Tcl_Event *nextPtr; };
typedef void (*MainThreadFunc)(int, void **);
static Tcl_ThreadId mainThreadId;
static CRITICAL_SECTION queueLock;
static Tcl_Event *first, *last;
static volatile LONG allocations, handles, callbacks;
static HANDLE workerFinished;
static int simulateEventFailure;
#define TCL_QUEUE_TAIL 0
#define Tcl_GetCurrentThread GetCurrentThreadId

static void *Tcl_Alloc(size_t size) {
    void *result = malloc(size);
    assert(result);
    InterlockedIncrement(&allocations);
    return result;
}
static void Tcl_Free(void *pointer) {
    assert(pointer);
    InterlockedDecrement(&allocations);
    free(pointer);
}
static HANDLE TestCreateEvent(void *attributes, BOOL manual, BOOL signaled, void *name) {
    HANDLE result;
    (void)attributes; (void)name;
    if (simulateEventFailure) return NULL;
    result = CreateEventW(NULL, manual, signaled, NULL);
    if (result) InterlockedIncrement(&handles);
    return result;
}
static BOOL TestCloseHandle(HANDLE handle) {
    BOOL result = CloseHandle(handle);
    assert(result);
    InterlockedDecrement(&handles);
    return result;
}
static void Tcl_ThreadQueueEvent(Tcl_ThreadId thread, Tcl_Event *event, int position) {
    (void)position;
    assert(thread == mainThreadId);
    event->nextPtr = NULL;
    EnterCriticalSection(&queueLock);
    if (last) last->nextPtr = event; else first = event;
    last = event;
    LeaveCriticalSection(&queueLock);
}
static void Tcl_ThreadAlert(Tcl_ThreadId thread) { assert(thread == mainThreadId); }
static void Tcl_DeleteEvents(int (*predicate)(Tcl_Event *, void *), void *data) {
    Tcl_Event **link;
    EnterCriticalSection(&queueLock);
    link = &first;
    while (*link) {
        Tcl_Event *event = *link;
        if (predicate(event, data)) {
            *link = event->nextPtr;
            Tcl_Free(event);
        } else {
            link = &event->nextPtr;
        }
    }
    last = first;
    while (last && last->nextPtr) last = last->nextPtr;
    LeaveCriticalSection(&queueLock);
}
#undef CreateEvent
#define CreateEvent TestCreateEvent
#define CloseHandle TestCloseHandle
#ifdef MYL_TEST_LEGACY
#define TCL_UNUSED(type) type unused
#include "legacy-dispatch.h"
static int MylDispatch(MainThreadFunc func, int count, void **args) {
    if (!func || count < 0 || count > 6) return 0;
    RunOnMainThreadSync(func, count, args[0]);
    return 1;
}
static void MylDispatchThreadExit(void *unused) { (void)unused; }
#else
#include "tkWinA11yDispatch.h"
#endif
#undef CreateEvent
#undef CloseHandle

static int service(void) {
    Tcl_Event *event;
    EnterCriticalSection(&queueLock);
    event = first;
    if (event) {
        first = event->nextPtr;
        if (!first) last = NULL;
    }
    LeaveCriticalSection(&queueLock);
    if (!event) return 0;
    assert(event->proc(event, 0) == 1);
    Tcl_Free(event); /* Exactly what Tcl_ServiceEvent does. */
    return 1;
}
static void callback(int count, void **args) {
    assert(GetCurrentThreadId() == mainThreadId);
    assert(count == 1);
    InterlockedIncrement(&callbacks);
    *(int *)args[0] = 42;
}
static void slowCallback(int count, void **args) {
    Sleep(700); /* Worker times out after callback starts, but cannot return. */
    assert(WaitForSingleObject(workerFinished, 0) == WAIT_TIMEOUT);
    callback(count, args);
}
typedef struct { MainThreadFunc func; int result, value; } Worker;
static DWORD WINAPI worker(void *data) {
    Worker *task = (Worker *)data;
    void *args[] = { &task->value };
    task->result = MylDispatch(task->func, 1, args);
    if (workerFinished) SetEvent(workerFinished);
    return 0;
}
static HANDLE start(Worker *task) {
    HANDLE thread = CreateThread(NULL, 0, worker, task, 0, NULL);
    assert(thread);
    return thread;
}
static void join(HANDLE thread) {
    assert(WaitForSingleObject(thread, 3000) == WAIT_OBJECT_0);
    assert(CloseHandle(thread));
}
static void waitQueued(void) {
    int queued = 0;
    for (int i = 0; i < 2000; i++) {
        EnterCriticalSection(&queueLock);
        queued = first != NULL;
        LeaveCriticalSection(&queueLock);
        if (queued) return;
        Sleep(1);
    }
    assert(queued);
}
static void balanced(void) { assert(!first && !last && allocations == 0 && handles == 0); }

int main(void) {
    Worker task;
    HANDLE thread;
    int value = 0;
    void *args[] = { &value };
    InitializeCriticalSection(&queueLock);
    mainThreadId = GetCurrentThreadId();
    assert(MylDispatch(callback, 1, args) && value == 42);
    balanced();

    task = (Worker){callback, -1, 0};
    thread = start(&task); waitQueued(); assert(service()); join(thread);
    assert(task.result && task.value == 42); balanced();

    task = (Worker){callback, -1, 0};
    thread = start(&task); waitQueued(); join(thread);
    assert(!task.result && task.value == 0);
    assert(service()); assert(task.value == 0); balanced();

    task = (Worker){slowCallback, -1, 0};
    workerFinished = CreateEventW(NULL, TRUE, FALSE, NULL);
    assert(workerFinished);
    thread = start(&task); waitQueued(); assert(service()); join(thread);
    assert(task.result && task.value == 42);
    CloseHandle(workerFinished); workerFinished = NULL; balanced();

    task = (Worker){callback, -1, 0};
    thread = start(&task); waitQueued(); MylDispatchThreadExit(NULL); join(thread);
    assert(!task.result && task.value == 0); balanced();

    task = (Worker){callback, -1, 0};
    thread = start(&task); waitQueued(); join(thread); MylDispatchThreadExit(NULL);
    assert(!task.result && task.value == 0); balanced();

    simulateEventFailure = 1;
    task = (Worker){callback, -1, 0};
    thread = start(&task); join(thread);
    assert(!task.result && task.value == 0); balanced();
    simulateEventFailure = 0;
    assert(!MylDispatch(NULL, 0, args));
    assert(!MylDispatch(callback, -1, args));
    assert(!MylDispatch(callback, 7, args)); balanced();

    for (int repetition = 0; repetition < 30; repetition++) {
        Worker tasks[16]; HANDLE threads[16];
        for (int i = 0; i < 16; i++) {
            tasks[i] = (Worker){callback, -1, 0};
            threads[i] = start(&tasks[i]);
        }
        while (WaitForMultipleObjects(16, threads, TRUE, 0) == WAIT_TIMEOUT) {
            if (!service()) Sleep(1);
        }
        for (int i = 0; i < 16; i++) {
            join(threads[i]); assert(tasks[i].result && tasks[i].value == 42);
        }
        balanced();
    }
    assert(callbacks == 483);
    DeleteCriticalSection(&queueLock);
    puts("{\"passed\":true,\"scenarios\":9,\"parallel_requests\":480,\"callback_count\":483,\"remaining_allocations\":0,\"remaining_handles\":0}");
    return 0;
}
