# Handoff: decisions and work from the claude.ai session (27 Oct – 2 Nov 2026)

This file brings Claude Code up to date with work done outside it. Read it before changing the app.
The working rule in `CHECKLIST.md` still applies: a question is not a command; only work on what is asked.

---

## 1. What changed in the repos (already committed, not pushed)

Root repo (backend + docs):
- `503bc7e` Cluster Manager role; inspection ratings renamed to Good / Fair / Poor (migration 0028)
- `6d6b37d` Consumables and spare parts backend (migrations 0029–0031, new `backend/assets/parts.py`)
- `2098f28` `WorkOrder.assigned_technician` renamed to `assigned_to` (migration 0032)

Mobile repo:
- `50dff48` role type `technician` → `field_team`, added `team_lead` (`src/types/api.ts`, `src/dev/mockData.ts`)

To run the backend after pulling:
1. `pip install Pillow==12.3.0` (needed for usage photos; now in `requirements.txt`)
2. `python manage.py migrate`
3. Optional reseed: adds `tech1` to "Lagos Island Team A", a Cluster Manager `cm1` / `cm1pass` (cluster Lagos Island), and opening regional store stock.

Backend tests: 133 passing (run on SQLite, not yet on Postgres).

Note: `requirements.txt` was already missing djangorestframework, simplejwt, django-cors-headers etc. Only Pillow was added.

---

## 2. Roles and who sees what

| Role (`role` from `/api/auth/me/`) | Sees |
| --- | --- |
| `field_team` (was "technician" — renamed everywhere) | The existing app: Today / base stations to maintain and related screens. No menu. |
| `team_lead` | Same screens as Field Team. One Team Lead per cluster team. Holds the team's received parts. |
| `cluster_manager` | A menu (see below). Assigned to exactly one cluster (`/api/auth/me/` returns `cluster: {id, name}`). |
| `regional_manager` | Approves/declines requests and records deliveries — **later phase, screens out of scope**. Use Django admin for now. |

`/api/auth/me/` now also returns `cluster_team: {id, name} | null`.

Login must route by role: Cluster Managers land on the menu; everyone else lands on Today.
The current login is a single "Enter" button (demo auth) — it cannot tell roles apart; a real username/password login is needed.

### Cluster Manager menu
1. Base-station maintenance (the existing app space)
2. Maintenance reports
3. Consumables and spare parts
4. Diesel delivery (not yet specified)
5. Petty cash (not yet specified)
Plus a **Log out** button (the app currently has no logout anywhere, though `logout()` exists in `AuthContext`).

---

## 3. Design reference

Use the existing palette in `src/constants/colors.ts` / `field_safety_color_palette.md` (teal `#0F766E` primary, orange `#EA580C` only for primary calls to action, status colours as defined).

A clickable mockup of all screens below exists as a private claude.ai Design canvas ("CMMS Cluster Manager mockup"). Claude Code cannot open it; the descriptions here are the source of truth. Ask the user for screenshots if layout detail is needed.

Mockup conventions worth keeping:
- Phone width 390, cards on `#FAFAF9` with white 14px-radius cards, 44px min touch targets.
- Status grids use: Good = green dot, Fair = amber dot, **Poor = red square** (not colour-only), No maintenance = hollow grey ring.
- Health/SLA % text: ≥95 green, 90–94 amber, <90 red.

---

## 4. Maintenance reports (Cluster Manager) — UI designed, backend NOT built

Six read-only screens, scoped to the manager's cluster, shown a month at a time (backend keeps all history). Tabs: **Stations · Asset types · Staff**.

1. **Base stations overview** — summary tiles (station count, visits this week, avg SLA); a grid: one row per station (site ID + SLA %), one column per day (week view with prev/next arrows, not pagination). Cell = Good/Fair/Poor/No maintenance. Tap a row → station detail.
2. **Base-station detail** (e.g. OYO123) — urgent items banner; tiles: checks this month (21/25), overall health, SLA %, diesel at last check; assets with health pill (tap → asset detail); open notes/tasks; maintenance & alarm history (item, date, status); diesel delivery log (date, qty L, level before → after mm, by).
3. **Base-station asset detail** (e.g. OYO123 Generator) — tiles: health, SLA, checks, run hours (generators), last service, next service; last readings (run hours, diesel level, voltage); maintenance & alarm history with who did it.
4. **Cluster asset types** — one row per asset type: count, health %, bar; "weakest type" tile. Tap → single type grid.
5. **Single asset type in cluster** — same day grid as screen 1 but scored on that asset type only. Tap row → that station's asset.
6. **Cluster staff list** — name, clusters covered, count; unassigned staff flagged.

Open before building the backend for these:
- **Health % and SLA % have no definition yet** — need formulas from the user.
- **Good/Fair/Poor per visit doesn't exist.** The rating currently lives on the checklist template (`AssetCheckList.condition`), not on each inspection. The grids need a per-visit, per-asset rating (e.g. on `InspectionResponse`). Not added yet — confirm with the user first.
- Diesel: tank level in mm, deliveries in litres (keep that split).

---

## 5. Consumables and spare parts

### 5.1 Flow (as built)
- Field Team requests parts for **one base station**; a request has several **lines** (one per part: quantity, required date). Requester, team, Team Lead and date are recorded automatically.
- Required dates in the past are allowed but flagged `is_backdated` (to measure how often it happens).
- Each line is approved/declined (decline needs a reason) at Regional Manager level — **Django admin for now**.
- Deliveries: a line can be delivered in parts. A delivery is **Pending** until both sides confirm (approver records it; Field Team confirms received — either order). Pick-up date = when Field Team confirms receipt. Pick-up location field exists, left blank for now.
- Partly delivered lines go back to Approved ("2 of 3 delivered") until the rest arrives or the line is **closed short** (ends as Delivered, shortfall recorded).
- Requester can **cancel** while every line is still Requested. Editing comes later.
- **Stock** lives at the regional store and per cluster team. A completed delivery moves regional → team. Usage takes from the logging person's team. If a team holds too little, the shortfall is first added as **"added at site"** (stock never goes negative). Every change is a row in `StockMovement`.
- Whole-number quantities only for now (round inputs in the app).
- In-app notifications for: new request, cancelled, approved, declined, delivery recorded, delivery received, added at site, low regional stock.

Line statuses: `requested`, `approved`, `declined`, `cancelled`, `pending`, `delivered`.

### 5.2 Usage logging (Field Team) — app changes needed
Existing Log part usage screen (from Asset Maintenance): part search, qty, notes. Add:
- **Required photo, camera only** (no gallery). Install `expo-image-picker` and `expo-image-manipulator`. Resize longest side ~1600 px, JPEG ~70% (aim 200–400 KB, labels readable). Server accepts JPEG only, max 2 MB.
- Optional Part ID field (`part_identifier`, free text).
- Send as **one multipart request** with the photo. Record `photo_taken_at`.
- **Offline:** save the photo to permanent app storage (not cache), queue the log pointing at it, delete only after the server confirms. The current offline queue stores JSON only — needs extending for files.
- Until this ships, the server can be run with env `PART_USAGE_PHOTO_REQUIRED=false`, otherwise the current screen is rejected.

### 5.3 Part requests (Field Team) — app changes needed
- Where in the app requests are made: **still to be decided** by the user.
- Form: base station, pick several parts, qty for each, one required date per part. The old single-part `PartRequestScreen` (hidden) uses removed endpoints — rewrite it.
- Field Team also needs: list of my requests with line status; confirm received on deliveries; cancel.

### 5.4 Cluster Manager screens (designed)
Tabs **Requests · Usage**.

**Requests tab**
- Summary "Waiting on parts" at the top: one row per part, columns **Requested** (qty on Requested lines), **Approved** (still-to-receive qty on Approved + Pending lines), **Total** (sum). Excludes Delivered, Declined, Cancelled.
- Below: request cards **grouped by base station**. Each card: request date, requester, and each part with qty and status pill.
- Tapping a card for full details: **parked**.

**Usage tab** (this month only)
- Summary "This month": one row per part — **Delivered** (confirmed received this month) and **Used** (usage logs this month). No toggle here.
- Usage log below with a toggle **By consumable / By base station** that groups the log cards. Each card: photo thumbnail, part (or station), qty, asset, date, logged by, Part ID, "Added at site" tag where applicable.

Status pill colours used: Requested grey, Approved teal, Pending amber, Delivered green, Declined red, Cancelled muted grey.

### 5.5 API (built, all under `/api/`)

| Who | Method / path | Notes |
| --- | --- | --- |
| Field Team | `POST part-requests/` | JSON `{id?, base_station, work_order?, asset?, notes?, lines: [{part, quantity, required_date "YYYY-MM-DD"}]}`. All-or-nothing. Replay with same `id` returns 200. |
| Field Team | `GET part-requests/` | My requests with `lines[]` and each line's `deliveries[]`, `delivered_qty`, `shortfall`. |
| Field Team | `POST part-requests/{id}/cancel/` | Only while all lines Requested. |
| Field Team | `POST part-request-lines/{id}/receipts/` | `{quantity, id?}` — confirm receipt before the delivery is recorded. |
| Field Team | `POST part-deliveries/{id}/confirm-received/` | Confirm a recorded delivery. |
| Field Team | `POST part-usages/` | **multipart**: `id?, work_order, asset, part, qty_used, notes?, part_identifier?, photo_taken_at?, photo` (JPEG ≤ 2 MB). Response includes `photo_url`, `base_station`, `cluster_team`. |
| Field Team | `GET part-usages/?work_order=&asset=` | As before. |
| Field Team | `GET team-stock/` | `{cluster_team, items: [{part, qty, reorder_threshold}]}` |
| Cluster Manager | `GET manager/part-requests/` | One row per line. Filters: `base_station, part, status, backdated=true, date_from, date_to`. |
| Cluster Manager | `GET manager/part-usages/` | Filters: `base_station, part, recorded_by, date_from, date_to`. |
| Cluster Manager | `GET manager/stock/` | `{teams: [...], totals: [{part, qty}]}` |
| Everyone | `GET notifications/` → `{unread, results}`; `POST notifications/{id}/read/` | |
| Everyone | `GET parts/?search=&kind=consumable|spare_part` | Parts now have `kind`, `unit`. |

Removed: `POST part-requests/{id}/receive/`.

**Not built yet** (needed by the Cluster Manager screens):
- `GET manager/requests-summary/` — Requested / Approved (incl. Pending, still to receive) / Total per part.
- `GET manager/usage-summary/?month=YYYY-MM` — Delivered / Used per part; default this month. Usage list should also default to this month.

Business rules live in `backend/assets/parts.py`; views and admin both call it. Keep it that way.

### 5.6 Open decision (do not build until confirmed)
**Cluster Manager collects and distributes.** Proposed by the user on 29 Oct, parked: Field Team requests; Cluster and Regional Managers both see it; the Cluster Manager picks up from the Regional Manager and distributes to teams. If confirmed: two hand-overs (pick-up, then distribution), a third stock holder (cluster), Cluster Manager "picked up" / "distributed" actions, Pending covers the team hand-over. Still to answer: does pick-up need both sides to confirm; does each part go only to its request's team.

### 5.7 Deferred
API role/scope enforcement (and missing station checks on some write endpoints); request editing; matching part used to part supplied; usage without a request (allowed, revisit); back-dated requests (allowed, revisit); push notifications; pick-up locations list; supplier receipts into regional stock.

---

## 6. App work implied, in rough order
1. Real login + role-based landing; menu for Cluster Managers; logout button.
2. Rename remaining "technician" wording in the UI to Field Team.
3. Update `src/dev/mockData.ts` and its tests for the new API shapes (the `tester` build runs on mock data).
4. Usage photo capture + compression + offline file queue.
5. Multi-part request form, my requests, confirm received, cancel.
6. Cluster Manager Consumables screens (Requests, Usage) + the two summary endpoints.
7. Notifications list with unread count.
8. Maintenance reports (after health/SLA and per-visit rating are defined).

## 7. Known issues found along the way
- Logout doesn't revoke tokens (token blacklist app not installed) — CHECKLIST Phase 3.
- `tsc --noEmit` fails only in `*.test.ts(x)` (missing Jest types); tests themselves pass.
- Diesel tab lists only stations on today's routine, so it's empty on days with none.
- Tasks tab is a placeholder.
