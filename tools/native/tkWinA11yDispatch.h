/* ManageYourLibrary Windows accessibility repair, MIT (see project LICENSE).
 * Included by the hash-locked Tk source and the native regression harness.
 * Tcl owns queued events. A separately reference-counted request owns its
 * completion handle; a timed-out, not-yet-started call must never use the
 * caller's stack arguments later.
 */
#define MYL_A11Y_DISPATCH_VERSION 1
#define MYL_PENDING 0
#define MYL_RUNNING 1
#define MYL_DONE 2
#define MYL_CANCELLED 3

typedef struct {
    MainThreadFunc func;
    int num_args;
    void *args[6];
    HANDLE doneEvent;
    volatile LONG references;
    volatile LONG state;
} MylMainThreadRequest;

typedef struct {
    Tcl_Event header;
    MylMainThreadRequest *request;
} MainThreadSyncEvent;

static void
MylReleaseRequest(MylMainThreadRequest *request)
{
    if (InterlockedDecrement(&request->references) == 0) {
        CloseHandle(request->doneEvent);
        Tcl_Free(request);
    }
}

int
ExecuteOnMainThreadSync(Tcl_Event *ev, int flags)
{
    MainThreadSyncEvent *event = (MainThreadSyncEvent *)ev;
    MylMainThreadRequest *request = event->request;
    (void)flags;
    if (InterlockedCompareExchange(&request->state, MYL_RUNNING,
            MYL_PENDING) == MYL_PENDING) {
        request->func(request->num_args, request->args);
        InterlockedExchange(&request->state, MYL_DONE);
        SetEvent(request->doneEvent);
    }
    MylReleaseRequest(request); /* Release only the queue's request reference. */
    return 1;                  /* Tcl frees the event, exactly once. */
}

static int
MylDeleteSyncEvent(Tcl_Event *ev, void *unused)
{
    MainThreadSyncEvent *event;
    MylMainThreadRequest *request;
    (void)unused;
    if (ev->proc != ExecuteOnMainThreadSync) {
        return 0;
    }
    event = (MainThreadSyncEvent *)ev;
    request = event->request;
    InterlockedCompareExchange(&request->state, MYL_CANCELLED, MYL_PENDING);
    SetEvent(request->doneEvent);
    MylReleaseRequest(request);
    return 1; /* Tcl_DeleteEvents owns and frees the event. */
}

static void
MylDispatchThreadExit(void *unused)
{
    (void)unused;
    Tcl_DeleteEvents(MylDeleteSyncEvent, NULL);
#ifdef MYL_A11Y_ACTION_CLEANUP
    Tcl_DeleteEvents(MylDeleteActionEvent, NULL);
#endif
}

static int
MylDispatch(MainThreadFunc func, int num_args, void **args)
{
    MylMainThreadRequest *request;
    MainThreadSyncEvent *event;
    DWORD result;
    LONG state;
    int completed;
    if (!func || num_args < 0 || num_args > 6) {
        return 0;
    }
    if (Tcl_GetCurrentThread() == mainThreadId) {
        func(num_args, args);
        return 1;
    }
    request = (MylMainThreadRequest *)Tcl_Alloc(sizeof(*request));
    request->func = func;
    request->num_args = num_args;
    for (int i = 0; i < num_args; i++) {
        request->args[i] = args[i];
    }
    request->references = 2; /* caller and queued event */
    request->state = MYL_PENDING;
    request->doneEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    if (!request->doneEvent) {
        Tcl_Free(request);
        return 0;
    }
    event = (MainThreadSyncEvent *)Tcl_Alloc(sizeof(*event));
    event->header.proc = ExecuteOnMainThreadSync;
    event->request = request;
    Tcl_ThreadQueueEvent(mainThreadId, (Tcl_Event *)event, TCL_QUEUE_TAIL);
    Tcl_ThreadAlert(mainThreadId);
    result = WaitForSingleObject(request->doneEvent, 500);
    if (result != WAIT_OBJECT_0) {
        state = InterlockedCompareExchange(&request->state, MYL_CANCELLED,
                MYL_PENDING);
        if (state == MYL_RUNNING) {
            /* Once execution starts, its borrowed output pointers must remain
             * live until it finishes. Never return a running stack frame. */
            WaitForSingleObject(request->doneEvent, INFINITE);
        }
    }
    completed = InterlockedCompareExchange(&request->state, MYL_DONE,
            MYL_DONE) == MYL_DONE;
    MylReleaseRequest(request);
    return completed;
}

void
RunOnMainThreadSync(MainThreadFunc func, int num_args, ...)
{
    void *args[6];
    va_list ap;
    if (num_args < 0 || num_args > 6) {
        return;
    }
    va_start(ap, num_args);
    for (int i = 0; i < num_args; i++) {
        args[i] = va_arg(ap, void *);
    }
    va_end(ap);
    (void)MylDispatch(func, num_args, args);
}
