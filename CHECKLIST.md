# Asset Management — Path to Mobile Deployment

## Working rule

**A question is not a command. A checklist does not mean build or implement something. What I ask is exactly what I mean.**

- If I ask a question, answer it. Don't change code.
- If I ask for a checklist, plan, or list, write it. Don't start working through it.
- Only work on a checklist item when I explicitly say to, and only on the item(s) I name.
- When an item is done, tick it here and stop. Don't roll on to the next one.

---

## Already done (for reference)

- [x] Backend models, API, and admin for diesel delivery, part requests, part usage, safety reports, and meter readings (mm)
- [x] Hi-fi screens for Diesel Delivery, Part Request, Part Usage, and Safety Report, linked from Work Order Detail, Asset Maintenance, and the Station List Diesel tab
- [x] Web build runs against the real backend (API URL and mock mode come from env vars, token storage works on web, login errors show inline)
- [x] Git: root repo (backend and docs) and mobile repo, both committed
- [x] Demo users: `tech1` / `tech1pass`, `appleveil` / `demo-pass-1`
- [x] Bug fix: starting a session now creates an `InspectionResponse` for every active asset at the station, not just the first one — every asset row is clickable
- [x] Bug fix: checklist items no longer visually reorder after being toggled (stable `created` ordering)
- [x] Bug fix: the Comments field no longer fires a network request per keystroke (saves on blur)
- [x] Manual "Mark complete" button on the asset checklist (not automatic): requires either a fully-checked checklist or a comment explaining why not; Generator assets additionally require today's run-hours and diesel-level readings. Auto-navigates back after completing; reopen toggle and button label audited
- [x] Meter readings: monotonic validation (run hours can't decrease; diesel level can't increase except via a logged delivery)
- [x] Diesel delivery now updates the generator's diesel-level reading automatically; "Log diesel delivery" removed and "Request parts" hidden (not deleted) from Site Actions; Part Usage moved to the per-asset screen and auto-uses the asset being checked
- [x] New Asset Catalog admin screen — list/add/edit/delete asset categories and their checkpoint questions
- [x] New Alarm Simulator screen — station/asset picker, raises a test alarm for demo purposes
- [x] Login screen simplified to a single "Enter" button (demo auth, no email/password fields)
- [x] Seed data expanded from 2 to 5 base stations (Victoria Island, Lekki, Ikeja, Wuse II, Port Harcourt GRA)
- [x] `app.json`: real app name ("CMMS Field Maintenance"), slug, and Android package (`com.cmms.assetmanagement`) — was the Phase 6 placeholder
- [x] Mock data layer fully rewritten to mirror the real backend (5 stations, 25 assets, realistic per-asset states) with its own regression tests, so the app is fully navigable/demoable with no backend at all
- [x] `eas.json` configured with three build profiles: `tester` (mock data, installable APK, for sharing with people who have no backend access), `preview` (real backend via LAN IP, APK), `production` (app-bundle, placeholder)
- [x] Backend tests (80) and frontend tests (15) passing

---

## Phase 1 — Web walkthrough & sign-off

- [ ] Reseed a clean database (`python manage.py shell < seed.py` or equivalent) before testing
- [ ] Login → Station List, all 4 tabs (Routine, Alarms, Tasks, Diesel)
- [ ] Station Detail → start session → Asset Maintenance: checklist, issues, readings → end session
- [ ] Diesel Delivery: create a record from the Diesel tab **and** from Site Actions, then check both in Django admin
- [ ] Part Request: create one, mark it received
- [ ] Part Usage: log usage against an asset and confirm it appears under "Logged this visit"
- [ ] Safety Report: create one and confirm it in admin
- [ ] Alarm: add a note, then resolve it
- [ ] Logout, then refresh to confirm you're logged out. Log in, refresh, and confirm the session is restored
- [ ] Check error states: wrong password, backend down, empty required fields
- [ ] Record any bugs found here as new unchecked items
- [ ] **Sign-off: web flow approved**

## Phase 2 — Open product decisions

- [ ] Offline support: do technicians need to capture data with no signal (common at remote sites)? Decide this first, because it affects the architecture of everything built in Phase 3
- [ ] Distribution: public store listings, or private/internal distribution (Apple Business Manager / Google managed Play)? This decides which accounts Phase 8 needs and what Phase 10 involves
- [ ] Diesel Delivery entry point: keep the **Diesel tab** or the **Site Actions button**, then remove the other
- [ ] Photo attachments (delivery ticket, safety report photos): build now with `expo-image-picker`, or defer
- [ ] Asset request: define core details (noted as "later")
- [ ] Should corrective work orders promoted from Issues link back to the source work order?
- [ ] Resolved alarms on next-day refresh: hard delete or archive?
- [ ] Geofencing: real server-side coordinate check, or keep the simulate toggle for v1?
- [ ] Reports (daily activity, PM, outstanding work, site visit, diesel consumption): confirm they're out of scope for v1

## Phase 3 — Build the decided items

- [ ] Fix logout: add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS` and migrate, so tokens are actually revoked (existing bug: logout looks fine in the app, but the token stays valid until it expires)
- [ ] Remove the rejected Diesel entry point
- [ ] Photo attachments, if approved
- [ ] Issue → Work Order promotion, if in v1
- [ ] Geofencing, if in v1
- [ ] Offline queueing, if in v1
- [ ] Tests for each of the above
- [ ] Re-run the Phase 1 walkthrough on web

## Phase 4 — Backend hardening (before any real device talks to it)

- [ ] Move `SECRET_KEY`, DB credentials, and `DEBUG` into environment variables
- [ ] `DEBUG = False` in production
- [ ] Restrict `ALLOWED_HOSTS` (currently `*`)
- [ ] Restrict CORS (currently `CORS_ALLOW_ALL_ORIGINS = True`)
- [ ] Review JWT token lifetimes (access/refresh) for field use
- [ ] Production file storage for attachments (S3 or similar), since uploads currently go to local `MEDIA_ROOT`
- [ ] Static files: `collectstatic` plus WhiteNoise or a CDN
- [ ] Celery + beat for the scheduled jobs (6pm note cutoff, next-day refresh), if in v1
- [ ] Run `python manage.py check --deploy` and clear its warnings
- [ ] Pin `requirements.txt` versions

## Phase 5 — Backend deployment

- [ ] Choose a host (e.g. Railway, the same as Leyyow Affiliates)
- [ ] Provision a managed PostgreSQL database
- [ ] Deploy, run migrations, and create a superuser
- [ ] Load real data (stations, assets, checklists, personnel), not the demo seed
- [ ] HTTPS on a stable domain (the mobile app needs a fixed API URL)
- [ ] Set up database backups
- [ ] Error monitoring (e.g. Sentry) and logging
- [ ] Smoke test: log in against production from the web build

## Phase 6 — Native app setup

- [x] `app.json`: real app name, slug, and Android `package` (`com.cmms.assetmanagement`)
- [ ] iOS `bundleIdentifier`
- [ ] App icon and splash screen in Field Safety branding
- [ ] Permissions strings (camera/photos if attachments are built; location if geofencing is built)
- [ ] Run `npx expo install --fix` to align SDK versions
- [ ] `npm run typecheck` and `npm test` pass

## Phase 7 — Native dev builds & device testing

- [ ] `npx expo run:ios` on the simulator
- [ ] `npx expo run:android` on the emulator
- [ ] Physical device on local network: `EXPO_PUBLIC_API_URL=http://<mac-LAN-IP>:8002/api` with `runserver 0.0.0.0:8002`
- [ ] Repeat the Phase 1 walkthrough on iOS
- [ ] Repeat the Phase 1 walkthrough on Android
- [ ] Native-specific checks: SecureStore token persistence, keyboard covering inputs, numeric keypads, back gestures, small screens, poor network
- [ ] Fix and re-test any native-only bugs

## Phase 8 — Store accounts & EAS

*Note: a separate, smaller track is already underway — an internal-distribution APK built from the `tester` profile (mock data, no backend needed) to hand to a handful of people ahead of full store deployment. That only needs `eas login` (interactive, done in your own terminal) + `eas build --profile tester`, not the full store-account setup below.*

- [ ] Apple Developer account ($99/yr) and Google Play Console account ($25 one-time), plus Apple Business Manager / managed Google Play if Phase 2 chose private distribution
- [ ] `eas login`, `eas build:configure` — `eas.json` already exists with `tester`/`preview`/`production` profiles
- [ ] Set `EXPO_PUBLIC_API_URL` per profile (preview → staging/prod API, production → prod API)
- [ ] Signing credentials (let EAS manage them, or upload your own)

## Phase 9 — Internal test release

- [ ] `eas build --profile preview`: iOS to TestFlight, Android as an internal testing APK/AAB
- [ ] Install on real technicians' phones
- [ ] Field test at an actual base station (signal, sunlight readability, gloves, real workflow)
- [ ] Collect feedback and log issues here
- [ ] Fix, rebuild, and re-test until approved
- [ ] **Sign-off: field test approved**

## Phase 10 — Production release

- [ ] Privacy policy URL (required by both stores)
- [ ] Distribution setup, based on the Phase 2 decision: public store listings (description, screenshots, category), or private distribution configuration
- [ ] `eas build --profile production`
- [ ] `eas submit` to the App Store and Play Store
- [ ] Pass store review
- [ ] Onboard technicians: create accounts, assign stations, set up a password reset process
- [ ] Decide on an update strategy: `eas update` (OTA) for JS fixes, store builds for native changes
- [ ] **Released**
