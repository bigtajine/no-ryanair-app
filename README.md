# ryanair-app-gate-re

Reverse-engineering investigation: why does Ryanair require the mobile app (not the
mobile/desktop web site) to issue a boarding pass, when web check-in works fine?
Goal: find the actual technical gate (API flag, feature check, server-side rule) and
any legitimate way to get a boarding pass without installing the app.

Scope: static analysis of the public Ryanair Android APK (JADX/decompile) + black-box
HTTP comparison between web check-in and app check-in. No credential misuse, no
bypassing authentication, no ToS violations beyond "use my own account's web session
to see what the app's API actually returns."

## Status
Done (v1). See notes/findings.md for the full writeup.

Short version: boarding-pass issuance runs on its own backend subdomain family
(`*bp.ryanair.com`) that the public website was never wired to call — it's an
infrastructure/policy split, not a client-side flag. Two legitimate app-free paths exist
and are built by Ryanair itself: the airport self-service kiosk print API, and
Google/Samsung Wallet — add the pass to your phone's wallet once via the app, then you
can delete the app and the wallet pass still works (server-pushed updates, not app-pushed).

## Plan
1. Pull the current Ryanair Android APK (device backup / APKMirror / APKPure — an
   official-mirror copy of the exact store build, not a modified one).
2. jadx-decompile; grep for boarding-pass / check-in / "app only" gating strings,
   feature flags, remote-config keys.
3. Compare web check-in network calls (browser devtools) vs what the app's
   decompiled code calls for the same step — diff the endpoints/response fields
   (e.g. does web get a `boardingPassUrl: null` where app gets a real one?).
4. Write up the actual mechanism (client-side gate vs server-side entitlement)
   and any legitimate workarounds (third-party checkin services, PWA, printing from
   airport kiosk, third-party boarding-pass wallets, EU261/consumer-rights angle).
