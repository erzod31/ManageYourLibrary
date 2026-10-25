/* Linux-only GLib -> Tcl notifier adapter. MIT, as the project LICENSE.
 * GLib callbacks remain on the Tk/Tcl owner thread. No reader or UI policy.
 * The caller zero-initializes the state and keeps it alive until callbacks
 * have returned, including after deletion from inside a GLib callback. */
#ifndef MYL_TK_UNIX_A11Y_LOOP_H
#define MYL_TK_UNIX_A11Y_LOOP_H
#include <tcl.h>
#include <glib.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <limits.h>
#include <string.h>

typedef struct MylTkGlibLoop MylTkGlibLoop;
typedef struct {
    MylTkGlibLoop *loop;
    int fd; /* Our duplicate, never the source's descriptor. */
} MylTkGlibWatch;
typedef struct MylTkGlibEvent {
    Tcl_Event header;
    MylTkGlibLoop *loop;
    struct MylTkGlibEvent *previous_active;
} MylTkGlibEvent;
struct MylTkGlibLoop {
    GMainContext *context;
    Tcl_ThreadId owner;
    GPtrArray *watches;
    Tcl_TimerToken timer;
    MylTkGlibEvent *active_event;
    const char *problem;
    gint timeout_ms;
    gboolean live, queued, dispatching, refreshing, owns_context;
    guint dispatch_depth;
    guint stale_fd_retries;
};

#define MYL_TK_GLIB_EVENT_FLAGS (TCL_FILE_EVENTS | TCL_TIMER_EVENTS | TCL_WINDOW_EVENTS)
#define MYL_TK_GLIB_MAX_FDS 4096
static int MylTkGlibLoopDelete(MylTkGlibLoop *loop);
static void MylTkGlibRefresh(MylTkGlibLoop *loop);
static int MylTkGlibEventRun(Tcl_Event *event, int flags);

static gboolean MylTkGlibOwner(MylTkGlibLoop *loop)
{ return loop && loop->owner == Tcl_GetCurrentThread(); }

static void MylTkGlibQueue(MylTkGlibLoop *loop)
{
    MylTkGlibEvent *event;
    if (!MylTkGlibOwner(loop) || !loop->live || loop->queued) return;
    event = (MylTkGlibEvent *)Tcl_Alloc(sizeof(*event));
    event->header.proc = MylTkGlibEventRun;
    event->loop = loop;
    loop->queued = TRUE;
    Tcl_QueueEvent((Tcl_Event *)event, TCL_QUEUE_TAIL);
}

static void MylTkGlibFdReady(void *data, int mask)
{
    MylTkGlibWatch *watch = (MylTkGlibWatch *)data;
    (void)mask;
    /* Do not consume I/O from the duplicated descriptor. GLib owns I/O. */
    MylTkGlibQueue(watch->loop);
}

static void MylTkGlibTimerReady(void *data)
{
    MylTkGlibLoop *loop = (MylTkGlibLoop *)data;
    loop->timer = NULL;
    MylTkGlibQueue(loop);
}

static void MylTkGlibClearWatches(MylTkGlibLoop *loop)
{
    if (loop->timer) { Tcl_DeleteTimerHandler(loop->timer); loop->timer = NULL; }
    if (loop->watches) {
        for (guint i = 0; i < loop->watches->len; i++) {
            MylTkGlibWatch *watch = g_ptr_array_index(loop->watches, i);
            Tcl_DeleteFileHandler(watch->fd);
            close(watch->fd);
            g_free(watch);
        }
        g_ptr_array_set_size(loop->watches, 0);
    }
}

/* Only query and observe the context's descriptors here. iteration() later
 * performs its own prepare/query/check with its untouched GPollFD snapshot. */
static void MylTkGlibRefresh(MylTkGlibLoop *loop)
{
    GMainContext *context;
    GPollFD *fds = NULL;
    gint priority = G_MAXINT, timeout = -1, count = 0, capacity = 0;
    gint duplicate_minimum;
    gboolean ready, stale_seen = FALSE;
    guint attempt = 0;
    if (!MylTkGlibOwner(loop) || !loop->live || loop->refreshing) return;
    loop->refreshing = TRUE;
    context = g_main_context_ref(loop->context);
retry_snapshot:
    if (!g_main_context_acquire(context)) {
        loop->problem = "glib_context_owned_by_another_thread";
        goto done;
    }
    ready = g_main_context_prepare(context, &priority);
    do {
        count = g_main_context_query(context, priority, &timeout, fds, capacity);
        if (count < 0 || count > MYL_TK_GLIB_MAX_FDS) {
            loop->problem = "glib_poll_descriptor_bound";
            break;
        }
        if (count <= capacity) break;
        capacity = count;
        fds = g_renew(GPollFD, fds, capacity);
    } while (loop->live);
    g_main_context_release(context);
    if (!loop->live || loop->problem) goto done;
    duplicate_minimum = 0;
    for (gint i = 0; i < count; i++) {
        if (fds[i].fd == INT_MAX) { loop->problem = "glib_poll_descriptor_bound"; goto done; }
        duplicate_minimum = MAX(duplicate_minimum, fds[i].fd + 1);
    }
    MylTkGlibClearWatches(loop);
    /* Recreate duplicates even if source fd numbers match the previous poll
     * set: an fd may have been closed and reused for a different socket. */
    for (gint i = 0; i < count; i++) {
        int mask = 0, duplicate;
        MylTkGlibWatch *watch;
        if (fds[i].fd < 0) continue;
#ifdef F_DUPFD_CLOEXEC
        duplicate = fcntl(fds[i].fd, F_DUPFD_CLOEXEC, duplicate_minimum);
#else
        duplicate = fcntl(fds[i].fd, F_DUPFD, duplicate_minimum);
        if (duplicate >= 0 && fcntl(duplicate, F_SETFD, FD_CLOEXEC) < 0) {
            close(duplicate); duplicate = -1;
        }
#endif
        if (duplicate < 0 && errno == EBADF) {
            /* A source can be removed/closed by another thread after query.
             * Retry a fresh snapshot once, then omit just that stale fd. The
             * context wakeup and remaining live descriptors stay observable;
             * GLib's own next check handles NVAL if the source still exists. */
            if (!attempt++) { loop->stale_fd_retries++; goto retry_snapshot; }
            stale_seen = TRUE;
            continue;
        }
        if (duplicate < 0) { loop->problem = "glib_poll_descriptor_duplication_failed"; break; }
        if (fds[i].events & (G_IO_IN | G_IO_PRI)) mask |= TCL_READABLE;
        if (fds[i].events & G_IO_OUT) mask |= TCL_WRITABLE;
        mask |= TCL_EXCEPTION;
        if (!(mask & (TCL_READABLE | TCL_WRITABLE))) mask |= TCL_READABLE;
        watch = g_new0(MylTkGlibWatch, 1);
        watch->loop = loop;
        watch->fd = duplicate;
        g_ptr_array_add(loop->watches, watch);
        Tcl_CreateFileHandler(duplicate, mask, MylTkGlibFdReady, watch);
    }
    /* One nonblocking check lets GLib observe NVAL for an omitted stale fd.
     * A healthy context with timeout=-1 still sleeps solely on its FDs. */
    loop->timeout_ms = ready || stale_seen ? 0 : timeout;
    if (!loop->problem && loop->timeout_ms >= 0)
        loop->timer = Tcl_CreateTimerHandler(loop->timeout_ms, MylTkGlibTimerReady, loop);
done:
    g_free(fds);
    g_main_context_unref(context);
    loop->refreshing = FALSE;
    if (loop->problem && loop->live) MylTkGlibLoopDelete(loop);
}

static void MylTkGlibSetup(void *data, int flags)
{
    MylTkGlibLoop *loop = (MylTkGlibLoop *)data;
    if (flags & MYL_TK_GLIB_EVENT_FLAGS) {
        MylTkGlibRefresh(loop);
        if (loop->live && loop->timeout_ms >= 0) {
            Tcl_Time timeout = {loop->timeout_ms / 1000, (loop->timeout_ms % 1000) * 1000};
            Tcl_SetMaxBlockTime(&timeout);
        }
    }
}

static void MylTkGlibCheck(void *data, int flags)
{
    MylTkGlibLoop *loop = (MylTkGlibLoop *)data;
    GMainContext *context;
    gboolean pending;
    if (!(flags & MYL_TK_GLIB_EVENT_FLAGS) || !MylTkGlibOwner(loop)
            || !loop->live || loop->refreshing) return;
    /* pending() invokes source prepare/check functions. They can delete the
     * adapter and release its last context reference while this call runs. */
    context = g_main_context_ref(loop->context);
    pending = g_main_context_pending(context);
    if (pending && loop->live && loop->context == context) MylTkGlibQueue(loop);
    g_main_context_unref(context);
}

static int MylTkGlibEventRun(Tcl_Event *event, int flags)
{
    MylTkGlibLoop *loop = ((MylTkGlibEvent *)event)->loop;
    GMainContext *context;
    if (!(flags & MYL_TK_GLIB_EVENT_FLAGS)) return 0;
    if (!loop->live) return 1;
    if (!MylTkGlibOwner(loop) || loop->refreshing) return 0;
    loop->queued = FALSE;
    MylTkGlibEvent *current = (MylTkGlibEvent *)event;
    current->previous_active = loop->active_event;
    loop->active_event = current;
    context = g_main_context_ref(loop->context);
    loop->dispatching = TRUE;
    loop->dispatch_depth++;
    /* One nonblocking GLib iteration per Tcl event. No while-pending loop and
     * no immediate requeue: Tcl's own timer/check sources must get a turn. */
    g_main_context_iteration(context, FALSE);
    loop->dispatch_depth--;
    loop->dispatching = loop->dispatch_depth != 0;
    g_main_context_unref(context);
    if (loop->live) MylTkGlibRefresh(loop);
    loop->active_event = current->previous_active;
    return 1;
}

static int MylTkGlibDeleteEvent(Tcl_Event *event, void *data)
{
    MylTkGlibLoop *loop = (MylTkGlibLoop *)data;
    for (MylTkGlibEvent *active = loop->active_event; active; active = active->previous_active)
        if (event == (Tcl_Event *)active) return 0;
    return event->proc == MylTkGlibEventRun && ((MylTkGlibEvent *)event)->loop == loop;
}

static void MylTkGlibThreadExit(void *data)
{ MylTkGlibLoopDelete((MylTkGlibLoop *)data); }

static int MylTkGlibLoopDelete(MylTkGlibLoop *loop)
{
    if (!loop || !loop->live) return 1;
    if (!MylTkGlibOwner(loop)) return 0;
    loop->live = FALSE;
    Tcl_DeleteEventSource(MylTkGlibSetup, MylTkGlibCheck, loop);
    Tcl_DeleteThreadExitHandler(MylTkGlibThreadExit, loop);
    Tcl_DeleteEvents(MylTkGlibDeleteEvent, loop);
    loop->queued = FALSE;
    MylTkGlibClearWatches(loop);
    g_ptr_array_free(loop->watches, TRUE);
    loop->watches = NULL;
    if (loop->owns_context) { g_main_context_release(loop->context); loop->owns_context = FALSE; }
    g_main_context_unref(loop->context);
    loop->context = NULL;
    return 1;
}

static int MylTkGlibLoopInit(MylTkGlibLoop *loop, GMainContext *context)
{
    if (!loop || !context) return 0;
    if (loop->dispatching || loop->refreshing) return 0;
    if (loop->live) return MylTkGlibOwner(loop) && loop->context == context;
    memset(loop, 0, sizeof(*loop));
    loop->owner = Tcl_GetCurrentThread();
    loop->context = g_main_context_ref(context);
    if (!g_main_context_acquire(context)) {
        loop->problem = "glib_context_owned_by_another_thread";
        g_main_context_unref(loop->context);
        loop->context = NULL;
        return 0;
    }
    /* Retained until Delete: worker g_main_context_invoke must enqueue on the
     * owner, never execute a Tk-related callback inline in the worker. */
    loop->owns_context = TRUE;
    loop->watches = g_ptr_array_new();
    loop->live = TRUE;
    Tcl_CreateEventSource(MylTkGlibSetup, MylTkGlibCheck, loop);
    Tcl_CreateThreadExitHandler(MylTkGlibThreadExit, loop);
    MylTkGlibRefresh(loop);
    return loop->live && !loop->problem;
}
#endif
