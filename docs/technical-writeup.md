# no-ryanair-app: technical writeup

Claim tags:

- `[STATIC]`: from `apk/ryanair-3.243.0.apk` (v3.243.0), decompiled with JADX.
- `[LIVE]`: reproduced against the real API on a real account. See `tools/client.py`.

## 1. Boarding passes have their own backend `[STATIC]`

`ApiBuildConfiguration` supplies every Retrofit client's base URL. Boarding passes get their own host, separate from the general app API and from the public website:

```
b()  -> https://nativeapps.ryanair.com/api/            (general app API)
v()  -> https://nativeapps.ryanair.com/checkin-service/ (check-in)
c()  -> https://nativeapps.ryanair.com/kiosk-api/       (airport kiosk)
x()  -> https://mntappbp.ryanair.com/                   (boarding pass)
y()  -> https://mgpbp.ryanair.com/                       (Google Wallet bp)
e()  -> https://mswbp.ryanair.com/                       (Samsung Wallet bp)
B()  -> https://mhwbp.ryanair.com/                       (Huawei Wallet bp)
```

Issuance is on `*bp.ryanair.com`. `www.ryanair.com` never calls it, and the APK has no `isWebClient`-style gate on it.

## 2. REST surface (`BoardingPassService`, `v1/*`) `[STATIC]`

```
POST v1/boardingpass           getBoardingPasses(flight request)
POST v1/boardingpasses         getBoardingPasses(bookings request)
POST v1/boardingpasses/group   getBoardingPassesGroup
POST v1/boardingpass/refresh   refreshBoardingPass
POST v1/boardingpass/recheck   recheckBoardingPass
POST v1/boardingpass/state     getBoardingPassState
```

Auth is the normal app session. No device-bound credential beyond what other `nativeapps.ryanair.com` calls use.

`[LIVE]` No Play Integrity or attestation check gates the endpoint, despite `DynamicIntegrity` / `PlayIntegrity` classes existing elsewhere in the APK. `tools/client.py` sends a fabricated `X-DEVICE-FINGERPRINT` (random SHA1, no attestation token) and gets a 200 with real pass data.

## 3. App-install funnel (`DispatcherActivity`) `[STATIC]`

`AndroidManifest.xml` registers `DispatcherActivity` as a verified App Link (`android:autoVerify="true"`):

```
https://www.ryanair.com/<lang>/<country>/app/*
https://www.ryanair.com/<lang>/<country>/lp/app/*
https://app.ryanair.com/store/android      (-> Play Store)
```

`.../app/...` links open the app if installed, otherwise a "download the app" page (`lp` = landing page). Generic funnel, not specific to boarding passes.

## 4. `BoardingPassDeepLinkActivity`, package `.deeplink.gate` `[STATIC]`

`com.ryanair.cheapflights.ui.deeplink.gate.BoardingPassDeepLinkActivity` takes a PNR from an internal deep-link payload, looks up passes via `GetBoardingPassesForFlightUseCaseImpl`, and routes to `HOME`, `BOARDING_PASS` or `BOARDING_PASS_LIST`. It has no manifest intent-filter and is reached only through `DispatcherActivity`. Presumably the target of the "view your boarding pass" links Ryanair emails and pushes.

## 5. App-free channels Ryanair provides `[STATIC]`

### a. Airport kiosk: `KioskBoardingPassService`

```
POST /v1/boardingpasses/print   (host: nativeapps.ryanair.com/kiosk-api/)
```

Kiosk hardware prints a physical pass through this endpoint. Fees and availability vary by airport and are commercial, not visible in the app.

### b. Google/Samsung/Huawei (and historically Apple) Wallet: `BoardingPassWalletService`

```
PUT <dynamic wallet url>   getBoardingPassWalletToken(...)  -> BoardingPassWalletTokenDto
```

Standard "Save to Google Wallet" JWT flow. The app is needed once, to add the pass. After that the pass lives in the Wallet app and receives server-pushed updates (gate, seat) independently.

## 6. Auth mechanics `[STATIC + LIVE]`

`MyRyanairAuthInterceptor` (com.ryanair.cheapflights.user.networking) runs on every `nativeapps.ryanair.com`-family request:

- Header: `X-AUTH-TOKEN: <token>` (not `Authorization: Bearer`).
- On 401, refreshes via `LoginUsingRefreshMyRyanairToken` and retries once.
- The server can rotate the token on any response (`X-AUTH-TOKEN` response header); the app persists it via `SessionController.h(token)`.

`res/xml/network_security_config.xml` pins no Ryanair host. The only pinned traffic belongs to a third-party in-flight SDK, `com.airware.*`.

### Request shapes, confirmed live

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

Field names are PascalCase (kotlinx.serialization). `BookingIds` must be JSON integers. Strings return 403, not 400, which reads like an auth failure. Confirmed live.

## 7. The barcode: IATA BCBP, field by field `[LIVE]`

`BoardingPassDto.barcode` is an IATA Resolution 792 BCBP string, the format every airline uses, mobile or paper. [shooshx/BoardingBarcode](https://shooshx.github.io/BoardingBarcode/) builds one in the browser. A real string was sliced by byte offset and cross-checked against its flight. The example below is fabricated, with the same layout:

```
M1DOE/JOHN             XYZ123 STNDUBFR 1234 001Y001A0001 149>5181W 6305BFR 0000000000000000000000000000 0                          NN
```

| Bytes | Field | Value | Meaning |
| --- | --- | --- | --- |
| 0:1 | Format code | `M` | always `M` for BCBP |
| 1:2 | Legs encoded | `1` | one flight segment |
| 2:22 | Name | `DOE/JOHN` | `LAST/FIRST`, space-padded to 20 |
| 22:23 | Electronic ticket indicator | `' '` | blank; Ryanair doesn't set `E` |
| 23:30 | PNR | `XYZ123 ` | 6-char PNR, padded to 7 |
| 30:33 | Origin | `STN` | London Stansted |
| 33:36 | Destination | `DUB` | Dublin |
| 36:39 | Operating carrier | `FR ` | Ryanair, padded to 3 |
| 39:44 | Flight number | `1234 ` | padded to 5 |
| 44:47 | Julian date | `001` | day 1 of the year |
| 47:48 | Compartment | `Y` | economy |
| 48:52 | Seat | `001A` | matches `BoardingPassDto.seat.designator` |
| 52:57 | Sequence number | `0001 ` | matches `BoardingPassDto.sequence` |
| 57:58 | Passenger status | `1` | checked in |
| 58:60 | Conditional-data length | `49` (hex) | `0x49` = 73 bytes follow |

Past byte 60 is the conditional/security block: a version marker (`>`), per-leg conditional fields, an airline-use zone, and in newer BCBPs a signature field. Sub-offsets vary by airline, so only the mandatory block above was byte-verified.

Two checks confirm the offsets:

- The Julian date decodes to a day matching the flight's departure date elsewhere in the response (`departure.date`).
- The conditional-data-length field says 73 bytes follow (`0x49`), and the remaining string is exactly 73 characters. One byte off would break this.

`tools/bp_render.py` renders the string as Aztec. Field contents are verified live; the symbology Ryanair's own UI uses is listed under Open items.
