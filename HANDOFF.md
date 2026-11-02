# Handoff: decisions and work from the claude.ai session (27 Oct – 2 Nov 2026, updated 2 Nov afternoon)

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
- Status grids use: Good = green dot, Fair = amber dot, **Poor = red square** (not colour-only), Missed = hollow dark ring, Not scheduled = short grey dash.
- Health/SLA % text: ≥95 green, 90–94 amber, <90 red.

---

## 4. Maintenance reports (Cluster Manager) — SPECIFIED 2 Nov, not built

Spec agreed with the user on 2 Nov 2026 (source: claude.ai doc "Maintenance Reports — Spec", plus the user's Form 1a and Defects Rating Criteria). This section is the source of truth for Claude Code.

### 4.1 Asset types (replace the current categories)
Nine asset types, grouped under Form 1a headings. Remove HVAC/AC, Rectifier, Hybrid DC Power (and any other old categories). Checklist points = Form 1a "Defects scope". Defects = Defects Rating Criteria, each tagged **Poor** or **Fair**.

| Group | Asset type | Checklist points | Poor defects | Fair defects |
| --- | --- | --- | --- | --- |
| 1. Janitorial Services | Janitorial Services (one per site; covers 2 m perimeter setback, perimeter fence and entrance doors, concrete floors and gravel cover) | Cleanliness of concrete and gravel floors; Additional gravel required; Oil and diesel spillage; Rodent or insect infestations; Site access control (locks etc.); Warning signs and safety labels | Rodents; Perimeter fence; Major granite stain; Damaged shelter floor / leaking roof (indoor sites); Palisade fence earthing | Internal cleanliness; External cleanliness; Minor granite stain; Shelter cleanliness (indoor sites) |
| 2. Generator Power Supply | Diesel Generator | Generator cleanliness; Housing rust, leakages, bolts and nuts; Oil, diesel and coolant leakages; Wiring and control system; Pipes and hoses; Exhaust secure and free of obstruction; Exhaust carbon build-up; Incorrect load sizing; Proper cabling; Engine condition; Electrical condition; Engine vibration ("Generator Operations" items are part of this checklist) | Engine oil, diesel or radiator coolant leakages; Engine problems; Exhaust conditions; Generator vibration; Safety devices bypassed; Generator earthing | Generator housing; Generator cleanliness; Minor wiring (battery terminals etc.); Generator not installed on plinth |
| 2. Generator Power Supply | Diesel Tank | Tank cleanliness; Tank rust and leakages; Water separator condition; Diesel leakages; Diesel pipes and hoses | Leakages from diesel tank; Water ingress; Severe rust; Water separator; Galvanized diesel line; Tank tilting; Tank not installed on plinth; Tank earthing | Minor rust; Tank dented; Tank calibration |
| 3. Solar Power Supply | Solar Panels and Structure | Solar panel condition; Panel structure condition; Solar control condition | Structural stability; Solar structure earthing; Solar cables termination | Solar panels condition; Tree shading solar panel |
| 3. Solar Power Supply | Battery Packs | Battery pack condition | (none yet) | (none yet) |
| 4. Grid Power Supply | Transformer | Transformer condition; Grid cables | Transformer inside the site and not fenced; Grid functionality; Grid cable unsafe termination/connection/condition | Transformer condition |
| 5. Control Panels | AC Control Panel | AC control panel condition | Exposed terminals; Faulty panel door; Damaged components; Bypassed control panel | Poor cable management; Panel cleanliness; Aged components; Panel labelling |
| 5. Control Panels | DC Control Panel | DC control panel condition | (same as AC Control Panel) | (same as AC Control Panel) |
| 6. Telecoms Tower | Tower Structure | Painting, rust, bolts etc.; Security and aviation light; Cables, cable trays and arrangement; Earthing system | Earthing; Foundation structure; Tower deflection; Unsafe tower ladder | Painting wear; Aviation light; Security light; Cables arrangement |

Left out for now: HSE (in criteria, not on form), Active Equipment Cabinets, Any Other Equipment/Facility.

### 4.2 Ratings
- **Asset rating per visit:** set when the asset is marked complete, from the defects ticked (the existing per-category "conditions" multi-select): any Poor defect → Poor; else any Fair defect → Fair; else Good. Nobody picks a rating by hand. Store it on that visit's record so history never changes.
- **Default is Good.** Very minor issues are not recorded. An asset keeps its rating until a later complete visit changes it ("current rating" = latest completed visit; Good if none).
- **Station rating per visit day** (only for a complete visit = every active asset at the station marked complete), checked in order:
  1. Poor if Diesel Generator is Poor, OR Diesel Tank is Poor, OR any two other assets are Poor.
  2. Good if no asset is Poor and no more than two assets are Fair.
  3. Fair otherwise (e.g. one Poor asset that isn't generator/tank; or 3+ Fair).
  A station without a generator or tank uses only the "two other assets" part of rule 1. Store the result when the visit completes.
- **Grid cell per station per day:** Good / Fair / Poor (complete visit that day) · **Missed** (scheduled but not done, or only partly done) · **Not scheduled**. The single-asset-type grid uses that asset's rating per day.
- **Visit date** = the day the work was done (Africa/Lagos).

### 4.3 Measures
| Measure | Rule |
| --- | --- |
| Station SLA % | Complete visits ÷ scheduled visits in the period (partial = not done). |
| Asset checks (e.g. "21 / 25") | Maintenance completed on the asset ÷ maintenance scheduled for it in the period. **Hardcoded placeholder in the UI for now** (asset SLA is still undefined). |
| Asset SLA % | Undefined — placeholder. |
| Health % (station, asset, asset type, cluster) | Undefined — placeholder. |
| Colour bands | ≥95 green, 90–94 amber, <90 red. Store as settings (not hardcoded) so a future Settings screen can change them. |
Period = calendar month by default; backend keeps all history.

### 4.4 Data model changes
- `AssetCategory`: the nine types above; add `group` (Form 1a heading) and an optional service interval (run hours or days) used for "Next service". Next service only shows where an interval is set.
- `PMQuestion`: load checklist points per type. `Condition`: add `severity` (poor/fair) and load defects per type.
- `InspectionResponse`: add `rating` (good/fair/poor), computed on mark-complete.
- Station visit rating stored when the last asset completes.
- Remove `AssetCheckList.condition` (template-level Good/Fair/Poor; replaced by the above).
- `MeterReading` (diesel level) and `DieselDelivery` (tank level before/after): add **litres** beside mm. The Field Team enters both (the app does not convert).
- New simple settings store: colour band thresholds; service intervals. Settings has no UI scope yet.
- Field Team UI: the asset checklist screen must let them tick defects (grouped Poor / Fair) and shows the resulting rating before Mark complete; diesel level inputs take mm and L.

### 4.5 Screens (all scoped to the manager's cluster; tabs Stations · Asset types · Staff)
1. **Base stations overview** — tiles (stations, visits this week, avg SLA); week grid (prev/next week), cells per 4.2; tap row → detail.
2. **Base-station detail** — urgent items (open alarms + open issues); tiles: checks this month, overall (station) rating, SLA %, diesel at last check (L and mm); assets with current rating; open notes/tasks; maintenance & alarm history; diesel delivery log.
3. **Asset detail** — current rating; checks (placeholder); SLA (placeholder); run hours (generator); last service; next service (only if interval set); last readings (diesel shows mm and L); history with who did it.
4. **Asset types** — row per type: count, health % (placeholder); tap → single-type grid.
5. **Single asset type** — same grid, that type's rating per station per day.
6. **Staff list** — names only (staff belong to one cluster).

### 4.6 Reminders and later list (do not build)
- Reminders for the user: define asset SLA (keep "21/25" placeholder until then); set generator service hours in Settings (per base station or asset type); define health %; decide whether alarms affect health/SLA.
- Later: HSE; Active Equipment Cabinets and Any Other Equipment; Battery Packs has no defects (always Good until added); Settings screens (unscoped); voltage reading (not recorded today).

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

## 6. App work status
Done by Claude Code (see git log): login + role landing + logout; Cluster Manager menu; Field Team wording; blank mock/seed data; usage photo; part requests; Consumables Requests/Usage screens + summary endpoints; notifications; Request parts on Site actions.

Next: Maintenance reports, as specified in section 4.

## 7. Known issues found along the way
- Logout doesn't revoke tokens (token blacklist app not installed) — CHECKLIST Phase 3.
- `tsc --noEmit` fails only in `*.test.ts(x)` (missing Jest types); tests themselves pass.
- Diesel tab lists only stations on today's routine, so it's empty on days with none.
- Tasks tab is a placeholder.
