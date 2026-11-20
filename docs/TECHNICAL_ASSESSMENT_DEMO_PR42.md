# PR #42 — Delivery UX & Date Consistency

## What changed

1. **Compact delivery follow-up cards.** Each signal now has a content area (type, title, evidence-backed detail) and a distinct action area (severity and "Inspect in Project Memory"). A two-column layout uses available desktop width, while smaller viewports stack controls without the misaligned extra grid row seen in PR #41.
2. **Contextual return path.** Delivery → Project Memory displays a "Back to Delivery Intelligence" button. Opening Project Memory directly or from executive navigation does not show a misleading contextual back button. Links still select an existing Memory *section*, not an individual record.
3. **Date semantics.** Project Memory displays the planned finish and the separately recorded forecast finish; missing forecasts explicitly say **Not recorded**. It never substitutes the planned date for a forecast. Delivery Intelligence uses the same missing-forecast terminology and only computes variance when both values exist.
4. **Date-only timezone correction.** Project Memory formats governed date-only fields using noon UTC and an explicit UTC timezone. This avoids the previous one-day shift for browsers in America/Bogota, where an ISO date parsed as midnight UTC appeared as the prior calendar date.

## Safety and scope

- All changes are UI/read-model display and navigation; governed state and server API models are unchanged.
- No new seed, automatic change, paid AI API call, database migration or Railway service.
- All data shown remains permission-scoped to the selected signed-in project.

## Validation

CI runs Python 3.11/3.12 tests, Next.js lint/build, synthetic Docker demo/UAT, and staging config. A small regression test additionally checks the date semantics, UTC formatting, guided navigation and compact signal layout at the source level. The source-level tests are *not a real browser automation substitute*.

### Manual UAT after merging

On the existing Windows Docker demo, from `C:\Users\Usuario\PMWizard`:

```powershell
git pull origin main
docker compose --env-file .env.demo -f compose.demo.yml up -d --build --force-recreate --no-deps demo-web
```

Do not destroy volumes or reseed local project data.

1. Open `http://localhost:3000`, select **Atlas Delivery — Synthetic Demo**.
2. Inspect the **Delivery follow-up queue** on desktop width: label, title, status and inspect button should be aligned without extra empty rows.
3. Select **Receive vendor integration sign-off**: Memory should open **RAID**, show the blocked dependency and offer **Back to Delivery Intelligence**.
4. Return, select **Select staged rollout strategy**: Memory should open **Decisions**; the back button should work.
5. Select **Project Memory** directly from the sidebar: return button should not appear.
6. Compare Planned finish on Delivery with Planned finish in Memory on a browser set to America/Bogota. They should show the **same calendar date**. If forecast is absent, Memory must say **Forecast: Not recorded**, not pretend the planned date is the forecast.
7. Use narrow/mobile width to verify card controls wrap accessibly without horizontal overflow.
8. Confirm that no status or governed record changes merely through navigation.

## Assessment talking point

PMWizard distinguishes *schedule baseline* from *current forecast* and opens governed evidence from delivery signals without inventing predictions. The project dashboard remains local and synthetic until a separately authorized cloud deployment.
