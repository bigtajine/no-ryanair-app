# Findings: why Ryanair boarding passes are app-only

Source: static decompile (JADX) of `apk/ryanair-3.243.0.apk` (v3.243.0, com.ryanair.cheapflights).
No network traffic was captured; no server was queried; no auth was used. Everything below is
read directly from the app's own code/manifest.

## 1. It's an infrastructure split, not a client-side toggle

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
There is no `if (isWebClient) hide` flag to flip — the public website was simply never built against
this backend. This matches Ryanair's long-publicised (and controversial) policy of making boarding
passes an app-exclusive feature to cut printing costs and push app installs — the code confirms the
*mechanism*, the *policy* is Ryanair's own stated choice, not a bug or an oversight.

## 2. The actual REST surface (`BoardingPassService`, `v1/*`)

```
POST v1/boardingpass           getBoardingPasses(flight request)
POST v1/boardingpasses         getBoardingPasses(bookings request)
POST v1/boardingpasses/group   getBoardingPassesGroup
POST v1/boardingpass/refresh   refreshBoardingPass
POST v1/boardingpass/recheck   recheckBoardingPass
POST v1/boardingpass/state     getBoardingPassState
```

All calls go through the app's normal session auth (same login as the rest of the app) — there's no
special device-bound credential visible in the Retrofit/DI wiring for this specific host beyond what
every other `nativeapps.ryanair.com` call uses. Whether the backend additionally validates a Play
Integrity / app-attestation token on arrival (SafetyNet/Play Integrity is included in the APK,
`DynamicIntegrity`/`PlayIntegrity` classes exist) is not fully resolved by static analysis — R8
had heavily inlined the DI providers for this module, so the auth interceptor chain couldn't be
traced to a concrete header. **Open item**, see below.

## 3. The app-install funnel (`DispatcherActivity`)

`AndroidManifest.xml` shows `DispatcherActivity` as a verified Android App Link
(`android:autoVerify="true"`) for:

```
https://www.ryanair.com/<lang>/<country>/app/*
https://www.ryanair.com/<lang>/<country>/lp/app/*
https://app.ryanair.com/store/android      (-> Play Store)
```

Any `.../app/...` or `.../lp/app/...` link on ryanair.com is designed to be hijacked into the app
when installed (Android App Links), and to fall through to a "download the app" landing page (`lp`
= landing page) in a plain browser otherwise. This is the standard deferred-deep-link install funnel
— generic, not boarding-pass-specific.

## 4. `BoardingPassDeepLinkActivity` — literally in a package called `.deeplink.gate`

`com.ryanair.cheapflights.ui.deeplink.gate.BoardingPassDeepLinkActivity` takes a PNR from an
internal deep-link payload, looks up boarding passes for it via
`GetBoardingPassesForFlightUseCaseImpl`, and routes to one of `HOME` / `BOARDING_PASS` /
`BOARDING_PASS_LIST`. It has no manifest intent-filter of its own — it's reached only through
`DispatcherActivity`'s internal routing, i.e. it's the in-app landing point for whatever
"view your boarding pass" link Ryanair emails/pushes you, confirming that link is meaningless
without the app (no server-rendered PDF fallback exists on that URL).

## 5. The two *legitimate* app-free channels Ryanair itself built

### a. Airport self-service kiosk — `KioskBoardingPassService`
```
POST /v1/boardingpasses/print   (host: nativeapps.ryanair.com/kiosk-api/)
```
This is a real, first-party, no-app-needed path: the airport kiosk hardware calls this to print a
physical boarding pass. Availability and fees vary by airport/base (some Ryanair bases removed free
kiosk printing; some charge an airport check-in fee if you didn't web-check-in first) — this is a
business/contract matter per-airport, not something visible in the Android app.

### b. Google/Samsung/Huawei (and historically Apple) Wallet — `BoardingPassWalletService`
```
PUT <dynamic wallet url>   getBoardingPassWalletToken(...)  -> BoardingPassWalletTokenDto
```
This is a standard "Save to Google Wallet" JWT flow. Practical consequence: **you only need the app
once**, to tap "Add to Wallet". After that, the pass lives in the OS's own Wallet app (Google
Wallet / Samsung Wallet), which receives server-pushed updates (gate/seat changes) independently —
you can uninstall the Ryanair app afterward and the wallet pass still scans at security/gate.
This is the most practical "app-free" outcome: *temporarily* install the app, add the pass to your
phone's wallet, then delete the app.

## Open items (not resolved by static analysis alone)
- Whether `mntappbp.ryanair.com` additionally requires a Play Integrity / app-attestation token
  (would mean a non-app HTTP client with a valid session cookie still gets rejected server-side).
- Exact per-airport kiosk fee/availability matrix (commercial data, not in the app binary).
- Whether iOS currently supports Apple Wallet for boarding passes (this analysis only covers the
  Android build); historically yes.

## Practical takeaway for staying app-free
1. Check in on the web site as normal (works fine, no app needed).
2. Shortly before departure, install the app *once*, log in, open your boarding pass, tap "Add to
   Google/Samsung Wallet", then uninstall the app. The wallet pass is standalone from then on.
3. If you'd rather not touch the app at all: use the airport's self-service check-in kiosk
   (`v1/boardingpasses/print`) where available, or Ryanair's airport desk — both still function
   without the app, subject to that airport's/fare's fee rules.

## 6. Auth mechanics (for the client script in `tools/`)

`MyRyanairAuthInterceptor` (com.ryanair.cheapflights.user.networking) is the real interceptor on
every `nativeapps.ryanair.com`-family request, including boarding pass:
- Header is `X-AUTH-TOKEN: <token>`, **not** `Authorization: Bearer`.
- On a 401 it transparently refreshes via `LoginUsingRefreshMyRyanairToken` and retries once.
- The server can rotate the token on any response (`X-AUTH-TOKEN` response header) — the app
  persists whatever comes back via `SessionController.h(token)`.

`res/xml/network_security_config.xml` sets no certificate pinning for any Ryanair host (the only
pinned traffic belongs to a third-party in-flight-connectivity SDK, `com.airware.*`, unrelated to
login/boarding pass). This means a user-installed MITM proxy (mitmproxy/HTTP Toolkit with its root
CA added as a user CA) can observe the app's own traffic, including the real `X-AUTH-TOKEN` the app
received at login — a user capturing their own session's header this way is reading their own
device's own traffic, not breaking anything server-side.

### Request shapes confirmed from the DTOs
```
POST https://mntappbp.ryanair.com/v1/boardingpass
Header: X-AUTH-TOKEN: <token>
Body:   {"pnr": "<PNR>", "email": "<account email>"}
->      [BoardingPassDto, ...]   (heavily obfuscated field names; see tools/client.py)

POST https://mntappbp.ryanair.com/v1/boardingpasses
Header: X-AUTH-TOKEN: <token>
Body:   {"customerId": "<myRyanair customer id>", "bookingsId": ["<bookingId>", ...]}
->      [BoardingPassDto, ...]
```
