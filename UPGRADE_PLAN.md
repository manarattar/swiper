# SwipeEat product upgrade plan

## Goal and positioning

SwipeEat is for diners choosing and ordering food at a restaurant table on a 390px phone, and for staff running service on a 1024-1440px tablet or laptop. **Find food you will love, order it from your table, and follow it to the table.** The experience should feel like a real restaurant service: appetising food first, clear choices, trustworthy totals and status, and calm operational screens.

Design read: a restaurant ordering product for diners and staff, using warm editorial food photography and precise utility layouts to make discovery and ordering obvious in the first viewport. Visual variance 6/10; motion energy 3/10; information density 4/10 for diners, 7/10 for staff. Primary asset: real dish photography. Navigation: short diner journey with a persistent cart, and a compact staff workspace. Avoid fake AI claims, stock food used as a substitute for actual menu images, giant empty heroes, emoji as primary icons, and repeated generic card grids.

## Audit of the current product

| Screen / files | Findings |
| --- | --- |
| `/` `templates/welcome.html` | Screenshot shows a tiny tutorial card in a wide flat peach field. The first action is hidden until three scripted gestures; touch listeners are on `document`, so normal page swipes can advance it. The sample dish, small copy and step text explain a demo instead of letting a guest order. Inline palette and blue buttons disagree with other pages; mojibake arrow glyphs are visible in source. A keyboard-only user can advance, but the changing instruction has no live-region announcement. |
| `/food-swipe` `templates/index.html`, `static/styles.css`, `static/script.js` | Swipe mechanics, progress, buttons and undo exist, but the page still uses an isolated card and a Font Awesome CDN. `fetchCurrentMeal()` leaves the whole page hidden on empty or failed responses; image failure leaves a blank image. Requests log errors only to console. The card captures pointer events over its controls; keyboard arrows are global rather than scoped. No cart indicator or direct menu escape. |
| `/meal-of-the-day` `templates/meal_of_the_day.html` | Match results and add-to-cart exist, but the page has another inline design system, a large metadata panel and global order fields. Its copy and layout should present a short taste summary, honest match reasons, and food-led choices. Verify result links and cart handoff when redesigning; retain recommendation scoring and endpoint behavior. |
| `/menu` `templates/menu.html` | Screenshot confirms search, table, contact, session, AI prompt, quantity, notes and diet controls consume the first viewport before dishes. Quantity and notes apply globally, then appear again in item detail; table/name/phone appear again at checkout. `Popular` means low stock or a nonzero price (`mealMatchesCategory()`), so its label is false. `setStatus()` assigns `innerHTML` to a server error string; use text content. `addToCart()` checks only the new quantity against stock, not the existing quantity. Cart totals are calculated in JS and need a clear server-authoritative checkout result; fixed `$` formatting ignores `restaurant_settings.currency`. The menu already has detail and review dialogs and localStorage cart, so refine them rather than duplicate them. Search/filter failures and zero results lack useful recovery. |
| `/landingpage` `templates/landingpage.html` | Screenshot shows a nearly empty dark first viewport and a different fork/hexagon logo in the hero asset. The page loads a large image lazily, has no visible product promise in HTML hero copy, uses hardcoded `/` and `/menu` navigation in inline handlers, and has a two-second custom scroll that ignores reduced-motion preference. Tutorial screenshots and gallery are long and vague; copy such as "innovative" and "pioneers" does not show the ordering workflow. |
| Confirmation / tracking / receipt `templates/order_confirmation.html`, `order_tracking.html`, `receipt.html` | These files are **not empty in this checkout** (2,520 / 4,378 / 2,557 bytes). `server.py` renders them at `/order-confirmation/<token>`, `/order/<token>`, `/receipt/<token>`; the menu sends the guest to confirmation after POST `/orders`. Each is compressed into one-line HTML with its own inline CSS. Hardcoded `$` ignores restaurant currency. Tracking listens to `/orders/<token>/events` and polls, but only status and ETA update in the DOM: item list, total and payment text can go stale. Cancelled orders still show "Received" as active, with no cancellation explanation. Receipt is print-capable, but contact data is exposed on possession of the token, so avoid surfacing it unnecessarily. |
| `/kitchen` `templates/kitchen.html`, `server.py:admin_required` | Screenshot shows raw JSON `{"error":"Admin login required"}` on a browser visit: `/kitchen` is included in the decorator's JSON path prefix. Kitchen currently uses status tabs and cards rather than a spatial new/preparing/ready board. Fetch failures can leave "Updating" indefinitely; status/ETA mutations ignore non-2xx responses. The new-order sound/visual path exists but needs user-controlled audio, clear reconnection state and large tablet targets. |
| `/admin/login`, `/admin` `templates/admin_login.html`, `admin.html` | Login has another inline palette and no brand continuity. Admin combines analytics, settings, monitoring, meal editor, operations and list in one long page; the primary operational view is buried. Many small controls and dense rows need clearer grouping, focus states and permission/error feedback. Keep all existing management features and APIs. |
| Errors / infrastructure `templates/error.html`, `server.py`, `backend.py` | 404/500 handlers and a template already exist, but the page is generic and visually disconnected. Preserve JSON error contracts for APIs. `server.py` uses route prefixes in `wants_json_response()` and `admin_required()`, causing HTML/API confusion. Current CSP allows cdnjs styles/fonts, but chosen Google Fonts will need `fonts.googleapis.com` in `style-src` and `fonts.gstatic.com` in `font-src`. `PROJECT_LOG.md` mentions Render, while `DEPLOYMENT.md` says the live app is now on a Contabo VPS; treat the latter as deployment truth. `backend.py` seeds only an empty menu and has additive column helpers; production menu/order data must never be reset. |

## Design system

Use one SwipeEat **wordmark** treatment everywhere: a clean text wordmark with a small restrained plate or swipe mark, supplied as one local SVG plus a monochrome variant via CSS where possible. Replace the fork/hexagon mark in the landing hero. Let configured `restaurantName` remain the venue label; SwipeEat is the product brand. Use genuine existing dish images where they match real menu records, crop consistently at 4:3 or 1:1, provide descriptive alt text, and use a neutral illustrated placeholder only for missing images. Do not silently replace production dishes with sample content.

Implement tokens in `static/styles.css` and load it on all redesigned templates:

```css
:root {
  --color-canvas: #F8F5EF; --color-surface: #FFFEFB; --color-surface-quiet: #F1EBE2;
  --color-ink: #26221D; --color-muted: #655E55; --color-line: #DCD4C8;
  --color-brand: #9B3F2F; --color-brand-hover: #7D3023; --color-brand-soft: #F4E5DF;
  --color-olive: #56623D; --color-success: #28694B; --color-warning: #9B5B13;
  --color-danger: #A52F31; --color-focus: #245B85;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;
  --radius-sm: 8px; --radius-md: 14px; --radius-lg: 22px; --radius-pill: 999px;
  --shadow-card: 0 8px 28px rgba(38,34,29,.08);
  --shadow-sheet: 0 22px 70px rgba(38,34,29,.20);
}
```

Google Fonts: **DM Serif Display** for major headings and **DM Sans** for UI, weights 400/500/600/700. Fallback to Georgia and system sans. Scale: display 48/52 desktop and 36/40 mobile; h1 32/38; h2 24/30; h3 19/26; body 16/24; support 14/20; label 12/16. Keep body text at 16px on mobile and use tabular numerals for prices, timers and order IDs. Link fonts in templates with `preconnect`, `display=swap`, and matching CSP allowlist; no CSS framework or icon CDN.

Components: primary terracotta solid button, secondary quiet surface button, and text button; all at least 44px high with visible keyboard focus and disabled/loading states. Inputs have persistent labels, 48px height and inline validation. Chips are selectable controls only when interactive; selected and focus states cannot rely on color alone. Food cards show image, name, one-line description, price and one clear action. On mobile, item detail and checkout are bottom sheets using native `<dialog>` with focus restoration, Escape, backdrop dismissal and scroll containment; on desktop they become centered dialogs or a side cart. Toasts announce noncritical actions in a polite live region; errors remain visible near the affected control. Empty states include a specific next action; loading uses stable skeletons; recoverable errors include Retry. Respect `prefers-reduced-motion`; 150-250ms transitions only where state changes. Maintain WCAG AA text contrast, semantic landmarks and touch targets.

## Information architecture and flows

| Step | Content and primary action | Secondary UI / transitions |
| --- | --- | --- |
| QR `/qr/<table>` | Redirect to `/menu?table=...`; show venue, table chip, food and Browse menu. | Preserve table through swipe, matches, checkout and order-more links. If no table QR, allow manual table entry at checkout. |
| Welcome `/` | Food-led entrance with "Find your next favourite dish" and two actions: Browse menu / Find my match. | Optional 3-step help sheet; no required tutorial. Marketing lives at `/landingpage`. |
| Swipe `/food-swipe` | One generous dish photo, name, short description, progress and Like / Skip / Undo. | Drag physics mirror buttons; visible Browse menu escape and cart badge. Loading/error/finished states are explicit. |
| Matches `/meal-of-the-day` | "Your taste" summary, ranked real menu dishes, reasons derived from existing recommendation data, View dish / Add. | Item detail sheet for quantity, notes, allergens and pairings. Let guests return to menu at any time. Avoid implying a model explanation that is not present in the API. |
| Menu `/menu` | Food and category chips in first viewport; search, filter button, table chip, cart badge. | Diet/allergen controls in filter sheet; optional AI prompt behind "Help me choose" sheet. Per-item quantity/notes in detail sheet. Order history and table bill in a compact secondary section. |
| Cart and checkout | Sticky cart opens review sheet; line items editable, subtotal/fees/total shown. Primary: Place order. | Checkout section contains table, optional name/phone, order note and payment wording. Keep existing `/orders` payload and show server validation in sheet. On success go to existing confirmation route. |
| Confirmation `/order-confirmation/<token>` | Order number, accepted state, table, ETA, concise item summary. Primary: Track order. | Receipt and Order more, keeping table context. Do not claim payment is complete when `paymentStatus` is unpaid. |
| Tracking `/order/<token>` | Live Received -> Preparing -> Ready/Completed timeline, ETA, payment state and item summary. | SSE first, 30-second fallback polling and explicit reconnecting state; cancelled state gets its own explanation. Receipt link. |
| Receipt `/receipt/<token>` | Printable itemised bill, venue details, server totals, payment status. Primary: Print / Save PDF via browser. | Tracking link; hide controls in print. No claim of paid receipt when unpaid. |
| Staff login `/admin/login` | Branded login with clear destination, validation and safe return URL. Primary: Sign in. | Unauthenticated HTML `/kitchen` and `/admin` redirect here with `next`; JSON APIs retain 401 JSON. |
| Kitchen `/kitchen` | New, Preparing, Ready/Completed columns with table and elapsed time dominant; one next-status action per ticket. | Status history in tabs/archive; ETA in ticket detail or inline compact control; cancel requires confirmation. Sound toggle defaults off until user interaction. |
| Admin `/admin` | Overview with active orders, quick link to kitchen, menu and operations navigation. | Preserve settings, exports, monitoring, inventory and analytics in grouped sections or tabs without changing API contracts. |

## Functional upgrade backlog

| Priority | Work and acceptance behavior | Files |
| --- | --- | --- |
| P0 | Replace required tutorial with product entrance; unify wordmark and shared tokens/fonts; make landing first viewport show product promise and real workflow. | `templates/welcome.html`, `landingpage.html`, `index.html`, `meal_of_the_day.html`, `static/styles.css`, local SVG asset; possibly shared Jinja partials |
| P0 | Move menu form wall into filter/help/detail/checkout sheets, keep food visible at 390px, preserve QR table and existing cart/order contracts. Fix false Popular category (use a truthful label or real order counts), stock accumulation, safe status text, error/empty states, configurable currency display. | `templates/menu.html`, `static/styles.css`, `server.py` only if view data is needed, `tests/test_app.py` |
| P0 | Make checkout honest and resilient: table preserved, optional contact labels, authoritative result, field errors inside sheet, duplicate-submit guard, clear cart only after success. | `templates/menu.html`, `server.py`, `tests/test_app.py` |
| P0 | Fix HTML auth redirect for `/kitchen`; keep `/admin/*` JSON endpoint 401 contract, SSE behavior, CSRF and safe `next`. Add regression tests. | `server.py`, `tests/test_app.py` |
| P0 | Redesign confirmation, tracking, receipt and 404/500 with the shared system; update *all* tracking fields on SSE/poll, show cancelled/reconnecting states, use configured currency. | `templates/order_confirmation.html`, `order_tracking.html`, `receipt.html`, `error.html`, `static/styles.css`, `tests/test_app.py` |
| P1 | Refine swipe drag threshold, button parity, scoped keyboard input, undo/progress, reduced-motion and retry/empty/image fallback. Keep `/handle_swipe`, `/go_back` and progress JSON unchanged. | `templates/index.html`, `static/script.js`, `static/styles.css`, `tests/test_app.py` |
| P1 | Turn existing match results into a concise taste summary and explainable food choices; use existing `rankedRecommendations()` reasons and add no new AI promise. Keep add-to-cart handoff. | `templates/meal_of_the_day.html`, `backend.py` only if a view helper is needed, `tests/test_app.py` |
| P1 | Kitchen board with clear columns, large status targets, opt-in sound, reconnect/error feedback and mutation error handling. Admin overview and login grouping without removing tools. | `templates/kitchen.html`, `admin.html`, `admin_login.html`, `static/styles.css`, `tests/test_app.py` |
| P2 | Polish table bill, order history and AI helper discoverability; add focused browser smoke checks if tooling is available, with no runtime build step. | `templates/menu.html`, `templates/admin.html`, `tests/` |

No new database table is required for P0/P1. If a later change truly needs persisted data, increment `backend.py`'s existing schema version and use additive `create_schema()` / `ensure_column()` changes that run on SQLite and Postgres; never reset or reseed live data. No real online payment, account system, add-ons without existing menu data, or new staff roles in this stage.

## Stage 2 implementation order

1. Record route/API response baselines and run `python -m unittest discover -v`; inspect menu images and current production-compatible fields without modifying data.
2. Add shared design tokens, typography, local wordmark asset and reusable template structure; update CSP only enough for Google Fonts.
3. Rebuild `/`, `/landingpage` and `/food-swipe` layout; keep direct links and swipe API, then add accessible loading, error and reduced-motion states.
4. Reorganise `/menu` around food, filter sheet, item detail and cart/checkout sheet; preserve QR table, localStorage cart and POST payload. Fix Popular, stock, text injection and currency issues.
5. Rework matched-meal presentation and its cart handoff using existing recommendation data.
6. Rebuild confirmation, tracking, receipt and error pages; preserve token URLs and SSE/poll fallback, update full order state and print layout.
7. Fix `/kitchen` HTML auth routing and reshape kitchen/admin/login layouts; preserve staff JSON, CSRF and status mutations.
8. Add focused regression tests for new behavior, then run the full suite and manually review every route before any release decision.

## Verification checklist

- `python -m unittest discover -v` passes; add tests for unauthenticated `/kitchen` HTML redirect, API 401 JSON, safe `next`, QR table propagation, checkout errors, cancelled tracking, configured currency, and 404/500 content where behavior changes.
- At 390px: first menu viewport includes real food; no horizontal overflow; 44px controls; safe-area cart bar; sheets fit the viewport and restore focus; keyboard and screen-reader labels work; swipe button/drag/undo agree; checkout survives bad network or sold-out responses.
- At 1440px and 1024px: landing hero has visible promise and product imagery; kitchen columns show readable tickets and transitions; admin tools remain reachable; login redirects to intended staff page.
- Exercise `/`, `/landingpage`, `/food-swipe`, `/meal-of-the-day`, `/menu`, `/qr/<table>`, confirmation, tracking, receipt, `/admin/login`, `/admin`, `/kitchen`, missing route and invalid order token. Check SSE update and fallback refresh; print receipt; test reduced motion and image failure.
- Check existing JSON API shapes, `/admin/events` and `/orders/<token>/events`, CSRF, auth, rate limits, security headers, CSP font loading, and both SQLite/Postgres migration compatibility. Do not reset production data.
- Keep Flask/Jinja/vanilla JS with no npm/build step or CSS framework CDN. Do not edit secrets, `.env*`, `Dockerfile` (`--preload` is required), or `ml_food_model.json`. Write every file as UTF-8; use HTML entities for punctuation in templates and `\u` escapes in JS strings when needed. Verify with a UTF-8 decode and a scan for replacement characters, mojibake and literal `?` substitutions.
