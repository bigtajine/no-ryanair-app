# no-ryanair-app

Ryanair stopped issuing boarding passes outside its own app in November 2025. I wanted to know whether that was actually enforced by the system that generates the pass, or whether it was just a rule the app's interface imposes on top of a server that doesn't care. It's the second one. The boarding pass is ordinary data sitting behind an API call, and that call works fine from a browser session, a Python script, or a Chrome extension with no Ryanair app installed anywhere in the chain.

This repository documents how I reached that conclusion and ships the tools that prove it: a Chrome extension that turns a logged-in Manage Trip page into a one-click PNG of your boarding pass, and a Python client that does the same from the command line. Both use your own account and your own session. Neither bypasses a login, a password, or anything Ryanair would call a security control.

## What I actually got, and what it was supposed to mean

I'd checked in online. Account logged in, phone charged, nothing wrong on my end. At the gate the app wouldn't load over bad airport wifi, and this is what Ryanair's own screen tells you in that situation:

> **You need the Ryanair App to access your digital boarding pass.** You must download the Ryanair App. This is the only way to access your digital boarding pass, paper boarding passes are no longer issued or accepted.

That statement isn't true. Ryanair's own policy gives a passenger whose phone dies after online check-in a free paper pass at the counter. The screen is stricter than the actual rule, which told me the boarding pass clearly exists as retrievable data before the app ever renders it. I went looking for where that data lives and what, if anything, actually gates access to it.

## Michael O'Leary's idea

The app-only rule is one man's fixation. Ryanair's CEO Michael O'Leary announced in October 2024 that paper boarding passes were finished, floated the deadline, let it slip twice, and finally pushed the airline fully digital on 12 November 2025. He has spent years telling anyone who'll listen that the app is the future and the printout is dead weight, and he built the policy to match: skip online check-in and it's £30 to £55 at the counter, though a dead phone after online check-in still gets a free paper replacement. The stated reasons are a tidy mix of anti-fraud, smoother rebooking during disruptions, and, in his own framing, lower airport costs and cheaper fares.

Not everyone bought it. Two days after the rule went live, Portugal's civil aviation regulator told Ryanair it couldn't fine a passenger who checked in online but didn't have the app. The EU passed a law in July 2026 that will ban this kind of app requirement outright, but it doesn't take effect until October 2027 and won't apply to flights leaving the UK at all. Until then, whether you need the app is a decision Ryanair enforces through its own interface, not through anything written into the boarding-pass service itself.

## What's technically going on

Ryanair's backend is split across subdomains. The general app API, check-in, the kiosk service, and boarding-pass issuance all live on different hosts, separate from `www.ryanair.com`, the site people actually check in on:

```
www.ryanair.com (web check-in)  ──╳── never wired to ──╳──  mntappbp.ryanair.com (boarding pass)
        │                                                              ▲
        └── nativeapps.ryanair.com (general app API) ─────────────────┘
                 same login, same X-AUTH-TOKEN, different host
```

`ApiBuildConfiguration`, the class that hands every API client its base URL, confirms it: boarding-pass issuance is wired to `mntappbp.ryanair.com`, and the website's code never calls it. There's no flag that says "deny web clients." Nobody had to write one, because the website was never connected to this part of the backend in the first place. I confirmed it by calling the app's own endpoint directly, using an ordinary web-login token obtained the way any browser gets one. It worked without modification.

The same `X-AUTH-TOKEN` the app uses works from outside the app, and the endpoint doesn't check for anything beyond that header. I sent a device fingerprint made of random bytes, with no attestation token of any kind, and the server returned a complete boarding pass anyway. Whatever app-integrity checks exist elsewhere in Ryanair's code, this endpoint doesn't call them.

One detail cost real debugging time: the `BookingIds` field must be a JSON integer, not a string. Sent as a string it returns a 403 that looks exactly like an auth failure and isn't one.

## What the barcode actually contains

The PNG these tools produce isn't a Ryanair invention. It encodes IATA Resolution 792, the boarding-pass barcode standard every airline uses. I took a real string from a live response and sliced it byte by byte rather than trusting the spec. The example below is fabricated; the layout is what I verified against a real pass:

```
M1DOE/JOHN             XYZ123 STNDUBFR 1234 001Y001A0001 149>5181W 6305BFR 0000000000000000000000000000 0                          NN
```

| Bytes | Field | Value | Meaning |
|---|---|---|---|
| 0:1 | Format code | `M` | always `M` for this standard |
| 1:2 | Legs encoded | `1` | one flight segment |
| 2:22 | Name | `DOE/JOHN` | `LAST/FIRST`, padded to 20 |
| 23:30 | Booking reference | `XYZ123 ` | the PNR, padded to 7 |
| 30:33 | Origin | `STN` | London Stansted |
| 33:36 | Destination | `DUB` | Dublin |
| 36:39 | Operating carrier | `FR ` | Ryanair |
| 39:44 | Flight number | `1234 ` | |
| 44:47 | Julian date | `001` | day 1 of the year |
| 47:48 | Compartment | `Y` | economy |
| 48:52 | Seat | `001A` | |
| 52:57 | Sequence number | `0001 ` | boarding order |
| 57:58 | Passenger status | `1` | checked in |

Two internal checks confirm the offsets are exact, not approximate. The Julian date decodes to a calendar day that matches the flight's departure date elsewhere in the same response, and a declared length field says how many bytes of conditional data follow, which the string then matches to the character. Miss by one byte and neither lines up. The full breakdown is in [`docs/technical-writeup.md`](docs/technical-writeup.md), and [shooshx/BoardingBarcode](https://shooshx.github.io/BoardingBarcode/) builds one in the browser if you want a feel for the format.

## Using this

The Chrome extension is the easiest path. Open `chrome://extensions`, turn on Developer mode, click **Load unpacked**, and select the `extension/` folder. Log in to [ryanair.com](https://www.ryanair.com), open **Manage Trip** for a booking you've checked in for, and click the toolbar icon once. It reads your session, refreshes a token the way the site does, and saves a scannable PNG. Details in [`extension/README.md`](extension/README.md).

For scripting, `tools/client.py` does the same from the command line:

```bash
pip install playwright && playwright install chromium
python tools/client.py --cookie-file cookie.txt --customer-id <id> --pnr ABC123 --email you@example.com --png
```

The session cookie expires quickly. On a 401, recapture it from DevTools, under the Network tab, on any request to `ryanair.com`.

## Why Ryanair would actually do this

My read, not something the code confirms. O'Leary's stated reasons, anti-fraud and rebooking and lower cost, are plausible and don't require banning the pass outside the app. Web check-in already produces the data; Ryanair chose not to render it anywhere else. A hard rule enforced entirely by the app's screen is the cheapest kind to build, because the server needs no changes. It also forces an install right before a flight, where the app sells seats, bags and priority far better than a browser tab you close after one visit, and where every download is one less paper pass to print. The restriction was never backed by anything the server checks. That's exactly why these tools work.

## Scope and limits

This answers one question: is the app-only requirement a technical gate, or just where Ryanair chose to put the door. It's the door. It does not audit what the app collects or tracks, and makes no claim about that. Whether using these tools breaks Ryanair's terms is yours to weigh. Cookies expire fast and Ryanair can rewire any of this at any time; everything here reflects the API as it behaved in late 2026, against `apk/ryanair-3.243.0.apk`.

Static analysis was done with [JADX](https://github.com/skylot/jadx) against `apk/ryanair-3.243.0.apk` (`com.ryanair.cheapflights`, 3.243.0). Every live claim was fired at the real API against a real booking before I wrote it down.
