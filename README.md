# no-ryanair-app

Ryanair's boarding pass is a plain API response behind your normal login, so you can fetch it without the app. There's a one-click Chrome extension and a Python client, and both use your own session.

The app says it's the only way to get the pass. It isn't. The pass comes from a dedicated host (`mntappbp.ryanair.com`) that the public website never calls, and nothing on the server enforces the app-only rule. That comes from decompiling `ryanair-3.243.0.apk` with JADX and confirming it live against a real booking.

## Findings

- A web-login token is enough to fetch the pass from `mntappbp.ryanair.com`.
- The site was never wired to that host. `ApiBuildConfiguration` gives boarding passes their own subdomain, and there's no "deny web clients" check.
- There's no device attestation. A random-byte fingerprint with no integrity token still returns a valid pass.
- `BookingIds` has to be a JSON integer. A string returns a 403 that looks exactly like an auth failure.
- The `ryanair:jwt` in `sessionStorage` isn't the `X-AUTH-TOKEN`. The real one comes from the `sessionToken` endpoint.
- The barcode is standard IATA BCBP (Res 792), and the offsets check out two ways.

Tested live on checked-in bookings, with one account, against the Android app's API. It may break Ryanair's terms, and they can change the API at any time. Full evidence is in [`docs/technical-writeup.md`](docs/technical-writeup.md).

## Request chain

```
Manage Trip ── cookie ──►  /api/usrprof/v2/accounts/{id}/sessionToken  ──►  X-AUTH-TOKEN
Manage Trip ── session ─►  /api/orders/v2/orders/{id}/trips/{trip}      ──►  bookingId
mntappbp.ryanair.com  ◄── POST /v1/boardingpasses {CustomerId, BookingIds:[int]} ──  BCBP  ──►  Aztec PNG
```

## Use

For the extension, open `chrome://extensions`, turn on Developer mode, click Load unpacked, and pick `extension/`. Log in to ryanair.com, open Manage Trip on a checked-in booking, and click the icon. The PNG downloads.

For Python:

​```bash
pip install playwright && playwright install chromium
python tools/client.py --cookie-file cookie.txt --customer-id <id> --pnr ABC123 --email you@example.com --png
​```

## Layout

| Path | What |
|---|---|
| `extension/` | one-click boarding-pass PNG from a Manage Trip page |
| `tools/client.py` | the same flow from the command line |
| `tools/bp_render.py` | turns a BCBP string into an Aztec PNG |
| `docs/technical-writeup.md` | decompile evidence, request shapes, barcode breakdown |
| `apk/ryanair-3.243.0.apk` | the build that was decompiled |

[JADX](https://github.com/skylot/jadx) · [bwip-js](https://github.com/metafloor/bwip-js) · barcode format from [shooshx/BoardingBarcode](https://shooshx.github.io/BoardingBarcode/) · policy timeline from [Pixidia](https://pixidia.com/en/ryanair-digital-boarding-pass-guide-2026/). MIT, for your own bookings.