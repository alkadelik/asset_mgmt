# Mobile app mockup — functional spec

This describes the behavior of a lo-fi interactive prototype for a technician-facing
mobile app in a CMMS (computerized maintenance management system). It covers three
screens, two independent "tracks" a base station can be on (routine maintenance and
alarms), and the state/locking rules that govern them. This is a functional spec of
*behavior*, not a UI style guide — layout, colors, and components are for you to design;
what matters is the states, transitions, and rules below.

## Core concepts

**Base station** — a physical site (e.g. a cell tower site) identified by an ID
(e.g. `OY0735`), with metadata: site classification, client, manager.

**Two independent tracks per base station:**
1. **Maintenance track** — routine, scheduled preventive maintenance. Lifecycle:
   not started → in progress → ended → submitted.
2. **Alarm track** — a triggered fault/alert at that base station. Lifecycle:
   triggered → resolved. A base station can have an alarm track and a maintenance
   track active at the same time, entirely independently — one does not block or
   depend on the other.

Not every base station has both tracks on a given day. A station might have only
routine maintenance, only an alarm, both, or (after being fully processed) neither
visible.

**Assets** — a base station has a list of assets (e.g. generators, AC units,
rectifiers). Each asset has:
- A **checklist** — a fixed list of inspection tasks (e.g. "Check oil level",
  "Inspect fuel lines"), each independently checkable.
- A **conditions** list — "select all that apply" tags (e.g. "Leaking", "Corroded",
  "Noisy") for flagging observed physical conditions. Independent of the checklist;
  selecting a condition does not itself block the asset from being marked done.
- An **outstanding issues** list — free-form entries a technician adds when something
  needs to be fixed later (see "Outstanding issues" section below). Also independent
  of the checklist and conditions.
- A derived **done** flag — see "When an asset becomes 'done'" below. Importantly,
  the checklist represents that the asset **has been inspected**, not that any
  problem found was fixed. An asset can be fully checked off and "done" while also
  having open outstanding issues against it.

## Screen 1 — base station list

Two tabs: **Routine** and **Alarms**. (There is no History tab — see "Daily cutoff"
below for why.)

Above the tabs, two summary cards, scoped to **the logged-in technician's assigned
stations, for today only**:
- Maintenance today: `<complete count> / <total count>`
- Alarms resolved: `<resolved count> / <total count>`

**Routine tab** lists every base station that has a maintenance track for the
technician today, regardless of status. Each row shows the base station ID and a
status badge: **Not started**, **Ongoing**, or **Complete**. Rows that have already
been submitted (see "Daily cutoff") are visually deemphasized (e.g. dimmed) and show
a lock icon, but remain visible and tappable (view only) — they are not hidden or
moved to a separate tab. Rows sort with unsubmitted stations first, submitted ones
sunk to the bottom.

**Alarms tab** lists every base station with an alarm today, regardless of status.
Each row shows the base station ID and a status badge: **Triggered** or **Resolved**.
Resolved alarms are visually deemphasized with a lock icon, same treatment as
submitted maintenance, and sink to the bottom of the list, but stay visible and
tappable.

Tapping any row (in either tab, in any state) navigates to Screen 2 for that base
station, in the mode corresponding to which tab it was tapped from (`maintenance` or
`alarm`). A station with both tracks is reached via two different rows (one per tab)
and Screen 2 shows the relevant track's session state depending on which row was
tapped.

## Screen 2 — base station detail

At the top: a back button, the base station ID as the title, and four info cards
(2×2 grid, not a list): **base station ID**, **site classification**, **client**,
**manager**.

Below that, a session status line showing whichever of these are set for the current
track: started time, ended/resolved time, last-edited time.

Below that: the full **asset list** for the base station, each row showing the asset
name and a read-only checkbox reflecting whether that asset is currently marked
"done." Tapping an asset row navigates to Screen 3 for that asset — this works in
every state (locked or unlocked); viewing is always allowed, editing is gated (see
"Locking rules" below).

The bottom of the screen shows one of the following, depending on state:

- **Not started, and editable:** a "Start maintenance" button, plus (until real
  geofencing is built) a manual toggle labeled "Simulate: I am at this base station"
  used to test the geofence-gated flow described below.
- **Started, not yet ended (maintenance mode):** a status line ("Maintenance in
  progress. Tap back to end session.") — no button. Ending happens via the back
  button, not a button on this screen.
- **Started, not yet ended (alarm mode):** a "Resolve alarm" button.
- **Ended, not yet submitted (maintenance mode):** a status line ("Completed.
  Editable until submitted at 6pm.") — the asset checklist, conditions, and
  outstanding issues remain fully editable in this state (see "Locking rules").
- **Locked (submitted maintenance, or resolved alarm):** a lock icon and "View
  only" message. For a **resolved alarm** specifically, this is where the
  **Additional notes** feature appears (see below) — notes remain addable even
  though everything else on the screen is locked.

### Starting maintenance (geofencing)

Tapping "Start maintenance" checks whether the technician is at the base station.
In this mockup that's simulated with a manual toggle; in the real app it should be
a real geolocation check against the base station's coordinates. If the check fails,
show the technician an error: *"You must be at base station `<base_station_id>` to
start this maintenance schedule."* and do not start the session. If it passes, record
the start time and unlock the checklist/conditions/outstanding issues for editing.

**Editing after the initial start is not geography-restricted.** The geofence check
only applies to the act of starting a session. Once started, a technician can
continue editing checklist items, conditions, or issues from anywhere, right up
until the record is submitted (see "Locking rules").

### Leaving Screen 2 (exit-navigation rules)

What happens when the technician taps back depends on the current track and state:

- If the track is locked (already submitted/resolved) or was never started: just
  navigate back to the list, no prompt.
- If it's an **alarm** track, started but not yet resolved: prompt *"Leave without
  resolving this alarm?"* with **Cancel** / **Leave**. Leaving does not resolve the
  alarm or mark anything done — it just exits, leaving the session open for later.
- If it's a **maintenance** track, started but not yet ended:
  - If every asset's checklist is fully checked: prompt *"End maintenance?"* with
    **Cancel** / **Yes**. Choosing **Yes** marks every asset whose checklist is fully
    checked as "done" (see below), records the end time, and returns to the list.
  - If not every asset's checklist is fully checked: prompt *"Some maintenance
    tasks have not been completed. End maintenance anyway?"* with **Continue
    maintenance** / **End maintenance**.
    - **Continue maintenance** just closes the dialog and keeps the technician on
      Screen 2 — it does **not** exit and does **not** mark anything.
    - **End maintenance** marks every asset whose checklist is fully checked as
      "done" (assets with incomplete checklists are simply left not-done — nothing
      is force-marked), records the end time, and returns to the list.
  - Either way, ending a maintenance session always results in overall status
    **Complete** for that station for the day, even if some individual assets were
    left incomplete. There is no persisted "partially ended" state from normal use —
    a session is either still open (in progress) or ended (Complete). The one
    exception is a session that gets force-submitted at 6pm without ever being
    explicitly ended by the technician — see "Daily cutoff."

### When an asset becomes "done"

There is **no explicit "Mark as done" button** on the asset screen. An asset becomes
"done" automatically, in bulk, at the moment the technician **ends** the maintenance
session (via either "Yes" or "End maintenance" above) or **resolves** an alarm — at
that point, every asset whose checklist is fully checked gets its `done` flag set.
Assets with an incomplete checklist are left not-done. This reflects that the
checklist represents "this asset was inspected," not "this asset was fixed" — outstanding
problems are tracked separately (below), not by withholding the done mark.

## Screen 3 — asset maintenance page

Title is the asset's name, with a back button (returns to Screen 2). Sections, top to
bottom:

1. **Checklist** — the asset's fixed inspection tasks, each with a checkbox, in a
   card/container.
2. **"Select all that apply"** — the conditions list, rendered as a multi-select
   grid of toggle chips/checkboxes (e.g. "Leaking", "Corroded", "Noisy",
   "Overheating", "Battery weak").
3. **Outstanding issues** — see below.

All three sections share the same lock state — see "Locking rules." There is no save
or submit button on this screen; every checkbox toggle is saved immediately and
updates the track's "last edited" timestamp.

### Outstanding issues

A separate section for logging problems that need follow-up work, distinct from the
"select all that apply" conditions (conditions are a quick observational tag; an
outstanding issue is something that needs someone to go fix it later).

Fields per issue:
- **Description** (free text) — what's wrong.
- **Severity** — Low / Medium / High / Critical.
- (Implicitly tied to the asset the technician is currently on — no separate asset
  picker needed.)

Interaction: an "Add issue" form (description input + severity selector) with an
"Add issue" button; added issues render as a list, each removable (while the screen
is unlocked). Back on Screen 2, an asset's row shows an issue count badge if it has
any open issues, so the technician can see at a glance which assets need follow-up
without opening each one.

**Outstanding issues generate a separate task**, specifically a corrective work
order, once submitted. The mapping is:
- issue `description` → work order `description`
- issue `severity` → work order `priority`
- the asset it was logged against → work order `asset`
- work order `type` is always `corrective` (not scheduled, so no
  `pm_schedule`/`pm_task_template` link)
- work order `status` starts as `open`, unassigned

(Not yet finalized: whether a work order needs a link back to which maintenance
visit or alarm session actually surfaced the issue, for traceability/reporting
purposes. Worth deciding before building this for real.)

## Locking rules (who can edit what, and when)

An asset's checklist/conditions/outstanding issues are editable if and only if:
- the relevant track (maintenance or alarm) has been **started**, and
- the track has **not yet been locked** — see below for what locks each track.

**Maintenance track locks** when it has been **submitted**. Submission happens
automatically at the daily 6pm cutoff (see below) — there is no manual "submit"
action a technician takes. Critically, **ending** a session (whether via "Yes" or
"End maintenance") does **not** itself lock editing — a station that's Complete but
not yet submitted remains fully editable (checklist, conditions, outstanding issues)
right up until 6pm. This is the main point of the "editable until submitted" rule:
editing happens directly on Screen 2/3, there is no separate "edit mode" or
edit-request flow.

**Alarm track locks** as soon as it's **resolved** — unlike maintenance, there's no
grace period; resolving locks the checklist/conditions/issues immediately, because
resolving an alarm is an explicit, deliberate action (not an automatic daily
cutoff). However, resolved alarms get one narrow exception: **Additional notes**.

### Additional notes (resolved alarms only)

A resolved alarm's checklist, conditions, and outstanding issues are locked, but a
separate, simpler channel — **Additional notes** — stays open: a technician can add
free-text notes even after resolution. This is meant to be a lighter-weight version
of the outstanding-issues flow (single text field, no severity, append-only, no
editing/removing past notes). It's accessible directly from the Alarms tab (via
tapping into the resolved alarm's Screen 2, which is the only entry point — there is
no separate notes-only screen). Additional notes have their own cutoff: **they can
no longer be added after 6pm**, same daily boundary as maintenance submission.

## Daily cutoff (6pm) and next-day refresh

At 6pm every day:
- Every maintenance track that hasn't been submitted yet gets **auto-submitted "as
  is."** This includes stations that were never started, stations that are still
  in progress, and stations that were ended but not yet submitted. Whatever state
  the checklist is in at that moment is what gets submitted — nothing is force
  completed. Any asset whose checklist happens to be fully checked at that moment
  gets marked done as part of this, same rule as a normal "end maintenance."
- Every resolved alarm's **Additional notes** channel closes (no more notes can be
  added), though the resolved alarm record itself remains visible (locked) in the
  Alarms tab.
- Submitted/locked items are **not** deleted or hidden — they remain visible in
  their respective tab (Routine or Alarms), dimmed and locked, until the next day's
  data replaces them. This is why there's no separate History tab: "history" is
  just yesterday's locked rows sitting at the bottom of today's list, until they're
  cleared out.

At the start of a new day (when a new maintenance schedule/new alarm data is
pulled in), the following refresh happens:
- Maintenance tracks reset to fresh (not started, all checklist/condition/issue
  data cleared) for the new day's schedule.
- Resolved alarms from the prior day are cleared out entirely — a resolved alarm
  does not carry over.
- Alarms that were **triggered but never resolved** carry over into the new day,
  still shown as Triggered — they don't disappear just because the day changed;
  outstanding problems stay outstanding until actually resolved.
- Any newly triggered alarms for the new day appear as normal Triggered rows.

## Open items / things flagged as not yet finalized

- Real geolocation for the "Start maintenance" geofence check (currently a manual
  simulate toggle).
- Whether a `WorkOrder` generated from an outstanding issue needs a field linking
  it back to the specific maintenance/alarm session that surfaced it.
- Exact UI treatment for "deemphasized" locked rows (dimming + lock icon was used
  in the mockup; adjust to match your actual design system).

---

# Backend/data model updates (added after prototype iteration)

The sections above describe the mockup's UI behavior. Since building it, the
checklist/conditions design evolved from "checkboxes stored permanently on the
asset" to "structured responses recorded per visit," and several other pieces
(the yes/no gate, outstanding issues, alarm notes, the 6pm cutoff) need explicit
backend support that wasn't in the original data model discussion. This section
lists what changed.

## New models needed

### `Condition` (lookup table)
The "select all that apply" conditions list should be data, not a hardcoded
frontend array — different asset categories likely need different condition
options (a generator's conditions aren't a laptop's).
- `name`
- `asset_category` (FK, if conditions vary by category — confirm whether this
  is actually category-specific or global before building)

### `InspectionResponse` (new — the important one)
The checklist itself stays static reference text, sourced from
`PMTaskTemplate`/`AssetCategory` as already modeled. But the *answers* need
their own per-visit record — they are facts about a specific visit, not
permanent facts about the asset.
- `work_order` (FK) — which visit this response belongs to
- `asset` (FK)
- `issues_found` (nullable boolean — `None`/`null` = unanswered yet, which is
  what powers the required yes/no gate and the "not yet valid" state on the
  step tracker)
- `conditions` (M2M to `Condition`)
- `comments` (text, optional — separate free-text field distinct from
  outstanding issues)
- `created` / `updated`
- **Constraint**: if `issues_found = True`, at least one `Condition` must be
  linked. This mirrors the "select at least one option" rule from the
  prototype and should be enforced at the DB/serializer level, not just in the
  frontend, since that's the actual definition of "this asset has been
  validly answered."

### `Issue` (outstanding issues — staging, not yet a work order)
Kept as a lightweight record separate from the corrective `WorkOrder` it
eventually becomes, so a technician can freely add/remove entries mid-visit
without spawning real work orders for every keystroke.
- `inspection_response` (FK) or `asset` + `work_order` — whichever is cleaner
  given how `InspectionResponse` ends up modeled
- `description` (text)
- `severity` (choices: Low / Medium / High / Critical)
- `promoted_work_order` (FK to `WorkOrder`, nullable) — set once this issue is
  actually converted into a real corrective work order (see mapping below)

### `AlarmNote`
Backs the "additional notes" feature available on resolved alarms.
- `work_order` (FK — the alarm's own work order record)
- `text`
- `created`
- No `updated` needed — notes are append-only, never edited, per the prototype.

## Changes to the existing `WorkOrder` model

The original spec had `WorkOrder` close to its final shape already, but the
session-lifecycle behavior built during the prototype needs explicit fields
that weren't there before:
- `started_at`, `ended_at` — distinct from the audit `created`/`updated`
  timestamps; these are the actual "Start maintenance" / "End maintenance" /
  "Resolve alarm" moments a technician triggers.
- `submitted` (boolean) + `submitted_at`
- `geofence_verified` (boolean) — records whether the Start-maintenance
  geolocation check passed (once real geofencing replaces the simulate
  toggle).
- **Alarms need their own status pipeline.** Alarms go through
  **Triggered → Resolved**, which doesn't map cleanly onto the existing
  `open / in_progress / complete / cancelled` status choices built for
  preventive/corrective work. Worth deciding explicitly whether this is a
  new `type` value with its own status enum, or a fully separate model —
  don't just overload the existing `status` field with alarm-specific values.

## Outstanding issue -> work order mapping (unchanged from earlier, restated for completeness)

| Issue field | Work order field |
|---|---|
| `description` | `work_order.description` |
| `severity` | `work_order.priority` |
| the asset it was logged on | `work_order.asset` |
| (fixed) | `work_order.type = "corrective"` |
| (fixed) | `work_order.status = "open"` |

## Background jobs (not schema, flagging for whoever builds the task runner)

- **6pm daily cutoff**: a scheduled task (Celery beat, cron, etc.) that sets
  `submitted = True` on every unsubmitted `WorkOrder` for the day, and
  force-sets `ended_at` on any that were started but never explicitly ended.
  This is also the point where "additional notes" on resolved alarms should
  stop accepting new entries.
- **Next-day refresh**: a job that generates the new day's routine
  `WorkOrder`s from `PMSchedule`, carries over any alarms still `Triggered`
  untouched (they don't reset or disappear just because the day changed), and
  clears `Resolved` alarms from the active view — not a hard delete, just no
  longer part of "today's" data set.

## Open questions worth resolving before implementation

- Is `Condition` global or per-`AssetCategory`? Affects whether it needs the
  `asset_category` FK at all.
- Does `InspectionResponse` belong on `WorkOrder` + `Asset`, or should
  `WorkOrder` be scoped to a single asset in the first place (worth checking
  against how the existing `WorkOrder.asset` FK is used elsewhere)?
- Should alarms get their own model instead of reusing `WorkOrder` with a
  different `type`? The lifecycle differences (Triggered/Resolved vs.
  open/in_progress/complete/cancelled, plus `AlarmNote` only making sense for
  alarms) are a real signal they may not belong in the same table.

---

# Responsive breakpoint

Two distinct layouts exist for this app, both described earlier in this
document:

- **Single-column ("phone") layout** — Screens 1/2/3 as separate views with
  back navigation, the step tracker with dots, and the Next/Complete button
  flow. This is the layout described in the main body of this spec.
- **Split-view ("tablet") layout** — a persistent left panel (station info +
  full asset list) and a right panel (the currently selected asset's
  checklist), with a horizontally scrollable row of station chips at the top
  for switching between stations. Station-switching triggers the same
  exit-warning modal as leaving a station in the phone layout.

**Breakpoint rule:** any viewport **600px or wider — portrait or
landscape — uses the split-view layout.** Below 600px uses the single-column
layout. This is width-only; orientation does not matter. A tablet held in
portrait at, say, 768px wide still gets split-view, not the phone layout,
since there's enough horizontal room for both panels to be usable at that
width.

Implementation note: this is a single `min-width: 600px` media-query (or
container-query, if the app's component structure supports it better)
switch between the two layouts — not three separate breakpoints and not a
gradual reflow. The two layouts are different enough (navigation model,
number of visible panes, presence of the step-tracker vs. persistent asset
list) that this should be treated as swapping layouts wholesale at the
threshold, rather than incrementally resizing one layout into the other.

---

# Wide-screen layout rules (split-view)

Two decisions on top of the breakpoint rule above:

**Implementation approach: hard swap.** The phone and split-view layouts are
two separate component trees, shown/hidden by the 600px breakpoint — not a
single shared tree with conditional/responsive styling. The two layouts
differ enough in navigation model (back-button screens vs. persistent
panels) and structure (step tracker vs. always-visible asset list) that
sharing one component tree would mean excessive internal branching for
little benefit.

**Panel width on wide screens.** In the split-view layout:
- The left panel stays a **fixed 300px** regardless of how wide the overall
  screen gets — it does not grow on large tablets or desktop-width windows.
- The right panel's *container* fills all remaining width (so its
  background, borders, and dividers span the full available space
  continuously).
- The right panel's *content* — the checklist, yes/no buttons, conditions
  grid, comments field, outstanding issues — is capped at a **max-width of
  roughly 480-560px**, left-aligned (not centered) with padding absorbing
  the remaining space.

This matches the convention used by native tablet split-view apps (Apple
Mail, Notes, Files): the detail pane's frame fills the screen, but the
content inside it doesn't stretch into uncomfortably long line lengths just
because the frame is wide. Left-aligning (rather than centering) the capped
content keeps it visually anchored next to the fixed sidebar — centering
would create uneven whitespace on the right that shifts unpredictably with
screen width, which reads as unintentional rather than as deliberate
padding.

---

# Hi-fi visual language (final pass)

The hi-fi mockups translated the Field Safety palette (see
`field_safety_color_palette.md`) into concrete UI patterns. This section
records the actual tokens and conventions used, since several were refined
beyond what the original palette doc specified.

## Additional tokens used in hi-fi mockups

Beyond the core palette, hi-fi screens introduced **tint pairs** for status
colors — a light background + a readable text color from the same family —
used for pills, badges, and icon chips:

| Purpose | Background tint | Text/icon color |
|---|---|---|
| Primary (teal) | `#E6F2F0` | `#0F766E` |
| Accent (orange) | `#FDECE3` | `#EA580C` |
| Not started | `#F1EFED` | `#78716C` |
| Ongoing | `#FDF3D8` | `#92610A` |
| Complete | `#E3F5E9` | `#166534` |
| Triggered | `#FCE8E8` | `#B91C1C` |
| Resolved | `#F1EFED` | `#57534E` |
| Danger (geofence error) | `#FCE8E8` | `#B91C1C` |

Note some of these darken the original palette doc's flat status colors
(e.g. `Complete` moved from `#15803D` to `#166534`, `Triggered` from
`#DC2626` to `#B91C1C`) specifically so they stay readable as *text* on a
light tint background, per the "darkest shade from the same family" rule —
the original flat hex values are still correct for borders/icons on white,
but tint-pair text needed a touch more contrast.

**Additional structural tokens (tablet only):**
- `--fs-border-strong: #DEDBD6` — used for the divider between panes and
  around focusable form fields, where the default `--fs-border` hairline
  was too subtle to register as a boundary.
- `--fs-work-bg: #F2F7F6` — a pale teal-gray tint applied to the right
  ("active work") panel specifically to distinguish it from the white left
  ("context") panel. This was added after initial contrast between the two
  panes was too low.

## Visual patterns established

- **Status pills** are filled tint-background pills (not outlined), e.g. a
  station's "Ongoing" badge is amber-tinted background with amber text, not
  a bordered outline. This reads faster at a glance than the outline style
  used in the lo-fi wireframes.
- **Asset completion** is shown as a filled teal circle with a check icon
  (done) vs. an empty outlined circle (not done) — not a checkbox. This
  matches the "checklist is informational, not checkable" rule: the circle
  represents the asset's overall answered/valid state, not literal checklist
  interaction.
- **Icon chips**: list rows (stations, alarms) use a rounded tinted square
  containing an icon (antenna for stations, alert-triangle for alarms) as a
  leading visual anchor, rather than a plain icon with no container.
- **Selection indicator**: the currently selected item in a persistent list
  (e.g. the active asset in the tablet left panel, the active work order in
  the Tasks tab left list) gets a colored left border stripe (3px, primary
  teal) plus a tinted background — not just a background change alone.
- **Locked/dimmed items**: submitted maintenance and resolved alarms use
  `opacity: 0.6` on the whole row/chip plus a small lock icon — consistent
  across phone and tablet.
- **Modals** (exit-warning, geofence error) use a dimmed backdrop
  (`rgba(28,25,23,0.5)`) over the *existing* screen rather than navigating
  to a new one, reinforcing that these are interruptions, not new screens.
  On tablet, the modal explicitly names which station it concerns (e.g.
  "You're switching away from OY0735...") since the trigger is picking a
  different station chip rather than an unambiguous single back button.
- **Cross-navigation context**: when arriving at an asset screen via the
  Tasks tab (rather than via its station), the asset screen adds a small
  breadcrumb line above the title (e.g. "OY0735 · Routine maintenance") to
  re-orient the technician, since the normal station-first navigation was
  skipped. The specific work order that was tapped also gets a 2px primary
  border on its card within the Work orders section, to confirm which one
  brought them there.

## Hi-fi vs. lo-fi differences (deliberate, not oversights)

A few things present in the interactive lo-fi prototype were intentionally
dropped from the hi-fi mockups, since they were prototype-testing scaffolding
rather than real product UI:
- The "Simulate: I am at this base station" toggle (stand-in for real
  geolocation) — hi-fi shows the resulting **error state** instead, without
  a visible toggle.
- The "Simulate 6pm cutoff" / "Simulate next day" developer buttons.
- The reset-demo refresh icon in the header (prototype-only affordance).

These should NOT be treated as removed features — they're testing aids that
don't belong in the final product surface. The underlying behavior (real
geofencing, the 6pm cutoff, next-day refresh) is unchanged and still
described earlier in this document.

---

# Summary metrics — third metric added for Tasks

The header summary metrics (shown on every list screen — Routine, Alarms,
and Tasks tabs, on both phone and tablet) now show **three** items instead
of two:

1. Maintenance today — `X / Y` (bounded daily count, e.g. `2/4`)
2. Alarms resolved — `X / Y` (bounded daily count, e.g. `1/2`)
3. **Open tasks — plain count, not a fraction** (e.g. `4 open`)

The third metric is deliberately **not** phrased as a fraction like the
other two. Routine and Alarms are both bounded, reset-daily sets — "4
stations today" and "2 alarms today" have a natural denominator. Work
orders don't: they accumulate and get resolved on no fixed schedule, so
"X of Y open tasks" would imply a false finish line. A plain open count is
the more honest and more actionable version of "how many things currently
need attention."

On phone, all three metrics render as a horizontal row of compact pills
(icon chip + label) rather than the larger 2-column card layout originally
used for just two metrics — the pill format scales to a third item on a
narrow screen without crowding, and this is now the standard pattern going
forward if a fourth metric is ever added.
