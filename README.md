# no-ryanair-app

Fetch the boarding pass Ryanair says only exists inside its app. It is an ordinary API response behind your ordinary login, and you can pull it with no app installed.

> ⚠️ Honest disclaimer up front: this tool does not bypass Ryanair's login, does not work without a booking you have already checked in for, and does not audit what the Ryanair app collects or tracks. It reads your own pass with your own session. The app-only rule lives in the app's interface; I could not find anything on the server that enforces it. Ryanair can change that whenever it likes, and using this may sit badly with its terms. That part is yours to weigh.

Every finding here was reproduced against the real API with a real booking before it was written down. See [`docs/technical-writeup.md`](docs/technical-writeup.md) for the evidence, tagged by confidence level, and [How this was built](#how-this-was-built) for what that verification actually involved.

## The story

In October 2024 Ryanair's CEO Michael O'Leary announced that paper boarding passes were finished. The deadline slipped twice, and on 12 November 2025 Ryanair went fully digital. Skip online check-in and the airport counter charges £30 to £55. Check in online and your phone dies, and the counter prints a pass for free. O'Leary's stated reasons are anti-fraud, smoother rebooking in a disruption, and lower airport costs.

Two days after the rule went live, Portugal's civil aviation regulator told Ryanair it could not fine a passenger who had checked in online but had no app. The EU passed a law in July 2026 that bans this kind of requirement, effective October 2027, and it does not cover flights leaving the UK. Until then, Ryanair enforces the rule through its own app.

I checked in online, my phone was charged, and the app would not load over the airport wifi. This is what Ryanair's own screen told me:

> **You need the Ryanair App to access your digital boarding pass.** You must download the Ryanair App. This is the only way to access your digital boarding pass, paper boarding passes are no longer issued or accepted.

It is not the only way, and Ryanair's own free paper pass at the counter proves it. So I took the app apart to find out what actually guards the pass. Nothing on the server does. This repo shows that and ships the tools.

## What the boarding pass really is

The pass is an IATA Resolution 792 BCBP string, the same format every airline prints. Ryanair serves it from a dedicated host (`mntappbp.ryanair.com`) that the public website is never wired to, and the app draws it as an Aztec code.

```
Manage Trip page ── your cookie ──►  /api/usrprof/v2/accounts/{id}/sessionToken  ──►  X-AUTH-TOKEN
Manage Trip page ── same session ─►  /api/orders/v2/orders/{id}/trips/{trip}      ──►  bookingId
mntappbp.ryanair.com  ◄── POST /v1/boardingpasses {CustomerId, BookingIds:[int]} ──  BCBP string  ──►  Aztec PNG
```

The fields sit at fixed byte offsets. I sliced a real string by hand to confirm the layout; this example is fabricated:

```
M1DOE/JOHN             XYZ123 STNDUBFR 1234 001Y001A0001 149>5181W 6305BFR 0000000000000000000000000000 0                          NN
```

Name is bytes 2 to 22, the booking reference 23 to 30, origin and destination 30 to 36, flight number 39 to 44, Julian date 44 to 47, seat 48 to 52. The Julian date decodes to the flight's real departure date, and a declared length field matches the conditional data to the character, so an offset wrong by one byte would break both. Full table in the write-up.

## Quick start

Chrome extension, the easy path. Open `chrome://extensions`, turn on Developer mode, click **Load unpacked**, pick the `extension/` folder.

```
1. Log in to https://www.ryanair.com
2. Open Manage Trip on a booking you have already checked in for
3. Click the toolbar icon once
   -> a scannable PNG named PNR_DEPARR_DATE.png downloads
```

Python, for scripting:

```bash
pip install playwright && playwright install chromium
python tools/client.py --cookie-file cookie.txt --customer-id <id> --pnr ABC123 --email you@example.com --png
```

The session cookie expires fast. On a 401, recapture it from DevTools, Network tab, any request to `ryanair.com`. Never commit it; the `.gitignore` already excludes it.

## What each part does

| Path | Purpose | Calls Ryanair? |
|---|---|---|
| `extension/` | One click on a Manage Trip page produces the boarding-pass PNG | Yes, with your session |
| `tools/client.py` | Same flow from the command line, prints JSON or saves a PNG | Yes, with your cookie or token |
| `tools/bp_render.py` | Renders a barcode string as an Aztec PNG | No |
| `docs/technical-writeup.md` | The decompile evidence, request shapes, byte-level barcode breakdown | None |
| `apk/ryanair-3.243.0.apk` | The exact build I decompiled | None |

## What I proved (and what doesn't work)

- The pass is plain data behind an API call. A web-login token fetches it from `mntappbp.ryanair.com` with no app involved. `[LIVE]`
- The website was never wired to that host. `ApiBuildConfiguration` gives boarding passes their own subdomain and the site never calls it. There is no "deny web clients" check to find, because nobody wrote one. `[STATIC]`
- Device attestation is not checked on this endpoint. A fingerprint made of random bytes and no integrity token still returns a valid pass. `[LIVE]`
- The barcode is standard IATA BCBP. I verified the field offsets against a real string with two independent checks. `[LIVE]`
- `BookingIds` must be a JSON integer. Send a string and you get a 403 that looks exactly like an auth failure and is not one. `[LIVE]`
- The `ryanair:jwt` value in `sessionStorage` is a different token from the `X-AUTH-TOKEN`. The real one comes from the `sessionToken` endpoint. `[LIVE]`
- I only tested checked-in bookings, on the Android API shape, on my own account. iOS and other airlines' apps are untested.
- Ryanair already knows every pass it issued, and this does not change what it holds.

## Trade-offs

The requests present themselves as the Android app 3.243.0 (`client: android`, a random device fingerprint), because that is the shape the endpoint expects. They still use your own login, but the imitation is the part Ryanair is most likely to dislike. The extension runs unpacked in developer mode, and the Python path needs your session cookie on disk, so treat both with the care you would give a password. If Ryanair rewires the website to that host or starts checking attestation, this stops working.

## Docs

- [`docs/technical-writeup.md`](docs/technical-writeup.md): the full chain, host split, request shapes, auth mechanics and byte-level barcode breakdown, every claim tagged `[STATIC]`, `[LIVE]` or `[STATIC + LIVE]`.
- [`extension/README.md`](extension/README.md): load and use the extension.

## How this was built

Static analysis was done with [JADX](https://github.com/skylot/jadx) against `apk/ryanair-3.243.0.apk` (`com.ryanair.cheapflights`, version 3.243.0): the base-URL config, the Retrofit services, the auth interceptor and the manifest.

- The decompile told me where to look and what the endpoints expected. It could not tell me what the server actually checks.
- I ran every test myself, against my own booking. Every live claim above was fired at the real API from my own account before I wrote it down.
- Several of my first guesses were wrong until tested. I assumed the `sessionStorage` JWT was the auth token (it is not). I sent `BookingIds` as strings (403). I called the boarding-pass host from the extension's page script and hit a CORS failure, which is why that one request now goes through the background worker.
- What I did not test, I do not claim. The write-up says which build and which path each finding comes from, and a claim with no tag is weaker.

If a claim here does not hold on your account, open an issue with the app version and what you saw.

## Credits

- Static analysis: [JADX](https://github.com/skylot/jadx).
- Barcode layout reference: [shooshx/BoardingBarcode](https://shooshx.github.io/BoardingBarcode/).
- Barcode rendering: [bwip-js](https://github.com/metafloor/bwip-js).
- Policy timeline: [Pixidia's Ryanair digital boarding pass guide](https://pixidia.com/en/ryanair-digital-boarding-pass-guide-2026/).

## License

MIT. Privacy-oriented tooling for your own bookings. Use it on accounts you own.
