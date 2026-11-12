# no-ryanair-app: technical writeup

Two phases, tagged per claim:
- `[STATIC]`: read from `apk/ryanair-3.243.0.apk` (v3.243.0) via JADX, no network involved.
- `[LIVE]`: reproduced against the real API from a real account. See `tools/client.py`.

## 1. It's an infrastructure split, not a client-side toggle `[STATIC]`

`ApiBuildConfiguration` (the class that hands every Retrofit client its base URL) exposes a
distinct boarding-pass backend **separate from the rest of the app's own API**, which is itself
already walled off from the public website:

```
b()  -> https://nativeapps.ryanair.com/api/            (general app API)
v()  -> https://nativeapps.ryanair.com/checkin-service/ (check-in)
c()  -> https://nativeapps.ryanair.com/kiosk-api/       (airport kiosk)
x()  -> https://mntappbp.ryanair.com/                   (boarding pass - "m[obile] nt[ive] app bp")
y()  -> https://mgpbp.ryanair.com/                       (Google Wallet bp)
e()  -> https://mswbp.ryanair.com/                       (Samsung Wallet bp)
B()  -> https://mhwbp.ryanair.com/                       (Huawei Wallet bp)
```

Boarding-pass issuance lives on its own dedicated subdomain family (`*bp.ryanair.com`), provisioned
under the "nativeapps" infrastructure, not under whatever `www.ryanair.com` calls for web check-in.
There is no `if (isWebClient) hide` flag to flip. The public website was never built against
this backend. The APK shows the mechanism (separate Retrofit base URL); the app-only requirement
is policy and routing, not a missing client check.

## 2. The actual REST surface (`BoardingPassService`, `v1/*`) `[STATIC]`

```
POST v1/boardingpass           getBoardingPasses(flight request)
POST v1/boardingpasses         getBoardingPasses(bookings request)
POST v1/boardingpasses/group   getBoardingPassesGroup
POST v1/boardingpass/refresh   refreshBoardingPass
POST v1/boardingpass/recheck   recheckBoardingPass
POST v1/boardingpass/state     getBoardingPassState
```

All calls go through the app's normal session auth (same login as the rest of the app). No
special device-bound credential is visible in the Retrofit/DI wiring for this specific host beyond
what every other `nativeapps.ryanair.com` call uses.

**Resolved live** `[LIVE]`: no Play Integrity / app-attestation check actually gates this endpoint.
`tools/client.py` sends a fabricated `X-DEVICE-FINGERPRINT` (random SHA1 hex, never seen by any real
device) from plain Python with no attestation token of any kind, and gets a 200 with real boarding-pass
data back. Whatever `DynamicIntegrity`/`PlayIntegrity` classes exist in the APK, this endpoint doesn't
call them. The static-only open item below is now closed.

## 3. The app-install funnel (`DispatcherActivity`) `[STATIC]`

`AndroidManifest.xml` shows `DispatcherActivity` as a verified Android App Link
(`android:autoVerify="true"`) for:

```
https://www.ryanair.com/<lang>/<country>/app/*
https://www.ryanair.com/<lang>/<country>/lp/app/*
https://app.ryanair.com/store/android      (-> Play Store)
```

Any `.../app/...` or `.../lp/app/...` link on ryanair.com is designed to be hijacked into the app
when installed (Android App Links), and to fall through to a "download the app" landing page (`lp`
= landing page) in a plain browser otherwise. This is the standard deferred-deep-link install
funnel, generic, not boarding-pass-specific.

## 4. `BoardingPassDeepLinkActivity`, in a package literally called `.deeplink.gate` `[STATIC]`

`com.ryanair.cheapflights.ui.deeplink.gate.BoardingPassDeepLinkActivity` takes a PNR from an
internal deep-link payload, looks up boarding passes for it via
`GetBoardingPassesForFlightUseCaseImpl`, and routes to one of `HOME` / `BOARDING_PASS` /
`BOARDING_PASS_LIST`. It has no manifest intent-filter of its own. It's reached only through
`DispatcherActivity`'s internal routing, i.e. it's the in-app landing point for whatever
"view your boarding pass" link Ryanair emails/pushes you, confirming that link is meaningless
without the app (no server-rendered PDF fallback exists on that URL).

## 5. The two *legitimate* app-free channels Ryanair itself built `[STATIC]`

### a. Airport self-service kiosk: `KioskBoardingPassService`
```
POST /v1/boardingpasses/print   (host: nativeapps.ryanair.com/kiosk-api/)
```
Real, first-party, no app needed: the airport kiosk hardware calls this to print a physical
boarding pass. Fees and availability vary by airport/base (some bases removed free kiosk printing;
some charge an airport check-in fee if you didn't web-check-in first). Business/contract matter
per airport, not something visible in the Android app.

### b. Google/Samsung/Huawei (and historically Apple) Wallet: `BoardingPassWalletService`
```
PUT <dynamic wallet url>   getBoardingPassWalletToken(...)  -> BoardingPassWalletTokenDto
```
Standard "Save to Google Wallet" JWT flow. Practical consequence: **you only need the app once**,
to tap "Add to Wallet". After that the pass lives in the OS's own Wallet app, which receives
server-pushed updates (gate/seat changes) independently of the Ryanair app. Uninstall afterward
and the wallet pass still scans at security. Most practical app-free outcome: install the app
once, add the pass to your phone's wallet, then delete the app.

## Open items
- Per-airport kiosk fee/availability matrix (commercial; not in the APK).
- iOS / Apple Wallet for Ryanair boarding passes (this write-up is Android `ryanair-3.243.0.apk` only).
- Which 2D symbology the Android UI picks for BCBP display (API payload verified; renderer not grepped in APK here).

## Practical takeaway (app-free paths)

Primary path for this repo: web check-in, then `tools/client.py` or the `extension/` on a Manage
Trip page to pull the BCBP and render a PNG: same data the app would show, no install.

Ryanair-built alternatives without keeping the app:

1. Add to Google/Samsung Wallet once from the app, then uninstall; wallet passes get server updates. `[STATIC]`
2. Airport kiosk print via `KioskBoardingPassService` where the base allows it (fees vary). `[STATIC]`
3. Counter/desk fallback per Ryanair's own check-in help (e.g. dead phone after online check-in).

## 6. Auth mechanics (for the client script in `tools/`) `[STATIC + LIVE]`

`MyRyanairAuthInterceptor` (com.ryanair.cheapflights.user.networking) is the real interceptor on
every `nativeapps.ryanair.com`-family request, including boarding pass:
- Header is `X-AUTH-TOKEN: <token>`, **not** `Authorization: Bearer`.
- On a 401 it transparently refreshes via `LoginUsingRefreshMyRyanairToken` and retries once.
- The server can rotate the token on any response (`X-AUTH-TOKEN` response header). The app
  persists whatever comes back via `SessionController.h(token)`.

`res/xml/network_security_config.xml` sets no certificate pinning for any Ryanair host (the only
pinned traffic belongs to a third-party in-flight-connectivity SDK, `com.airware.*`, unrelated to
login/boarding pass). A user-installed MITM proxy (mitmproxy/HTTP Toolkit with its root CA added
as a user CA) can observe the app's own traffic, including the real `X-AUTH-TOKEN` the app
received at login. Capturing your own session's header this way reads your own device's own
traffic; nothing server-side is broken to do it.

### Request shapes: confirmed live, not just from the DTOs
```
POST https://mntappbp.ryanair.com/v1/boardingpass
Headers: X-AUTH-TOKEN: <token>
         client: android
         client-os: <android sdk int, e.g. 34>
         client-version: 3.243.0
         client-carrier-code: FR
         X-DEVICE-FINGERPRINT: <any SHA1 hex, not validated, see §2>
Body:   {"RecordLocator": "<PNR>", "Email": "<account email>"}
->      [BoardingPassDto, ...]   (see tools/client.py)

POST https://mntappbp.ryanair.com/v1/boardingpasses
Headers: (same as above)
Body:   {"CustomerId": "<myRyanair customer id>", "BookingIds": [<bookingId as INTEGER>]}
->      [BoardingPassDto, ...]
```

Field names are PascalCase (kotlinx.serialization descriptors), not camelCase.
`BookingIds` must be JSON integers. Sending them as strings returns 403, not 400, so this
one's easy to misdiagnose as an auth failure (confirmed live).

## 7. The barcode itself: IATA BCBP, decoded field-by-field `[LIVE]`

`BoardingPassDto.barcode` isn't Ryanair's own format. It's IATA Resolution 792 BCBP, the same
string every airline's boarding pass encodes, mobile or paper. For a visual, interactive feel of
the format, [shooshx/BoardingBarcode](https://shooshx.github.io/BoardingBarcode/) builds one from
scratch in the browser and renders it as PDF417 or Aztec. The table below isn't guessed from the
spec, it's the real string I pulled from the live API, sliced by byte offset and
cross-checked against the known flight it belongs to:

```
M1DOE/JOHN             XYZ123 STNDUBFR 1234 001Y001A0001 149>5181W 6305BFR 0000000000000000000000000000 0                          NN
```

| Bytes | Field | Value | Meaning |
|---|---|---|---|
| 0:1 | Format code | `M` | always `M` for BCBP |
| 1:2 | Legs encoded | `1` | one flight segment in this pass |
| 2:22 | Name | `DOE/JOHN` | `LAST/FIRST`, space-padded to 20 |
| 22:23 | Electronic ticket indicator | `' '` | blank; Ryanair doesn't set `E` here |
| 23:30 | PNR | `XYZ123 ` | 6-char PNR, padded to 7 |
| 30:33 | Origin | `STN` | London Stansted |
| 33:36 | Destination | `DUB` | Dublin |
| 36:39 | Operating carrier | `FR ` | Ryanair, padded to 3 |
| 39:44 | Flight number | `1234 ` | padded to 5 |
| 44:47 | Julian date | `001` | day 1 of the year |
| 47:48 | Compartment | `Y` | economy |
| 48:52 | Seat | `001A` | matches the `BoardingPassDto.seat.designator` field |
| 52:57 | Sequence number | `0001 ` | matches `BoardingPassDto.sequence` |
| 57:58 | Passenger status | `1` | checked in |
| 58:60 | Conditional-data length | `49` (hex) | `0x49` = 73 bytes follow |

Past byte 60 is the conditional/security block: a version marker (`>`), per-leg conditional
fields (ticket/document data, frequent-flyer fields), an airline-use zone, and in newer BCBPs a
digital-signature field. Those sub-offsets vary more by airline implementation; I only
byte-verified the mandatory block above.

The string above is a fabricated example. The layout is what I verified against a real pass.

**Two independent checks that the slicing is right, not approximately right:**
- The Julian date field decodes to a calendar day that matches the flight's departure date
  returned elsewhere in the same API response (`departure.date`).
- The conditional-data-length field says `0x49` (73) bytes follow. The string's actual length
  past that point is exactly 73 characters. If the offsets were wrong by even one byte, this
  wouldn't line up.

`tools/bp_render.py` renders this string as Aztec (common for mobile BCBP). BCBP field
contents are verified live; symbology in Ryanair's own UI is listed under Open items above.
