# UI toolkit decision gate — 2026-09-29

## Decision

Keep the Python/Tkinter interface for the next implementation cycle. Do not add
PySide6 yet. The core remains independent enough to support a later read-only Qt
prototype if a measured trigger is reached.

## Evidence from this checkout

The reproducible baseline in `performance_baseline_2026-09-29.json` was run on
Windows 11, Python 3.12.10, AMD64. At 50,000 synthetic books:

- prepared catalog view: 1,753.465 ms once per catalog replacement;
- search: 5.274 ms p50 and 9.571 ms p95;
- format filter: 2.639 ms p50 and 4.720 ms p95;
- full prepared result: 1.228 ms p50 and 1.409 ms p95;
- prepared-view Python allocation peak: 77.039 MiB;
- cover widgets remain bounded to 30 visible cards and resizing repositions the
  existing cards rather than rebuilding them.

All measured interactions are below the 100 ms migration threshold. A separate
source startup baseline records import/smoke latency; installed-window startup,
native RSS, sash dragging, and screen-reader behavior still require measurement
on the packaged executable.

## Triggers that would change the decision

Create a read-only PySide6 Library screen prototype only if one of these is
demonstrated after reasonable Tk optimization:

1. search or filtering exceeds 100 ms p95 at the target catalog size;
2. installed resize/scroll interaction has visible stalls with the 30-card cap;
3. Narrator or NVDA cannot announce custom buttons reliably;
4. native high-contrast, touch, complex drag-and-drop, or multiwindow needs
   become product requirements;
5. custom Canvas maintenance dominates two consecutive feature cycles.

The prototype must never move, rename, replace, or quarantine books. It should
consume the same `LibraryViewIndex` in read-only mode and be compared on startup,
p50/p95 interaction latency, native RSS, live widget count, keyboard operation,
and screen-reader output before any migration decision.
