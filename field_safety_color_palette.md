# Field safety color palette

Finalized palette for the CMMS mobile app. Light mode only — no dark-mode
variants required.

## Neutrals

| Role | Hex | Usage |
|---|---|---|
| Primary | `#0F766E` | Primary buttons, active tab underline, links, icons that need brand emphasis |
| Accent | `#EA580C` | High-emphasis calls to action — e.g. "Start maintenance," "Resolve alarm" |
| Background | `#FAFAF9` | App/page background |
| Surface | `#FFFFFF` | Cards, info tiles, modals |
| Border | `#E7E5E4` | Hairlines, dividers, card outlines |
| Text primary | `#1C1917` | Headings, primary body text |
| Text muted | `#78716C` | Secondary text, timestamps, helper copy |

## Status colors

These five carry the actual state communication throughout the app (badges,
lock icons, dimmed rows) — they're the ones worth testing for contrast first.

| Status | Hex | Used for |
|---|---|---|
| Not started | `#A8A29E` | Maintenance not yet begun |
| Ongoing | `#EAB308` | Maintenance in progress |
| Complete | `#15803D` | Maintenance ended (before or after submission) |
| Triggered | `#DC2626` | Active, unresolved alarm |
| Resolved | `#57534E` | Resolved alarm (deliberately muted — resolved status shouldn't compete visually with an active Triggered alarm) |

## Usage notes

- **Text-on-color contrast**: when placing text on any status/accent swatch,
  use the darkest shade from that same color family rather than plain black —
  e.g. dark orange text on a light-orange accent tint, not `#000000`.
- **Locked/dimmed rows** (submitted maintenance, resolved alarms): apply
  reduced opacity (~55%) to the row rather than a separate muted color token —
  keeps the palette small and the "this is locked" signal consistent across
  contexts.
- **Do not repurpose the Accent orange for anything except primary
  calls-to-action.** If it starts showing up on decorative elements it'll
  compete with the Triggered red for visual priority, which is the one thing
  this palette needs to avoid — an alarm needs to read as more urgent than a
  button.
