# CMMS Mobile App — Developer Specification

## 1. Project Overview

A technician-facing mobile CMMS (computerized maintenance management system) for managing preventive maintenance and alarm resolution at cellular base stations.

**Backend stack:** Django 5.2, Django REST Framework, PostgreSQL
**Auth:** JWT (`djangorestframework-simplejwt`)
**Background jobs:** Celery (not yet set up)
**Frontend:** Mobile app (TBD)

**Core actors:**
- **Technician** — field worker assigned to a set of base stations. Primary mobile app user.
- **Regional Manager** — oversees stations and PM schedules. Primarily admin-facing, not the main mobile user.

---

## 2. Key Concepts

### Two independent tracks per base station

Every base station can be on one or both tracks on a given day:

1. **Maintenance track** — routine, scheduled preventive maintenance.
   Lifecycle: `not started → ongoing → complete → submitted`
   Mapped to a `WorkOrder` (type=`preventive`, FK to `base_station`).

2. **Alarm track** — a triggered fault on an asset at the base station.
   Lifecycle: `triggered → resolved`
   Mapped to an `Alarm` record (FK to `asset`; asset links to base station via location).

The two tracks are fully independent — one does not block or depend on the other.

### Assets and their per-visit data

A base station has assets (generators, AC units, rectifiers, etc.). For each asset within a maintenance/alarm visit, the app records an `InspectionResponse` — a per-visit, per-asset record containing:
- **Checklist responses** (`WorkOrderChecklistResponse`) — one checkbox per `PMQuestion`
- **Conditions** (M2M to `Condition`) — "select all that apply" observable tags
- **Issues** — outstanding problems to be followed up; eventually promoted to corrective `WorkOrder`s
- **done flag** — set automatically when the session ends, if the checklist is fully checked

An asset's checklist represents that it was *inspected*, not that any problem was fixed.

### Locking rules

| Event | What locks |
|---|---|
| `WorkOrder.submitted = True` | Entire maintenance track (checklist, conditions, issues) |
| `Alarm.resolved_at` set | Entire alarm track (checklist, conditions, issues); `AlarmNote` stays open until 6pm |
| 6pm daily cutoff | Auto-submits all unsubmitted `WorkOrder`s; closes `AlarmNote` channel on resolved alarms |

The API enforces locking — do not rely on the frontend to prevent writes.

---

## 3. Data Model Reference

| Model | Mobile-app role |
|---|---|
| `BaseStation` | The site. Has `site_id`, `site_classification`, `clients` (M2M), `manager` |
| `Asset` | Physical equipment at a location within a base station |
| `WorkOrder` | One maintenance track session (`type=preventive`, `base_station` FK) or one corrective task (`type=corrective`, `asset` FK) |
| `Alarm` | One alarm track event on an asset (`raised_at` / `resolved_at`) |
| `InspectionResponse` | Per-visit, per-asset record. Unique on `(work_order, asset)` |
| `WorkOrderChecklistResponse` | Per-question checkbox, FK to `InspectionResponse` |
| `Condition` | Lookup table of observable tags (e.g. "Leaking", "Corroded"). Nullable `asset_category` FK — `null` means global |
| `Issue` | Outstanding problem logged during a visit; becomes a corrective `WorkOrder` on promotion |
| `AlarmNote` | Append-only text note on a resolved `Alarm`. No `updated` field — never edited |
| `PMQuestion` | Static checklist item text, FK to `AssetCheckList` |

**WorkOrder XOR constraint:** A `WorkOrder` targets exactly one of `base_station`, `asset_category`, or `asset`. Never set more than one.

---

## 4. Auth

JWT via `djangorestframework-simplejwt`. All endpoints require `Authorization: Bearer <access_token>` except login.

Recommended token lifetimes: access = 60 min, refresh = 7 days.
Frontend should silently refresh the access token at ~50 minutes. On a 401, attempt one silent refresh before prompting login.

### POST `/api/auth/login/`
**Request:**
```json
{ "username": "string", "password": "string" }
```
**Response 200:**
```json
{
  "access": "string",
  "refresh": "string",
  "user": {
    "id": "uuid",
    "username": "string",
    "first_name": "string",
    "last_name": "string",
    "role": "technician"
  }
}
```
**Response 401:** `{ "detail": "No active account found with the given credentials" }`

---

### POST `/api/auth/refresh/`
**Request:** `{ "refresh": "string" }`
**Response 200:** `{ "access": "string" }`
**Response 401:** `{ "detail": "Token is invalid or expired" }`

---

### POST `/api/auth/logout/`
**Request:** `{ "refresh": "string" }`
**Response 205:** No content. Blacklists the refresh token.

---

### GET `/api/auth/me/`
**Response 200:**
```json
{
  "id": "uuid",
  "username": "string",
  "first_name": "string",
  "last_name": "string",
  "role": "technician",
  "stations": ["uuid"]
}
```

---

## 5. Screen 1 — Base Station List

### Layout

Two tabs: **Routine** and **Alarms**.

Above the tabs — two summary cards, scoped to the logged-in technician's assigned stations, today only:
- Maintenance today: `complete / total`
- Alarms resolved: `resolved / total`

**Routine tab:**
- Lists every base station with a maintenance `WorkOrder` assigned to this technician today
- Status badge per row: `Not started` / `Ongoing` / `Complete`
- Submitted rows: dimmed + lock icon, sorted to bottom. Still visible and tappable (view only)
- Unsubmitted rows: sorted to top

**Alarms tab:**
- Lists one row per `Alarm` record — if a base station has two assets with alarms, it appears twice
- Each row shows the base station `site_id` and the affected asset name
- Status badge per row: `Triggered` / `Resolved`
- Resolved rows: dimmed + lock icon, sorted to bottom. Still visible and tappable

Tapping any row navigates to Screen 2 for that specific alarm.

### Endpoints

#### GET `/api/today/`
Returns all Screen 1 data in a single call.

**Response 200:**
```json
{
  "summary": {
    "maintenance": { "complete": 3, "total": 5 },
    "alarms": { "resolved": 1, "total": 2 }
  },
  "routine": [
    {
      "base_station": {
        "id": "uuid",
        "site_id": "OY0735",
        "name": "string",
        "site_classification": "platinum",
        "clients": ["MTN"],
        "manager": { "id": "uuid", "name": "string" }
      },
      "work_order": {
        "id": "uuid",
        "started_at": null,
        "ended_at": null,
        "submitted": false
      },
      "track_status": "not_started"
    }
  ],
  "alarms": [
    {
      "base_station": {
        "id": "uuid",
        "site_id": "OY0735",
        "name": "string"
      },
      "asset": {
        "id": "uuid",
        "name": "string"
      },
      "alarm": {
        "id": "uuid",
        "raised_at": "2026-07-26T08:00:00Z",
        "resolved_at": null
      },
      "track_status": "triggered"
    }
  ]
}
```

`track_status` values:
- Routine: `not_started` | `ongoing` | `complete` | `submitted`
- Alarms: `triggered` | `resolved`

---

## 6. Screen 2 — Base Station Detail

### Layout

- **Header:** back button + base station `site_id` as title
- **Info cards (2×2):** site ID, site classification, clients, manager name
- **Session status line:** started time, ended/resolved time, last-edited time (shows whichever are set)
- **Asset list:** each row shows asset name + done indicator (read-only filled circle if done, empty circle if not) + issue count badge if the asset has open issues
- **Bottom action area** — varies by state (see table below)

Tapping an asset row navigates to Screen 3 regardless of lock state — viewing is always allowed; editing is gated by locking rules.

### Bottom action area states

| Track | State | Bottom content |
|---|---|---|
| Maintenance | Not started | "Start maintenance" button + simulate geofence toggle |
| Maintenance | Started, not ended | Status line: *"Maintenance in progress. Tap back to end session."* No button |
| Maintenance | Ended, not submitted | Status line: *"Completed. Editable until submitted at 6pm."* No button |
| Maintenance | Submitted | Lock icon + *"View only"* |
| Alarm | Started, not resolved | "Resolve alarm" button |
| Alarm | Resolved | Lock icon + *"View only"* + **Additional notes** input (text field + "Add note" button) — open until 6pm |

### Starting maintenance — geofence flow

1. Technician taps "Start maintenance"
2. Backend (or frontend simulate toggle) checks whether the technician is at the base station
3. **If check fails:** error modal — *"You must be at base station {site_id} to start this maintenance schedule."* [OK]. Session is NOT started.
4. **If check passes:** record `started_at`, set `geofence_verified = true`, unlock editing. Create an `InspectionResponse` for every asset at the base station (do not create lazily).

Editing after start is not geography-restricted. The geofence check only gates the start action.

### Exit navigation — back button rules

| Track | State | Behaviour |
|---|---|---|
| Either | Locked or never started | Navigate back immediately. No prompt. |
| Alarm | Started, not resolved | Modal: *"Leave without resolving this alarm?"* [Cancel] [Leave]. **Leave** exits without resolving; session stays open. |
| Maintenance | Started, not ended; all asset checklists fully checked | Modal: *"End maintenance?"* [Cancel] [Yes]. **Yes** marks done + records `ended_at` + navigates back. |
| Maintenance | Started, not ended; some checklists incomplete | Modal: *"Some maintenance tasks have not been completed. End maintenance anyway?"* [Continue maintenance] [End maintenance]. **Continue maintenance** closes modal, stays on Screen 2. **End maintenance** marks done (only fully checked assets) + records `ended_at` + navigates back. |

Ending a session always results in status `Complete`, even if some assets were left incomplete. There is no "partially ended" state.

### Endpoints

#### GET `/api/work-orders/{id}/`
Maintenance track detail for Screen 2.

**Response 200:**
```json
{
  "id": "uuid",
  "base_station": {
    "id": "uuid",
    "site_id": "OY0735",
    "name": "string",
    "site_classification": "platinum",
    "clients": ["MTN"],
    "manager": { "id": "uuid", "name": "string" }
  },
  "status": "open",
  "started_at": null,
  "ended_at": null,
  "submitted": false,
  "submitted_at": null,
  "geofence_verified": false,
  "updated": "2026-07-26T08:00:00Z",
  "assets": [
    {
      "id": "uuid",
      "name": "string",
      "inspection_response": {
        "id": "uuid",
        "done": false,
        "issue_count": 2
      }
    }
  ]
}
```

---

#### GET `/api/alarms/{id}/`
Alarm track detail for Screen 2.

**Response 200:**
```json
{
  "id": "uuid",
  "base_station": {
    "id": "uuid",
    "site_id": "OY0735",
    "name": "string",
    "site_classification": "platinum",
    "clients": ["MTN"],
    "manager": { "id": "uuid", "name": "string" }
  },
  "raised_at": "2026-07-26T08:00:00Z",
  "resolved_at": null,
  "resolved_by": null,
  "updated": "2026-07-26T08:00:00Z",
  "assets": [
    {
      "id": "uuid",
      "name": "string",
      "inspection_response": null
    }
  ],
  "notes": []
}
```

---

#### POST `/api/work-orders/{id}/start/`
Starts the maintenance session. The `geofence_verified` field records whether the check passed — do not trust the client claim blindly; verify server-side when real geofencing is implemented.

**Request:**
```json
{ "geofence_verified": true }
```
**Response 200:**
```json
{ "started_at": "2026-07-26T09:00:00Z", "geofence_verified": true }
```
**Response 400 (already started):** `{ "detail": "Work order already started." }`
**Response 403 (geofence failed):** `{ "detail": "You must be at base station OY0735 to start this maintenance schedule." }`

---

#### POST `/api/work-orders/{id}/end/`
Ends the maintenance session. Backend marks `done=true` on every `InspectionResponse` whose checklist is fully checked.

**Request:** No body.
**Response 200:**
```json
{ "ended_at": "2026-07-26T14:00:00Z", "assets_marked_done": ["uuid"] }
```
**Response 400:** `{ "detail": "Work order not started." }` | `{ "detail": "Work order already ended." }`

---

#### POST `/api/alarms/{id}/resolve/`
Resolves the alarm. Locks the alarm track immediately. Technician identity recorded as `resolved_by`.

**Request:** No body.
**Response 200:**
```json
{
  "resolved_at": "2026-07-26T11:00:00Z",
  "resolved_by": { "id": "uuid", "name": "string" }
}
```
**Response 400:** `{ "detail": "Alarm already resolved." }`

---

#### POST `/api/alarms/{id}/notes/`
Adds a note to a resolved alarm. Blocked after 6pm.

**Request:** `{ "text": "string" }`
**Response 201:**
```json
{ "id": "uuid", "text": "string", "created": "2026-07-26T15:00:00Z" }
```
**Response 400 (not resolved):** `{ "detail": "Alarm is not yet resolved." }`
**Response 403 (after 6pm):** `{ "detail": "Alarm notes cannot be added after 6pm." }`

---

## 7. Screen 3 — Asset Maintenance Page

### Layout

Title: asset name. Back button → Screen 2.

Three sections, all sharing the same lock state:

1. **Checklist** — list of `PMQuestion`s for this asset, each with a checkbox. Every toggle saves immediately and updates the work order's `updated` timestamp.
2. **Select all that apply** — grid of `Condition` chips for this asset's category (plus global conditions). Toggle saves immediately.
3. **Outstanding issues** — list of logged issues, each with a remove button (while unlocked). Below the list: an "Add issue" form with a description text field, severity selector (Low / Medium / High / Critical), and "Add issue" button.

No explicit save or submit button. There is no separate "edit mode."

### Lock state

Editable if and only if:
- **Maintenance track:** work order `started_at` is set AND `submitted = false`
- **Alarm track:** alarm `resolved_at` is null (i.e., not yet resolved)

### Endpoints

#### GET `/api/inspection-responses/{id}/`
Full asset inspection record for Screen 3.

**Response 200:**
```json
{
  "id": "uuid",
  "work_order_id": "uuid",
  "asset": {
    "id": "uuid",
    "name": "string",
    "asset_category": { "id": "uuid", "name": "string" }
  },
  "issues_found": null,
  "done": false,
  "comments": "",
  "conditions": [
    { "id": "uuid", "name": "string" }
  ],
  "checklist_responses": [
    {
      "id": "uuid",
      "question": { "id": "uuid", "question": "string" },
      "checked": false
    }
  ],
  "issues": [
    {
      "id": "uuid",
      "description": "string",
      "severity": "high",
      "promoted_work_order": null
    }
  ],
  "created": "2026-07-26T09:00:00Z",
  "updated": "2026-07-26T09:00:00Z"
}
```

---

#### POST `/api/inspection-responses/`
Create an `InspectionResponse` for an asset within a work order. Normally created in bulk when the session starts — this endpoint handles any gaps.

**Request:**
```json
{ "work_order": "uuid", "asset": "uuid" }
```
**Response 201:** Same shape as GET above, with empty arrays.
**Response 400 (duplicate):** `{ "detail": "Inspection response already exists for this asset in this work order." }`
**Response 403 (locked):** `{ "detail": "This work order is locked." }`

---

#### PATCH `/api/inspection-responses/{id}/`
Update `issues_found`, `comments`, and/or `conditions`.

**Request (any subset):**
```json
{
  "issues_found": true,
  "comments": "string",
  "conditions": ["uuid", "uuid"]
}
```
**Response 200:** Updated inspection response object.
**Response 400:** `{ "detail": "At least one condition must be selected when issues are found." }`
**Response 403 (locked):** `{ "detail": "This work order is locked." }`

---

#### PATCH `/api/checklist-responses/{id}/`
Toggle a checklist item. Saves immediately.

**Request:** `{ "checked": true }`
**Response 200:**
```json
{ "id": "uuid", "checked": true, "updated": "2026-07-26T09:30:00Z" }
```
**Response 403 (locked):** `{ "detail": "This work order is locked." }`

---

#### POST `/api/issues/`
Add an outstanding issue to an inspection response.

**Request:**
```json
{
  "inspection_response": "uuid",
  "description": "string",
  "severity": "high"
}
```
**Response 201:**
```json
{
  "id": "uuid",
  "description": "string",
  "severity": "high",
  "promoted_work_order": null,
  "created": "2026-07-26T10:00:00Z"
}
```
**Response 403 (locked):** `{ "detail": "This work order is locked." }`

---

#### DELETE `/api/issues/{id}/`
Remove an outstanding issue. Only allowed while unlocked and before the issue is promoted to a work order.

**Response 204:** No content.
**Response 400 (already promoted):** `{ "detail": "Cannot delete an issue that has been promoted to a work order." }`
**Response 403 (locked):** `{ "detail": "This work order is locked." }`

---

#### GET `/api/conditions/?asset_category={id}`
Returns conditions available for an asset category — both category-specific and global (`asset_category=null`).

**Response 200:**
```json
[
  { "id": "uuid", "name": "Leaking" },
  { "id": "uuid", "name": "Corroded" }
]
```

---

## 8. Site Actions & Readings

These cover technician responsibilities beyond the routine checklist: diesel delivery supervision, diesel/run-hour monitoring, spare parts requests, and safety/HSE reporting. Available from Screen 2 (station detail) at any time — not gated on an active maintenance session — since deliveries and hazards can occur outside a visit. Hidden once the work order is locked (submitted).

Reports that roll these up (daily activity report, PM report, outstanding work, site visit report) are deferred — see Open Items.

### Meter Readings

#### GET `/api/meter-readings/?asset={id}`
List readings for assets at the technician's stations, optionally filtered by asset.

#### POST `/api/meter-readings/`
Body: `{ "asset": "uuid", "reading_type": "run_hours" | "diesel_level", "value": int, "unit": "hours" | "days" | "litres" | "mm", "date": "YYYY-MM-DD" (optional, defaults to today), "work_order": "uuid" (optional) }`

`recorded_by` is set from the authenticated user. `run_hours` typically pairs with `unit=hours`; `diesel_level` is a dipstick depth reading and pairs with `unit=mm` (matching the same measurement convention as diesel delivery tank levels below). `unit=litres` remains available for sites with a calibrated volume gauge.

### Diesel Deliveries

#### GET `/api/diesel-deliveries/?base_station={id}`
List deliveries at the technician's stations.

#### POST `/api/diesel-deliveries/`
Body: `{ "base_station": "uuid", "vendor": "uuid" (optional), "work_order": "uuid" (optional), "quantity_litres": int, "tank_level_before": int (millimetres, dipstick reading, optional), "tank_level_after": int (millimetres, dipstick reading, optional), "delivered_at": "ISO datetime" (optional, defaults to now), "notes": "" (optional) }`

Tank levels are raw dipstick depth in millimetres, not a percentage — the app does not know each tank's calibration curve, so it records what the technician physically reads off the stick. `recorded_by` is set from the authenticated user. Attach delivery ticket photos via `POST /api/attachments/` with `diesel_delivery=<id>`.

### Parts Requests

#### GET `/api/vendors/?type=supplier`
Picker list for suppliers (used by diesel delivery and part requests).

#### GET `/api/parts/?search={q}`
Picker list for parts by name.

#### GET `/api/part-requests/`
List the authenticated technician's own requests.

#### POST `/api/part-requests/`
Body: `{ "part": "uuid", "base_station": "uuid", "work_order": "uuid" (optional), "asset": "uuid" (optional), "quantity": int, "reason": "" (optional) }`

Created with `status="requested"`. No approval step — a store/manager approval workflow is deferred (see Decisions below).

#### POST `/api/part-requests/{id}/receive/`
Marks the request `status="received"` and sets `received_at`. Technician-initiated when the parts physically arrive. 400 if already received.

### Part Usage Log

Separate from a parts *request*: this records a part that was actually installed or consumed (e.g. an oil filter changed during PM), not one being ordered. Reuses the existing `PartUsage` model (previously admin/back-office only), now with a technician-facing endpoint plus an `asset` field — usage is per-asset, and the asset's station is derived via `asset.location.base_station` (no separate `base_station` field needed).

#### GET `/api/part-usages/?work_order={id}`
List usage entries at the technician's stations, optionally filtered by work order.

#### POST `/api/part-usages/`
Body: `{ "work_order": "uuid", "asset": "uuid", "part": "uuid", "qty_used": int, "notes": "" (optional) }`

`asset` is required (unlike the optional `asset` on a parts request) since usage is always tied to what it went into. `recorded_by` is set from the authenticated user.

### Safety / HSE Reports

#### GET `/api/safety-reports/`
List reports at the technician's stations.

#### POST `/api/safety-reports/`
Body: `{ "base_station": "uuid", "work_order": "uuid" (optional), "type": "incident" | "near_miss" | "hazard", "severity": "low" | "medium" | "high" | "critical", "description": "text" }`

`reported_by` is set from the authenticated user. Attach photos via `POST /api/attachments/` with `safety_report=<id>`.

### Attachments (generic photo upload)

#### POST `/api/attachments/` (multipart/form-data)
Fields: `file` (the image), `type` (free text, e.g. `"delivery_ticket"`, `"hazard_photo"`), and **exactly one** of `asset`, `work_order`, `diesel_delivery`, `safety_report`. Saved to local media storage in dev; returns the created `Attachment` with a `file_url`. 400 if zero or more than one owner is given.

### Decisions

- No client sign-off step for Service Completion or Part Request receipt — the technician marking it done/received is sufficient.
- Part request approval (store/manager) is skipped for now; status is only `requested` → `received`.
- Daily facility-manager review meetings are not tracked in the app.

---

## 9. Issue → Work Order Promotion

At submission time (technician ends a session or 6pm auto-submit), every `Issue` with `promoted_work_order=null` is converted to a corrective `WorkOrder`:

| Issue field | WorkOrder field |
|---|---|
| `description` | `description` |
| `severity` | `priority` |
| `inspection_response.asset` | `asset` (XOR target) |
| (fixed) | `type = "corrective"` |
| (fixed) | `status = "open"` |
| (not set) | `assigned_technician = null` |

After creation, set `Issue.promoted_work_order = <new WorkOrder>`. This makes the issue non-deletable.

> **Open question:** Should the corrective `WorkOrder` link back to the source maintenance `WorkOrder` for traceability? Not yet decided. Resolve before implementing promotion.

---

## 10. Background Jobs (Celery — not yet implemented)

### 6pm daily cutoff
Runs at 18:00 every day:
1. Find all `WorkOrder` records where `submitted=False` and `due_date=today`
2. For those with `started_at` set and `ended_at` null: set `ended_at=now()`
3. Run "mark done" on each: set `InspectionResponse.done=True` for any fully-checked assets
4. Set `submitted=True`, `submitted_at=now()` on all of them
5. Promote all unpromoted `Issue`s to corrective `WorkOrder`s
6. `AlarmNote` cutoff is enforced by time check at the API level (no model flag needed)

### Next-day refresh
Runs at the start of each new working day:
1. Generate new maintenance `WorkOrder`s from active `PMSchedule` records
2. Carry over `Alarm` records with `resolved_at=null` — do not reset or duplicate them
3. Archive/soft-delete `Alarm` records with `resolved_at` set (hard delete vs. archive TBD)

---

## 11. Things to Pay Attention To

### `InspectionResponse` created at session start
When a technician starts a session (POST `/start/`), create an `InspectionResponse` for every asset at the base station in the same request. Do not create them lazily on first edit. This ensures Screen 2's asset list always has a concrete `inspection_response.id` to link to Screen 3.

### Alarm → base station path
`Alarm` links to `Asset`, not `BaseStation` directly. To query alarms at a base station:
```python
Alarm.objects.filter(asset__location__base_station=station)
```

### `issues_found` + conditions constraint
If `InspectionResponse.issues_found = True`, at least one `Condition` must be selected. Enforce in the serializer — return 400 if `issues_found=true` and `conditions=[]`.

### Conditions query includes globals
When fetching conditions for an asset category, return both `asset_category=<id>` AND `asset_category=null` (global) records in a single response.

### Geofencing
`WorkOrder.geofence_verified` records whether the geofence check passed. The `/start/` endpoint currently trusts the client's claim (`geofence_verified: true`). When real geofencing is implemented, validate coordinates server-side and set the field based on that — not the client payload.

### Alarm notes time gate
`AlarmNote` does not have a model-level "closed" flag. The 6pm cutoff is enforced by the API: check `datetime.now().time() >= time(18, 0)` on the POST `/api/alarms/{id}/notes/` view and return 403 if so.

### Responsive layout
The frontend has two layouts: phone (<600px) and tablet split-view (≥600px). The API contract is identical for both — no separate endpoints or response shapes.

### WorkOrder status field
The existing `status` choices (`open`, `in_progress`, `complete`, `cancelled`) are for maintenance/corrective work orders. Do not add alarm-specific status values (`triggered`, `resolved`) to this field — alarm state is tracked on the `Alarm` model via `raised_at` / `resolved_at`.

---

## 12. Open Items

- [x] Alarm rows on Screen 1: one row per `Alarm` record (decided)
- [x] No sign-off/approval step for Service Completion or Part Request receipt (decided)
- [x] No parts-request approval workflow for now — requested → received only (decided)
- [x] Daily facility-manager review meetings are out of scope, not tracked (decided)
- [ ] Should corrective `WorkOrder`s promoted from `Issue`s back-link to the source maintenance `WorkOrder`?
- [ ] Hard delete vs. soft delete/archive for resolved `Alarm`s on next-day refresh
- [ ] Real geofencing implementation (replace simulate toggle with server-side coordinate check)
- [ ] Celery setup and beat schedule
- [ ] Generated reports — deferred to a later phase: Daily Technician Activity Report, Preventive Maintenance Report, Outstanding Work list, Site Visit Report, Service Completion (all derivable from `WorkOrder`/`InspectionResponse`/`Issue`/`MeterReading`/`DieselDelivery` data already captured)
- [ ] Diesel consumption reporting (combining `MeterReading` diesel-level readings with `DieselDelivery` quantities into a computed consumption figure) — raw capture exists now; the computed report is deferred with the other reports above
- [ ] No file-storage decision made for production `Attachment` uploads (currently local dev storage via `MEDIA_ROOT`) — revisit before deploying (S3 or similar)
