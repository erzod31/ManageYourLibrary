# Project guidance

Read `docs/PROJECT_CONTEXT_2026-09-28.md` before substantial changes.

- Preserve books, catalog, settings, quarantine, journals, plans, backups, history
  and confirmed metadata during cleanup and upgrades.
- Never permanently discard books based on guesses or matching titles.
- Revalidate files before moving or replacing them. Ambiguity requires review.
- Preview must not modify originals. Failed Undo must remain recoverable.
- OCR and optional AI remain local; do not upload book contents.
- Inspect and preserve working-tree changes. Verify current code and tests.
- Distinguish automated checks from manual installed-UI/upgrade validation.
- Use existing platform builds. Executables are Release assets, not Git files.
- Distribute no personal state, real-world names, personal emails or local
  profile paths. Public project attribution to GitHub owner `erzod31` is intentional.
- Commit author and committer must use `erzod31` and the GitHub-provided private
  address `114614289+erzod31@users.noreply.github.com`; configure this locally,
  never change global Git identity or rewrite published history without approval.
- Evolve Python/Tkinter incrementally without unsupported rewrites.
