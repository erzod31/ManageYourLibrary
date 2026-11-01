# Manage Your Library: project guidance

Before making substantial changes, read `docs/PROJECT_CONTEXT_2026-09-28.md`. It
contains the durable handoff reconstructed from the related ChatGPT
conversations and the master continuity report.

## Non-negotiable safety rules

- Protect the user's books before optimizing speed or convenience.
- Never permanently delete a book merely because it appears to be a duplicate.
  Ambiguous or discarded files must remain recoverable through quarantine.
- Revalidate the source file and its current hash or file signature immediately
  before moving, replacing, or quarantining it.
- Do not treat matching titles as proof that volumes, editions, translations,
  or versions are interchangeable.
- A result requiring manual review must not trigger automatic rename, replace,
  or discard operations.
- Failed undo or partial operations must remain recorded and recoverable.
- Preview operations must not modify the original file.
- Cleanup and upgrades must preserve the catalog, configuration, quarantine,
  journal, pending plans, backups, history, and confirmed human corrections.
- OCR of book contents must remain local unless the user explicitly changes
  this privacy policy.

## Verification and provenance

- Treat claims from the 2026-09-28 ChatGPT work as handoff evidence, not proof
  that the corresponding code exists in this checkout.
- Inspect the current working tree before modifying it and preserve unrelated
  user changes.
- Do not call a feature implemented until it has been located in this checkout
  and exercised by an appropriate test.
- Do not report historical test counts or benchmarks as current results.
- Do not claim an installer is validated merely because it was built. Record
  exactly which source revision, tests, dependencies, and Windows checks were
  actually used.
- Generated executables belong in release artifacts, not in Git history, unless
  the repository policy is intentionally changed.
- Every delivery must include a usable Windows installer, built with the existing
  Windows packaging scripts. Preserve user data on upgrades and report exactly
  which installer checks were performed.

## Preferred direction

- Evolve the existing Python/Tkinter application incrementally; do not perform
  a wholesale rewrite without a demonstrated need.
- Keep automatic identity decisions explainable and based on provenance-aware
  evidence. Uncertainty should result in review, not destructive action.
- Prefer durable, resumable plans and atomic writes for critical state.
- Use the existing platform build entry points and avoid contradictory build
  paths.

## Permanent in-app update requirement (DG-0020)

- Every distributed client/platform must provide updating of its own installed
  application from its UI: check, show current/available version, download and
  verify the matching package, request confirmation, hand off to the native
  installer/store/service and support reopening. A download link, catalog
  refresh or page reload alone is not an application updater.
- Preserve product/AppId/package identity, signing/update identity, library,
  configuration, quarantine, journal, plans, backups and human corrections.
  Reject unauthorized downgrades, other products/platforms, altered downloads
  and invalid expected signatures. Never bypass OS/store confirmations.
- Use a real/configurable trusted channel. Clearly distinguish implemented
  flows, simulated installer tests and actually installed updates; document
  missing distribution/signing/channel dependencies and the initial manual
  transition for older binaries without an updater.
- Shared-Windows validation must not execute real installers, updaters or
  uninstallers, or alter the user's registry, shortcuts or ordinary profiles.
  Use mocks/fake launchers, extraction and temporary profiles. Test folders do
  not grant permission to run real installers. Do not change network services,
  publish or activate production versions as part of updater validation.
