# Accessibility validation — 2026-09-29

## Implemented and automatically checked

- Every rounded action is reachable with `Tab` and activates with `Enter` or
  `Space`; disabled actions cannot be invoked from the keyboard.
- Keyboard focus is drawn with the current foreground/accent color rather than
  depending only on hover state.
- `Ctrl+K` and `Ctrl+F` focus search; `Alt+1` through `Alt+5` open Library,
  Import, Reviews, Activity, and Settings; `F2`, `F5`, and `Ctrl+Z` retain their
  existing actions.
- The three icon-only library controls have translated accessible names and
  translated tooltips. Navigation tooltips are also shown on keyboard focus.
- Native entries, comboboxes, tree rows, and scrollbars remain in the tab order.

## Manual validation still required on the packaged Windows build

1. Navigate every page without a mouse and verify that focus is never lost or
   trapped, including dialogs and metadata review.
2. Use Windows Narrator and NVDA to verify reading order, control names, state,
   selected rows, and progress changes.
3. Check light, dark, Windows high-contrast, 125%, 150%, and 200% scaling.
4. Verify that color is not the only signal for selection, errors, review state,
   or disabled actions.
5. Verify the installer and first-run dialogs at keyboard-only and 200% scaling.

## Known toolkit limit and migration gate

`RoundedButton` is a focusable custom Tk canvas. It now has a keyboard contract,
visible focus, an internal accessible name, and tooltip text, but Tk does not
guarantee that a canvas is exposed to every Windows screen reader as a native
button. This must be tested on the packaged executable. If Narrator or NVDA does
not announce role, name, state, and focus consistently, replace these controls
with styled native buttons or activate the previously documented PySide6/Qt UI
prototype. The application must not claim screen-reader conformance until that
manual check passes.
