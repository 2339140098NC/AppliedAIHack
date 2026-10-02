# Handoff: Sapini Case Workspace (firm / provider views)

## Overview
A single-matter workspace for *Sapini v. Ferrara & Metro-North* (Index 160000/2024). Firm users scan a timeline, compare conflicting facts, work a to-do list of validation findings, and read the cited PDF page. A **Firm / Provider** toggle switches to a sanitized view for one chosen treating provider: they see only their own records and a short clinical summary. Firm-only items are removed entirely, so the provider can't tell anything was withheld.

## About the design files
`Case Workspace v2.dc.html` is a **design reference built in HTML**. It's a clickable prototype that shows the intended look and behavior; it is not production code. Rebuild it in the target stack, which per the project brief is **Python + FastAPI + Jinja templates returning HTMX fragments**, backed by Pydantic models and a SQLite JSON document store. To view it, open the file in a browser from this folder; it loads `support.js` and `_ds/.../styles.css` by relative path.

- Template markup is between `<x-dc>` and `</x-dc>`. `{{ path }}` holes, `<sc-for>` loops and `<sc-if>` conditionals map directly to Jinja `{{ }}`, `{% for %}` and `{% if %}`.
- The logic is the `class Component` at the bottom of the file. `renderVals()` is the view model; treat it as the spec for what each template receives.
- The constants at the top of the logic (`DOCS`, `EVENTS`, `GROUPS`, `TODOS`, `PFACTS`, `EXTRA`) are **mock data**. Page numbers (other than OCA-960 at p. 241), page ranges within each file and quote wording are invented. The real values come from Gemini extraction (segments and facets) and the validation functions.

## Fidelity
**High fidelity.** Final colors, type, spacing and interactions. All values come from the Industry design system in `_ds/.../styles.css`; reuse that stylesheet directly. It is plain CSS with no build step and works fine with HTMX.

## Global layout
- Full-viewport app: `height:100vh`, column flex, `overflow:hidden`; the panes scroll independently.
- Page background: `--color-bg` #f2f2f3 with a 28px blueprint grid (two 1px linear-gradients at accent #5980a6, 9% opacity).
- Rows, top to bottom: **Header** → **Provider banner** (provider view only) → **Tab bar** → **Main area**.
- Main area has two layouts, switched by the header "Layout" control (prop `layout`):
  - **A · Split** (default): CSS grid `minmax(0,1fr) minmax(380px,40%)`. Content on the left, PDF viewer always open on the right. The divider is 1px `--color-text`.
  - **B · Drawer**: content full width, inner `max-width:1040px`, centered. The PDF viewer is an absolute right drawer, `width:min(560px,92%)`, `--shadow-lg`, 1px left border. It opens when you click any source and closes with the X.

## Screens / views

### Header (background `--color-accent-900` #1d2d3d, text `--color-bg`)
- **Top row** (`padding:16px 24px 14px`, flex-wrap, gap 20px):
  - Monogram box: 38×38, 1px `--color-accent-400` border, "JS" in Barlow Condensed 600 15px, `--color-accent-300`.
  - Kicker "MATTER · PERSONAL INJURY": 10px, letter-spacing .18em, uppercase, `--color-accent-300`.
  - Title "SAPINI V. FERRARA & METRO-NORTH": Barlow Condensed 600, 30px, line-height 1, uppercase.
  - "VIEW AS" control (`.seg`, border `--color-accent-700`) with options **Firm | Provider**. In provider mode, a provider `<select class="input">` appears (background `--color-accent-800`, border `--color-accent-600`) listing Montefiore Nyack Hospital, Advanced Rockland Chiropractic, SportsCare Physical Therapy and New Horizon Surgical Center.
  - "LAYOUT" control with options **A · Split | B · Drawer**. This is a design-review toggle; drop it in production once a layout is chosen.
- **Fact plate**: a grid `repeat(auto-fit,minmax(150px,1fr))` with a 1px `--color-accent-800` top border and dividers between cells. Each cell has a label (10px, .16em, uppercase, `--color-accent-400`) over a value (Barlow Condensed 500, 18px).
  - Cells: Client · Index · Accident · Files ("15 PDFs · 662 pp.") · Open to-dos.
  - The to-do cell has a 7×7 `--color-accent-300` square that pulses (`@keyframes pulse` 1.6s opacity 1→.35) while the count is above 0.

### Provider banner (provider view only)
A diagonal hatch background: `repeating-linear-gradient(-45deg, accent-200 0 10px, accent-100 10px 20px)`, text `--color-accent-900`, bottom border `--color-accent-400`, padding 10px 24px, 14px text, eye icon. Copy: "**{Provider}** sees exactly this screen: their own records for Justin Sapini, nothing else."

### Tab bar
- Background `--color-bg`, bottom border 1px `--color-text`, padding 0 24px.
- Tabs are Barlow Condensed 600, 20px, uppercase, .04em spacing.
  - Each has a number prefix ("01", "02", "03") in Barlow 11px 600 accent.
  - Inactive: `--color-neutral-700`. Active: `--color-text` with a 3px `--color-accent` bottom border.
- Firm tabs: Timeline · Evidence · To-do (with a `.tag-accent` count of open items). Provider tabs: Timeline · My records.
- Firm view only, at the right: status text (12px neutral-700), then **Extract PDFs** and **Sync Clio** (`.btn-secondary`, 13px), then **Run validations** (`.btn-primary.blueprint` with 4 corner marks). Each button posts its action, then swaps the to-do list and status text in place via HTMX.

### 01 Timeline
- Grouped by year, **newest first**. Events without a date go in a final "Undated" group.
- **Year header**: the year in Barlow Condensed 600, 52px, line-height .85, outlined (`color:transparent; -webkit-text-stroke:1px var(--color-accent)`). An event count (11px uppercase, neutral-700) is right-aligned. Bottom border 1px `--color-text`, padding 26px 10px 6px.
- **Event row**: grid `52px 18px minmax(0,1fr) auto`, gap 14px, padding 14px 10px, bottom border 1px `--color-divider`. Whole row is clickable; hover background `--color-neutral-200`. Selected: background `--color-accent-200` plus inset 3px left accent.
  1. **Date**: month (11px, .1em, 600, accent-700) over day (Barlow Condensed 600, 30px). A month-only date shows "—" for the day; undated shows "?".
  2. **Spine**: a 1px `--color-accent-400` vertical line through all rows, with an 11×11 node at top 20px.
     - Firm-only event: filled `--color-accent-900` square.
     - Shared with a provider: `--color-bg` square with an accent border.
     - Conflict: the node is rotated 45° into a diamond.
     - Selected: adds a 4px `--color-accent-300` ring.
  3. **Body**: kind (11px uppercase neutral-700, plus " · Provider" in firm view), label (16px 500), optional sub line (13px neutral-800), then a source link with a file icon (12px accent-700, e.g. "Bill of particulars · p. 3").
  4. **Flags** (firm view only), stacked and right-aligned:
     - Conflict: `.tag` filled accent-900, text "≠ Conflict".
     - Sensitive: `.tag-neutral` with a 1px neutral-700 border.
     - Incomplete: `.tag-outline` with a dashed border and custom text such as "Blank DOB" or "Dates not extracted".
     - Visibility: lock icon + "Firm only", or eye icon + "Shared with {Provider}".
- Clicking a row opens the cited page in the viewer and highlights the quote.

### 02 Evidence (firm only)
- Header: "Evidence" (Barlow Condensed 22px) and the subline "Every fact links to the page it came from. Disagreements stay visible." On the right, a `.seg` with **Compared | All facts**.
- **Compared** (default): a grid `repeat(auto-fill,minmax(300px,1fr))`, gap 22px. One `.blueprint` card with 4 corner marks per comparison group, transparent, padding 16px 18px.
  - Card header: title (Barlow Condensed 19px) and a status tag: ≠ Conflict, Incomplete (dashed), Sensitive, ✓ Consistent (`.tag-accent`) or One source (`.tag-neutral`).
  - Value rows: grid `22px 1fr`, top border divider.
    - Letter box: 22×22. Conflict groups use accent-900 fill with bg text; other groups use a 1px accent-400 border with accent-700 text.
    - Value: 16px 500. A blank value renders as italic "Left blank" in neutral-700.
    - Source links follow the value.
  - Optional note: 12px neutral-700.
- **All facts**: a `.table` with columns Fact · What the page says · Source · Who can see it. Clicking a row opens its source.

### 03 To-do (firm only)
- Header "To-do" and summary text: "{n} of {total} still open. Click a source to see the page; tick the box when it’s handled."
- **Stat plate**: a `.blueprint` grid of 3 equal cells. Each shows a number (Barlow Condensed 600, 56px) over a label (11px, .14em, uppercase). The first cell, "Before sharing", is filled accent-900 with bg text; the other two sit on `--color-bg`. Counts include open items only.
- Sections, each with a title (Barlow Condensed 17px, .06em, uppercase), a subline, and a 1px `--color-text` rule:
  - **Before sharing anything**: severity `sensitive`.
  - **Facts that disagree**: severity `conflict`.
  - **Missing or blank**: severity `incomplete`.
- **Item row**: grid `24px 1fr auto`, padding 14px 4px.
  - Checkbox: a 20×20 square. Unchecked: 1px neutral-600 border. Checked: accent fill with a check icon.
  - Title (15px 500) over detail (13px neutral-800). When done, the text is struck through at 50% opacity.
  - A `.btn-ghost` source button (e.g. "Med. bundle 1 · p. 241") opens the page.

### 02 My records (provider only)
- **"What your records show"**: a `.blueprint` list. Rows use grid `160px 1fr auto`: label, value (16px 500), and a page number relative to the provider's own document.
- **"Your documents"**: one `.blueprint` row per provider-owned segment, with a file icon, the segment label, a page count and an **Open** button.

### PDF viewer
- **Header**: title (Barlow Condensed 19px) over the file name (11px, single line with ellipsis). Provider view replaces these with the segment name and "{Provider} · Justin Sapini". The drawer layout adds an X button.
- **"What's in this file"** (firm only, files with more than one segment): horizontally scrolling chips, one per segment, showing the label and page range. The active chip is filled accent with bg text; clicking a chip jumps to that segment's first page. This makes clear that page 1 of a bundle is not the start of the chart.
- **Toolbar**: prev/next icon buttons (30×30) and "Page X of N". Provider view counts pages relative to the segment and can't navigate outside it. A `.tag-accent` on the right shows the current segment.
- **Page stage**: background accent-900 with a 28px accent-800 grid, padding 28px 22px, `align-items:flex-start`. It scrolls.
- **Page sheet**: `max-width:440px`, `aspect-ratio:8.5/11`, background neutral-100, `--shadow-lg`, padding 30px 34px.
  - Firm view only: a NYSCEF banner at 9px ("FILED: NEW YORK COUNTY CLERK" and "NYSCEF DOC. NO. n · INDEX NO. x").
  - Segment heading: 10px uppercase.
  - Gray placeholder text lines.
  - Every cited quote on that page is highlighted: accent-100 background, or accent-300 with a 1px accent-700 outline when it's the active citation.
  - A redacted span renders as a 52×12 black bar, with any visible trailing digits after it. Struck text (tracked changes) renders with line-through.
  - Page number at the bottom center.
  - **In production, replace the mock sheet with PDF.js rendering of the real page, and draw the highlight over the quote's text bounds.**
- Scanned files show the footnote "Scanned page, no text layer. Facts were read from the page image."

## Sanitization rules (provider view)
These must be enforced on the server. The query parameter `?view=provider&provider=<id>` filters data; the templates don't just hide it.
- Timeline: only events whose `vis == provider_id`, plus a "Date of injury" event drawn from that provider's own note. No conflict, sensitive or incomplete flags, no visibility labels, no other provider names.
- Source labels use the segment name and a relative page, e.g. "Emergency department note · p. 2". **Never** show bundle names, absolute bundle page numbers, NYSCEF banners or index numbers.
- Viewer: restricted to the provider's own segments. Any request for another page is redirected to that provider's first segment.
- Highlights: only quotes from facets visible to that provider.
- Hidden entirely: Evidence, To-do, firm action buttons, the OCA-960, partial SSN, addresses not on the provider's own chart, defense IMEs, damages, Medicaid/SSD/no-fault, insurance and employee identifiers, pleadings, discovery and the draft complaint.
- Never display a count or placeholder for hidden items.

## Interactions and state
| State | Values | Notes |
|---|---|---|
| `view` | `firm` / `provider` | Query parameter. Switching to provider resets the tab to Timeline if it was on Evidence or To-do. |
| `provider` | montefiore, haggerty, sportscare, newhorizon | Changing it resets the viewer to that provider's first segment. |
| `tab` | timeline, evidence, todo, records | |
| `layout` | split / drawer | Design review only. |
| `viewer` | {doc, page, quote} | Set by any source click. Use `hx-get` to the viewer fragment with `hx-target="#viewer"`. |
| `selected` | event, group or to-do id | Highlights the originating row or card. |
| `ev_mode` | grouped / all | |
| `done` | set of to-do ids | Persist as a `resolved` flag on the finding document. Re-running validations should keep resolution for unchanged finding codes. |

Hover states use the design system: `.btn` and `.seg` built-ins, row hover neutral-200. Keyboard focus is a 2px accent outline (in the stylesheet).

## Data mapping (to the brief's store)
- `timeline_event` → event row: date, label, kind, facet ids, evidence[0], sensitivity, provider.
- `group` → evidence card: facet_key title, status conflict / consistent / incomplete, rows of distinct values with their evidence.
- `facet` → "All facts" row and the provider's "What your records show".
- `validation` → to-do item: the severity picks the section; the message is split into title and detail; evidence feeds the source button.
- `segment` → viewer chips and the provider's "Your documents".
- Clio `communication` documents are not shown yet. When they are, add them as firm-only timeline rows with kind Phone, Email, Note or Message.

## Design tokens (from `_ds/.../styles.css`)
- **Ground and text**: bg #f2f2f3, surface #e9e9ea, text #1d1f20, divider = text at 16%.
- **Accent ramp**: 100 #eef6ff · 200 #d6ebff · 300 #b5d9fd · 400 #94bce3 · 500 #749dc4 · base #5980a6 · 600 #597ea3 · 700 #416180 · 800 #2c455d · 900 #1d2d3d.
- **Neutral ramp**: 100 #f5f5f8 · 200 #e7e7ea · 300 #d4d4d7 · 400 #b7b7ba · 500 #98989b · 600 #7a7a7d · 700 #5d5d60 · 800 #424244 · 900 #2b2b2d.
- **Fonts**: Barlow Condensed 500/600 for headings, Barlow 400/500/600 for body (Google Fonts).
- **Spacing**: 3.4, 6.8, 10.2, 13.6, 20.4, 27.2px (`--space-1…8`).
- **Radius**: 0 on all components (blueprint style).
- **Shadows**: sm `0 1px 2px` / md `0 3px 10px` / lg `0 12px 32px`, using #2b2b2d at 14 / 16 / 22%.
- **Blueprint frame**: `.blueprint` plus `<i class="corner tl|tr|bl|br">`, which draws "+" registration marks at the corners.
- Mono palette: severities are told apart by fill, border style, shape and icon, never by an extra hue.

## Assets
- **Icons**: Lucide at stroke-width 1.5, inlined as SVG (file-text, lock, eye, chevron-left/right, x, check).
- No images.

## Files
- `Case Workspace v2.dc.html`: the prototype, with markup and the view-model logic.
- `support.js`: the prototype runtime. Needed only to open the HTML; don't port it.
- `_ds/industry-b52e7bd3-0c35-4c59-aaa0-080f24e5e961/styles.css`: the design-system stylesheet. Copy it into `static/`.
- `_ds/.../_ds_bundle.js`: the design-system script bundle, loaded only by the prototype.
