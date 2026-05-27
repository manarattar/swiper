# SwipeEat Project Log

Last updated: 2026-05-27

## Current State

SwipeEat is now a deployed Flask restaurant ordering app with:

- Customer menu ordering with a persistent cart.
- Swipe-based meal discovery and matched-meal ordering.
- Multi-item checkout with customer name, phone, table number, item notes, order notes, taxes, service fee, and totals.
- Customer order confirmation, receipt, and tracking pages.
- Admin dashboard for menu, orders, payments, settings, analytics, exports, inventory, QR codes, monitoring, and notifications.
- Kitchen dashboard with live orders, status controls, ETA controls, timers, delayed-order highlighting, and a shortcut back to admin.
- PostgreSQL support for Render production.
- Server-sent events for live order/status/payment/ETA updates.
- Trainable ML food embedding recommender for swipe-based recommendations.
- Production safety features including admin authentication, CSRF protection, secure headers, rate limits, order pause settings, and production warnings.

Production deployment:

- GitHub repo: `manarattar/swiper`
- Render app: previously deployed as `swiper-2xu5.onrender.com`
- Latest deployed commit: `16c7902 Add advanced order operations`
- Latest Render deploy triggered: `dep-d7r5d7hj2pic73f4te40`

Current verification:

- `python -m py_compile backend.py server.py tests\test_app.py`
- `python -m unittest discover -v`
- Latest passing suite: 38 tests

ML recommender:

- Added `ml_recommender.py` with a trainable TF-IDF food embedding model.
- Added `scripts/train_food_model.py` for training from Food.com/recipe CSV data.
- The app loads `ml_food_model.json` or `FOOD_ML_MODEL_PATH` when available.
- If no model artifact exists, the app falls back to a model built from the local menu.
- See `ML_RECOMMENDER.md` for training instructions.

## Completed Milestones

### Core App

- Built the original swipe flow for meal discovery.
- Added preference tracking and top meal recommendations.
- Connected recommended meals to the shared cart.
- Added a normal menu page that uses the same meal data.
- Connected swipe flow and menu flow so users can move between them with cart state preserved.

### Ordering

- Added order creation from the menu.
- Added multi-item cart ordering instead of one meal per order.
- Added item-level notes and order-level customer notes.
- Added table number support and QR table links.
- Added customer name and phone fields.
- Added stock decrementing and automatic sold-out hiding.
- Added customer order history in the current session.

### Checkout

- Built a professional checkout review modal.
- Added editable quantities before checkout.
- Added backend authoritative subtotal, tax, service fee, and total calculations.
- Added restaurant settings for tax and service fee.
- Added confirmation page after checkout.
- Added receipt page by tracking token.
- Added customer tracking page.

### Admin

- Added admin login/logout.
- Added menu CRUD.
- Added order list and analytics.
- Added order status controls.
- Added payment status controls: unpaid, paid, refunded.
- Added order detail modal.
- Added order search.
- Added inventory view.
- Added QR code generator.
- Added CSV exports for orders and meals.
- Added restaurant settings panel.
- Added production monitoring panel.
- Added production warning display.
- Added notification center for order/payment events.

### Kitchen

- Added kitchen dashboard.
- Added active/new/preparing/completed/cancelled tabs.
- Added large status action buttons.
- Added customer note visibility.
- Added payment badge visibility.
- Added admin dashboard shortcut.
- Added live update support.
- Added order timers.
- Added delayed-order highlighting.
- Added editable ETA controls.

### Live Updates

- Added server-sent event stream for admin/kitchen: `/admin/events`.
- Added customer order event stream: `/orders/<token>/events`.
- Published events when orders are created.
- Published events when order status changes.
- Published events when payment status changes.
- Published events when ETA changes.
- Reduced fallback polling from 5 seconds to 30 seconds.

### Operations And Audit

- Added app event logging for order and payment activity.
- Added order history table.
- Tracked order created, status changes, payment changes, and ETA changes.
- Added actor tracking for admin changes.
- Added history to order JSON and admin order detail modal.

### Production And Deployment

- Added Render deployment config/docs.
- Added PostgreSQL support.
- Fixed PostgreSQL lowercase column mapping issue.
- Added migration-safe schema column creation.
- Added secure headers.
- Added CSRF protection for admin mutations.
- Added rate limits for admin login and order attempts.
- Added order pause setting and customer-facing pause message.
- Added `.env.example`.
- Pushed multiple production commits and triggered Render deploys.

## Important Fixes

- Fixed `KeyError: 'meatKind'` on Render caused by PostgreSQL lowercase column names.
- Fixed match-page add-to-cart behavior so adding matched meals does not force navigation to menu.
- Fixed JavaScript syntax issue around order notification text.
- Fixed Postgres migration/default issues for new order fields.
- Kept cart state connected between swipe recommendations and menu.

## Current Product Strengths

- The app can operate as a real digital restaurant ordering workflow.
- Admin can see live orders immediately.
- Kitchen can update orders without refreshing.
- Customers can track order progress.
- Orders have enough metadata for operations: table, contact, notes, payment, ETA, status, history.
- Restaurant settings make the app configurable without code edits.
- PostgreSQL support makes the production app persistent on Render.
- Test coverage now protects most core flows.

## Known Limitations

- Payments are not real yet; payment status is manual.
- No email or SMS notifications yet.
- No role-based staff accounts beyond the current admin login model.
- SSE events are in-process; if Render is later scaled to multiple workers/instances, a shared event backend may be needed.
- No formal backup/restore UI yet.
- No custom domain/canonical public URL setting yet.
- No full end-to-end browser tests yet.

## Planned Next Work

### Priority 1: Deployment Hardening

- Add `/healthz` endpoint that checks app, database, and schema readiness.
- Add Render-friendly health check response.
- Add admin-visible database/schema status details.
- Add startup logging for environment mode, database type, and warning state.

### Priority 2: Backup And Export Center

- Create a clear admin backup/export page.
- Keep existing orders/meals CSV exports.
- Add operational export for app events and order history.
- Add one-click backup bundle option if practical.

### Priority 3: Receipt And Tracking Polish

- Upgrade receipt layout with restaurant info, timeline, payment status, order items, totals, and tracking link.
- Add clearer customer order timeline states.
- Add live ETA messaging on tracking page.
- Add printable receipt styling.

### Priority 4: Admin Audit Filters

- Add filters for notifications/events by source, date, order id, actor, status, and payment event.
- Add order history search from admin.
- Add direct links from notification rows to order details.

### Priority 5: First-Run Setup Guard

- Show a strong admin banner if default password is still used.
- Show a warning if `SECRET_KEY` is still the dev fallback.
- Show a warning if production security settings are disabled.
- Add setup checklist inside admin.

### Priority 6: Custom Domain Readiness

- Add public app URL setting.
- Use canonical app URL for receipts, QR codes, tracking links, and future payment callbacks.
- Prepare docs for connecting a custom domain on Render.

### Priority 7: Real Payments

- Add Stripe Checkout.
- Create checkout sessions from backend totals only.
- Store payment provider session/payment IDs.
- Add webhook endpoint for payment confirmation.
- Automatically mark orders as paid from Stripe webhook.
- Keep manual payment status override for cash/in-person payments.

### Priority 8: Staff Roles

- Add separate admin, kitchen, and manager roles.
- Restrict kitchen to order operations only.
- Restrict settings/export/security controls to manager/admin.
- Track actor names in order history more accurately.

### Priority 9: Notifications

- Add email receipts.
- Add SMS order updates if a provider is chosen.
- Add kitchen sound/notification controls.
- Add browser notification permission flow for kitchen/admin.

### Priority 10: Browser-Level QA

- Add Playwright smoke tests for menu checkout, admin login, kitchen order update, and customer tracking.
- Add mobile viewport checks for menu, checkout, admin, kitchen, receipt, and tracking pages.
- Add screenshots to catch layout regressions.

## Suggested Immediate Next Step

Start with Priority 1 and Priority 2 together:

- Add `/healthz`.
- Add backup/export center.
- Add order history/app event CSV exports.

This makes the deployed app easier to operate safely before adding real payments.
