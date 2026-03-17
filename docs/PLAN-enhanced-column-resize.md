# Plan: Enhanced Column Resize (Plan B)

## Status: Not Started

## Design Spec

### Problem
The current column resize implementation is functional but lacks polish:
- No double-click-to-auto-fit
- No visual guide line during drag
- No way to reset column widths to defaults
- Resize handle hover zone is only 6px (hard to grab)
- No max-width constraint (columns can grow infinitely)
- No proportional resize mode (Shift+drag)
- No keyboard-based resizing

### Solution
Enhance the existing resize system in `dashboard.js` and `main.css` with 7 improvements:

#### 1. Double-click to auto-fit
- On `dblclick` of resize handle, measure the max content width of that column across all visible rows
- Set column width to `max(minWidth, contentWidth + padding)`
- Uses a temporary off-screen `<span>` to measure text widths

#### 2. Visual guide line during drag
- Show a vertical blue line at the current drag position while resizing
- Implemented as a fixed-position `<div>` that follows the mouse X during drag
- Created/destroyed in `startResize`/`stopResize`

#### 3. Reset column widths button
- Add a "重置列宽" button at the bottom of the column settings dropdown
- Resets all column widths to their original defaults (stored as `defaultWidth` on each column)
- Preserves visibility settings

#### 4. Wider resize handle hover zone
- Increase invisible hover zone from 6px to 14px (with only 2px visible indicator)
- Use `::before` pseudo-element or padding for larger hit area

#### 5. Max-width constraints
- Add `maxWidth` property to each column definition
- Enforce in `doResize()`: `Math.min(col.maxWidth, Math.max(col.minWidth, newWidth))`
- Default max-widths: narrow cols 200px, medium 400px, wide 600px

#### 6. Proportional resize (Shift+drag)
- When holding Shift during drag, the neighboring column (right side) shrinks by the same delta
- Keeps total table width constant
- Check `event.shiftKey` in `doResize()`

#### 7. Keyboard resize
- When a column header is focused, `←`/`→` arrow keys adjust width by 10px (or 50px with Shift)
- Add `tabindex="0"` and `@keydown` handler to `<th>` elements

### Files to Modify
| File | Changes |
|------|---------|
| `src/frontend/static/js/dashboard.js` | Add `maxWidth`/`defaultWidth` to columns, enhance resize methods, add auto-fit/reset/keyboard methods |
| `src/frontend/static/css/main.css` | Wider resize handle, guide line styles |
| `src/frontend/dashboard.html` | Add reset button in column settings dropdown, add `tabindex`/`@keydown` on `<th>` elements |

## Implementation Stages

### Stage 1: Column config enhancements + wider handle
**Goal**: Add `maxWidth`/`defaultWidth` fields, widen resize handle
**Files**: `dashboard.js`, `main.css`
**Changes**:
- Add `defaultWidth` (copy of initial `width`) and `maxWidth` to each column in `columns[]`
- Update `doResize()` to enforce `maxWidth`
- Widen `.resize-handle` from 6px to 14px with padding trick

### Stage 2: Double-click auto-fit
**Goal**: Double-click a resize handle to auto-size column to content
**Files**: `dashboard.js`, `dashboard.html`
**Changes**:
- Add `autoFitColumn(columnKey)` method that measures content width
- Add `@dblclick.stop="autoFitColumn('columnKey')"` to each resize handle in HTML

### Stage 3: Visual guide line
**Goal**: Show vertical blue line during drag
**Files**: `dashboard.js`, `main.css`
**Changes**:
- Create/destroy a `.resize-guide-line` element in `startResize()`/`stopResize()`
- Position it at `event.clientX` in `doResize()`

### Stage 4: Reset button + proportional resize + keyboard
**Goal**: Complete remaining features
**Files**: `dashboard.js`, `dashboard.html`, `main.css`
**Changes**:
- Add `resetColumnWidths()` method
- Add reset button in column settings dropdown (after the column list)
- Add Shift+drag proportional resize in `doResize()`
- Add `resizeColumnByKeyboard(event, columnKey)` and wire up `@keydown` on `<th>`

## Test Cases

### Manual Verification
1. Drag a resize handle → column resizes, respects min/max width
2. Double-click resize handle → column auto-fits to content width
3. Blue guide line appears during drag, disappears on release
4. Click "重置列宽" → all columns return to original widths
5. Hold Shift while dragging → neighboring column shrinks proportionally
6. Focus a column header with Tab, press ←/→ → column width changes by 10px
7. Press Shift+←/→ → column width changes by 50px
8. Resize preferences persist after page reload (localStorage)
9. Resize handle is easy to grab (wider hit area)

## Acceptance Criteria
- [ ] All 7 features implemented and working
- [ ] Existing resize behavior preserved (no regressions)
- [ ] Column widths still persist in localStorage
- [ ] No visual glitches during resize drag
- [ ] Works in Chrome, Firefox, Safari
