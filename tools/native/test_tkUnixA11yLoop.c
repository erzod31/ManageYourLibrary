#define _POSIX_C_SOURCE 200809L
/* Real GLib + Tcl (no Tk, Tcl_Init, display, reader or audio) regression and
 * IPC microbenchmark. The legacy polling driver exists only in this harness. */
#include <glib.h>
#include <glib-unix.h>
#include <tcl.h>
#include <assert.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include "tkUnixA11yLoop.h"

#define SAMPLES 40
static Tcl_ThreadId owner;
static void mark_done(void *data) { g_atomic_int_set((gint *)data, 1); }
static void pump(gint *done)
{
    gint expired = 0;
    Tcl_TimerToken guard = Tcl_CreateTimerHandler(4000, mark_done, &expired);
    while (!g_atomic_int_get(done) && !expired) Tcl_DoOneEvent(TCL_ALL_EVENTS);
    Tcl_DeleteTimerHandler(guard);
    assert(!expired && g_atomic_int_get(done));
}
static void nonblocking(int fd)
{ assert(fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK) == 0); }

typedef struct { GMainContext *context; gboolean queued; } Legacy;
typedef struct { Tcl_Event event; Legacy *loop; } LegacyEvent;
static int legacy_run(Tcl_Event *event, int flags)
{
    Legacy *loop = ((LegacyEvent *)event)->loop;
    if (!(flags & MYL_TK_GLIB_EVENT_FLAGS)) return 0;
    loop->queued = FALSE;
    while (g_main_context_pending(loop->context)) g_main_context_iteration(loop->context, FALSE);
    return 1;
}
static void legacy_setup(void *data, int flags)
{
    Legacy *loop = data;
    if (!(flags & MYL_TK_GLIB_EVENT_FLAGS)) return;
    Tcl_Time wait = {0, g_main_context_pending(loop->context) ? 0 : 10000};
    Tcl_SetMaxBlockTime(&wait);
}
static void legacy_check(void *data, int flags)
{
    Legacy *loop = data;
    if (!(flags & MYL_TK_GLIB_EVENT_FLAGS) || loop->queued || !g_main_context_pending(loop->context)) return;
    LegacyEvent *event = (LegacyEvent *)Tcl_Alloc(sizeof(*event));
    event->event.proc = legacy_run; event->loop = loop; loop->queued = TRUE;
    Tcl_QueueEvent((Tcl_Event *)event, TCL_QUEUE_TAIL);
}
static int legacy_delete_event(Tcl_Event *event, void *data)
{ return event->proc == legacy_run && ((LegacyEvent *)event)->loop == data; }

typedef struct { int request[2], response[2]; gint done, failed, replies; double us[SAMPLES]; } Exchange;
static gboolean backend_ready(gint fd, GIOCondition condition, gpointer data)
{
    Exchange *exchange = data;
    unsigned char value;
    (void)condition;
    assert(Tcl_GetCurrentThread() == owner);
    if (read(fd, &value, 1) == 1 && value) {
        assert(write(exchange->response[1], &value, 1) == 1);
        exchange->replies++;
    }
    return G_SOURCE_CONTINUE;
}
static gpointer client(gpointer data)
{
    Exchange *exchange = data;
    for (int i = 0; i < SAMPLES; i++) {
        unsigned char value = (unsigned char)(i + 1), answer = 0;
        struct pollfd ready = {exchange->response[0], POLLIN, 0};
        gint64 started = g_get_monotonic_time();
        if (write(exchange->request[1], &value, 1) != 1 || poll(&ready, 1, 2000) != 1
                || read(exchange->response[0], &answer, 1) != 1 || answer != value) {
            g_atomic_int_set(&exchange->failed, 1); break;
        }
        exchange->us[i] = (double)(g_get_monotonic_time() - started);
    }
    g_atomic_int_set(&exchange->done, 1);
    unsigned char wake = 0;
    assert(write(exchange->request[1], &wake, 1) == 1);
    return NULL;
}
static int compare_double(const void *left, const void *right)
{ double a = *(const double *)left, b = *(const double *)right; return (a > b) - (a < b); }
typedef struct { double p50_us, p95_us; } Latency;
static Latency benchmark(gboolean use_notifier)
{
    GMainContext *context = g_main_context_new();
    Exchange exchange = {0};
    MylTkGlibLoop loop = {0};
    Legacy old = {context, FALSE};
    if (!use_notifier) assert(g_main_context_acquire(context)); /* Same owner pin as helper Init. */
    assert(pipe(exchange.request) == 0 && pipe(exchange.response) == 0);
    nonblocking(exchange.request[0]);
    GSource *source = g_unix_fd_source_new(exchange.request[0], G_IO_IN | G_IO_HUP);
    g_source_set_callback(source, G_SOURCE_FUNC(backend_ready), &exchange, NULL);
    g_source_attach(source, context);
    if (use_notifier) assert(MylTkGlibLoopInit(&loop, context));
    else Tcl_CreateEventSource(legacy_setup, legacy_check, &old);
    GThread *thread = g_thread_new("ipc-client", client, &exchange);
    pump(&exchange.done);
    g_thread_join(thread);
    assert(!exchange.failed && exchange.replies == SAMPLES);
    if (use_notifier) { assert(!loop.problem); assert(MylTkGlibLoopDelete(&loop)); }
    else {
        Tcl_DeleteEventSource(legacy_setup, legacy_check, &old);
        Tcl_DeleteEvents(legacy_delete_event, &old);
    }
    g_source_destroy(source); g_source_unref(source);
    close(exchange.request[0]); close(exchange.request[1]);
    close(exchange.response[0]); close(exchange.response[1]);
    if (!use_notifier) g_main_context_release(context);
    g_main_context_unref(context);
    qsort(exchange.us, SAMPLES, sizeof(double), compare_double);
    Latency result = {exchange.us[SAMPLES / 2], exchange.us[(SAMPLES * 95 - 1) / 100]};
    return result;
}

typedef struct { gint done; int calls, fd; gboolean consume; } FdState;
static gboolean got_byte(gint fd, GIOCondition condition, gpointer data)
{
    FdState *state = data;
    unsigned char byte;
    (void)condition;
    assert(Tcl_GetCurrentThread() == owner && read(fd, &byte, 1) == 1);
    state->calls++; g_atomic_int_set(&state->done, 1);
    return G_SOURCE_CONTINUE;
}
static void original_tcl_handler(void *data, int mask)
{
    FdState *state = data;
    (void)mask;
    assert(Tcl_GetCurrentThread() == owner);
    if (state->consume) {
        unsigned char byte;
        assert(read(state->fd, &byte, 1) == 1);
        state->calls++; g_atomic_int_set(&state->done, 1);
    }
}
static gpointer foreign_delete(gpointer data)
{
    MylTkGlibLoop *loop = data;
    assert(!MylTkGlibLoopDelete(loop) && loop->live);
    assert(!MylTkGlibLoopInit(loop, loop->context));
    return NULL;
}
static void fd_contract(void)
{
    GMainContext *context = g_main_context_new();
    MylTkGlibLoop loop = {0};
    int first[2], second[2];
    FdState received = {0}, original = {0};
    assert(pipe(first) == 0);
    nonblocking(first[0]);
    GSource *source = g_unix_fd_source_new(first[0], G_IO_IN | G_IO_HUP);
    g_source_set_callback(source, G_SOURCE_FUNC(got_byte), &received, NULL);
    g_source_attach(source, context);
    assert(MylTkGlibLoopInit(&loop, context));
    GThread *foreign = g_thread_new("foreign-delete", foreign_delete, &loop);
    g_thread_join(foreign);
    for (guint i = 0; i < loop.watches->len; i++) {
        MylTkGlibWatch *watch = g_ptr_array_index(loop.watches, i);
        assert(watch->fd != first[0] && (fcntl(watch->fd, F_GETFD) & FD_CLOEXEC));
    }
    assert(write(first[1], "A", 1) == 1); pump(&received.done);
    assert(received.calls == 1);
    /* Replace a watched fd with a new pipe at the exact same descriptor.
     * The adapter must stop observing the old open-file description. */
    int reused = first[0];
    g_source_destroy(source); g_source_unref(source); close(first[0]);
    assert(pipe(second) == 0);
    if (second[0] != reused) { assert(dup2(second[0], reused) == reused); close(second[0]); second[0] = reused; }
    nonblocking(second[0]);
    received.done = 0;
    source = g_unix_fd_source_new(second[0], G_IO_IN | G_IO_HUP);
    g_source_set_callback(source, G_SOURCE_FUNC(got_byte), &received, NULL);
    g_source_attach(source, context);
    original.fd = second[0];
    Tcl_CreateFileHandler(second[0], TCL_READABLE, original_tcl_handler, &original);
    assert(write(second[1], "B", 1) == 1); pump(&received.done);
    assert(received.calls == 2 && !loop.problem);
    /* Teardown only owns duplicates; an original Tcl handler and fd survive. */
    MylTkGlibQueue(&loop);
    assert(MylTkGlibLoopDelete(&loop) && MylTkGlibLoopDelete(&loop));
    assert(!loop.live && !loop.watches && !loop.context && !loop.queued);
    assert(fcntl(second[0], F_GETFD) >= 0);
    original.consume = TRUE;
    assert(write(second[1], "C", 1) == 1); pump(&original.done);
    assert(original.calls == 1);
    Tcl_DeleteFileHandler(second[0]);
    g_source_destroy(source); g_source_unref(source);
    close(first[1]); close(second[0]); close(second[1]);
    g_main_context_unref(context);
}

typedef struct { MylTkGlibLoop *loop; gint done; int depth, max_depth, calls, glib_timer; } Fair;
static gboolean busy_idle(gpointer data)
{
    Fair *fair = data;
    assert(Tcl_GetCurrentThread() == owner);
    fair->depth++; fair->max_depth = MAX(fair->max_depth, fair->depth); fair->calls++;
    Tcl_DoOneEvent(TCL_ALL_EVENTS | TCL_DONT_WAIT); /* Nested Tcl loop must not reenter GLib. */
    fair->depth--;
    return G_SOURCE_CONTINUE;
}
static gboolean glib_timer(gpointer data)
{ ((Fair *)data)->glib_timer++; return G_SOURCE_REMOVE; }
static gboolean delete_inside_dispatch(gpointer data)
{
    Fair *fair = data;
    assert(MylTkGlibLoopDelete(fair->loop));
    assert(!MylTkGlibLoopInit(fair->loop, g_main_context_default()));
    g_atomic_int_set(&fair->done, 1);
    return G_SOURCE_REMOVE;
}
static void fairness_contract(void)
{
    GMainContext *context = g_main_context_new();
    MylTkGlibLoop loop = {0};
    Fair fair = {.loop=&loop};
    assert(MylTkGlibLoopInit(&loop, context));
    GSource *idle = g_idle_source_new(), *timer = g_timeout_source_new(1);
    g_source_set_callback(idle, busy_idle, &fair, NULL); g_source_attach(idle, context);
    g_source_set_callback(timer, glib_timer, &fair, NULL); g_source_attach(timer, context);
    Tcl_TimerToken tcl_timer = Tcl_CreateTimerHandler(10, mark_done, &fair.done);
    pump(&fair.done);
    (void)tcl_timer; /* Fired and deleted by Tcl. */
    assert(fair.calls > 0 && fair.max_depth == 1 && fair.glib_timer == 1 && !loop.problem);
    g_source_destroy(idle); g_source_unref(idle); g_source_unref(timer);
    fair.done = 0;
    idle = g_idle_source_new();
    g_source_set_callback(idle, delete_inside_dispatch, &fair, NULL); g_source_attach(idle, context);
    pump(&fair.done);
    assert(!loop.live && !loop.context && !loop.active_event);
    g_source_unref(idle); g_main_context_unref(context);
}

static gpointer thread_exit_contract(gpointer unused)
{
    (void)unused;
    Tcl_Interp *interp = Tcl_CreateInterp();
    GMainContext *context = g_main_context_new();
    MylTkGlibLoop loop = {0};
    assert(MylTkGlibLoopInit(&loop, context));
    MylTkGlibQueue(&loop);
    assert(loop.queued);
    Tcl_DeleteInterp(interp);
    Tcl_FinalizeThread(); /* Real Tcl thread exit hooks cancel queued events. */
    assert(!loop.live && !loop.queued && !loop.watches && !loop.context);
    g_main_context_unref(context);
    return NULL;
}

typedef struct { GMainContext *context; gint done; } Invocation;
static gboolean invoked_on_owner(gpointer data)
{
    assert(Tcl_GetCurrentThread() == owner);
    g_atomic_int_set(&((Invocation *)data)->done, 1);
    return G_SOURCE_REMOVE;
}
static gpointer request_invoke(gpointer data)
{
    Invocation *request = data;
    g_main_context_invoke(request->context, invoked_on_owner, request);
    return NULL;
}
static void invocation_contract(void)
{
    GMainContext *context = g_main_context_new();
    MylTkGlibLoop loop = {0};
    Invocation request = {context, 0};
    assert(MylTkGlibLoopInit(&loop, context));
    assert(loop.timeout_ms == -1 && loop.timer == NULL); /* FD sleep, no polling timer. */
    assert(MylTkGlibLoopInit(&loop, context));
    GThread *thread = g_thread_new("invoke-owner", request_invoke, &request);
    g_thread_join(thread);
    assert(!g_atomic_int_get(&request.done)); /* Never executed inline in worker. */
    pump(&request.done);
    assert(MylTkGlibLoopDelete(&loop));
    assert(MylTkGlibLoopInit(&loop, context)); /* Same owner/context may restart cleanly. */
    assert(MylTkGlibLoopDelete(&loop));
    g_main_context_unref(context);
}

typedef struct { MylTkGlibLoop *loop; GMainContext *context; gint done, nested; int entered; } Modal;
static gboolean modal_reply(gpointer data)
{
    Modal *modal = data;
    assert(Tcl_GetCurrentThread() == owner && modal->loop->dispatch_depth >= 2);
    g_atomic_int_set(&modal->nested, 1);
    return G_SOURCE_REMOVE;
}
static gboolean modal_wait(gpointer data)
{
    Modal *modal = data;
    assert(++modal->entered == 1);
    GSource *reply = g_timeout_source_new(1);
    g_source_set_callback(reply, modal_reply, modal, NULL);
    g_source_attach(reply, modal->context);
    pump(&modal->nested); /* Simulates an ATK action opening a modal Tcl wait. */
    g_source_unref(reply);
    g_atomic_int_set(&modal->done, 1);
    return G_SOURCE_REMOVE;
}
static void modal_contract(void)
{
    GMainContext *context = g_main_context_new();
    MylTkGlibLoop loop = {0};
    Modal modal = {.loop=&loop, .context=context};
    assert(MylTkGlibLoopInit(&loop, context));
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, modal_wait, &modal, NULL);
    g_source_attach(source, context);
    pump(&modal.done);
    assert(modal.entered == 1 && modal.nested && !loop.problem);
    g_source_unref(source);
    assert(MylTkGlibLoopDelete(&loop));
    g_main_context_unref(context);
}

typedef struct { GSource source; GPollFD poll; gboolean closed; gint *done; } ClosingSource;
static gboolean closing_prepare(GSource *source, gint *timeout)
{
    ClosingSource *closing = (ClosingSource *)source;
    *timeout = -1;
    if (!closing->closed) { assert(close(closing->poll.fd) == 0); closing->closed = TRUE; }
    return FALSE;
}
static gboolean closing_check(GSource *source)
{ return (((ClosingSource *)source)->poll.revents & G_IO_NVAL) != 0; }
static gboolean closing_dispatch(GSource *source, GSourceFunc callback, gpointer data)
{
    (void)callback; (void)data;
    g_atomic_int_set(((ClosingSource *)source)->done, 1);
    return G_SOURCE_REMOVE;
}
static void stale_snapshot_contract(void)
{
    static GSourceFuncs functions = {closing_prepare, closing_check, closing_dispatch, NULL, NULL, NULL};
    GMainContext *context = g_main_context_new();
    MylTkGlibLoop loop = {0};
    gint done = 0;
    int channel[2]; assert(pipe(channel) == 0);
    ClosingSource *closing = (ClosingSource *)g_source_new(&functions, sizeof(*closing));
    closing->poll.fd = channel[0]; closing->poll.events = G_IO_IN; closing->done = &done;
    g_source_add_poll((GSource *)closing, &closing->poll);
    g_source_attach((GSource *)closing, context);
    assert(MylTkGlibLoopInit(&loop, context));
    assert(loop.live && !loop.problem && loop.stale_fd_retries == 1);
    pump(&done); /* GLib itself consumes NVAL and removes the closed source. */
    assert(!loop.problem);
    assert(MylTkGlibLoopDelete(&loop));
    g_source_unref((GSource *)closing); close(channel[1]);
    g_main_context_unref(context);
}

int main(int argc, char **argv)
{
    (void)argc;
    Tcl_FindExecutable(argv[0]); /* Do not call Tcl_Init or load user scripts. */
    Tcl_Interp *interp = Tcl_CreateInterp();
    assert(interp != NULL);
    owner = Tcl_GetCurrentThread();
    fd_contract(); fairness_contract(); invocation_contract(); modal_contract(); stale_snapshot_contract();
    GThread *exit_thread = g_thread_new("tcl-exit-contract", thread_exit_contract, NULL);
    g_thread_join(exit_thread);
    Latency old = benchmark(FALSE), current = benchmark(TRUE);
    printf("{\"passed\":true,\"result\":\"GLib/Tcl notifier contract: passed\","
           "\"checks\":{\"owner_thread_dispatch\":true,\"foreign_thread_rejected\":true,"
           "\"dynamic_fd_and_same_number_reuse\":true,\"owned_duplicates_cloexec\":true,"
           "\"teardown_preserves_original_fd_and_handler\":true,\"queued_event_cleanup\":true,"
           "\"glib_and_tcl_timer_fairness\":true,\"nested_loop_no_reentry\":true,"
           "\"delete_inside_dispatch\":true,\"thread_exit_queued_event_cleanup\":true,"
           "\"worker_invoke_owner_thread\":true,\"idle_wait_has_no_poll_timer\":true,"
           "\"idempotent_init_and_restart\":true,\"nested_modal_glib_service\":true,"
           "\"stale_query_fd_recovers\":true,"
           "\"equal_ipc_samples_and_payload\":true},"
           "\"versions\":{\"tcl\":\"%s\",\"glib\":\"%u.%u.%u\"},"
           "\"benchmark\":{\"scope\":\"synthetic_pipe_roundtrip_glib_tcl_not_atspi\","
           "\"samples_per_mode\":%d,\"payload_bytes\":1,\"unit\":\"microseconds\","
           "\"legacy_polling_10ms\":{\"samples\":%d,\"p50\":%.3f,\"p95\":%.3f},"
           "\"fd_notifier\":{\"samples\":%d,\"p50\":%.3f,\"p95\":%.3f}}}\n",
           TCL_PATCH_LEVEL, glib_major_version, glib_minor_version, glib_micro_version,
           SAMPLES, SAMPLES, old.p50_us, old.p95_us, SAMPLES, current.p50_us, current.p95_us);
    Tcl_DeleteInterp(interp);
    Tcl_Finalize();
    return 0;
}
