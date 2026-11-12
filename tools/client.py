"""
Ryanair boarding-pass API client (reverse-engineered from the Android app's own code,
see ../notes/findings.md sections 2 and 6).

This does NOT bypass any technical access control the app itself doesn't also skip past
(no cert pinning found for this host) - but it DOES bypass Ryanair's product decision to
keep boarding-pass issuance app-exclusive. Read notes/findings.md before using it. Running
this against your own account is between you and Ryanair's Terms of Service, not something
this script decides for you.

You supply AUTH_TOKEN yourself (see findings.md #6 for how to capture it from your own
device's traffic). This script never asks for, stores, or transmits your Ryanair password.

usage:
    python tools/client.py --token <X-AUTH-TOKEN> --pnr ABC123 --email you@example.com
"""
import argparse
import hashlib
import json
import sys
import urllib.request
import urllib.error

BASE = "https://mntappbp.ryanair.com"
USRPROF = "https://www.ryanair.com/api/usrprof/v2/accounts"
APP_VERSION = "3.243.0"

# Stable device fingerprint matching DeviceInfoImpl.b() — SHA1(seed), hex.
# The server uses this as a persistent device ID; any stable value works.
_DEVICE_FINGERPRINT = hashlib.sha1(b"ryanair-client-00000001").hexdigest()


def refresh_token(customer_id: str, session_cookie: str) -> str:
    """Exchange a web SESSION_COOKIE for a fresh X-AUTH-TOKEN."""
    req = urllib.request.Request(
        f"{USRPROF}/{customer_id}/sessionToken",
        headers={
            "Accept": "application/json, text/plain, */*",
            "client": "desktop",
            "client-version": "0.162.0 (desktop)",
            "Cookie": session_cookie,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            print(f"[refresh] got token", file=sys.stderr)
            return data["token"]
    except urllib.error.HTTPError as e:
        print(f"[refresh] HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        raise


def post(path: str, token: str, body: dict) -> object:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-AUTH-TOKEN": token,
            "client": "android",
            "client-os": "34",
            "client-version": APP_VERSION,
            "client-carrier-code": "FR",
            "User-Agent": f"RyanAir/{APP_VERSION} (Android)",
            "X-DEVICE-FINGERPRINT": _DEVICE_FINGERPRINT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        raise


def get_boarding_pass_for_flight(token: str, pnr: str, email: str):
    return post("/v1/boardingpass", token, {"RecordLocator": pnr, "Email": email})


def get_boarding_passes_for_bookings(token: str, customer_id: str, booking_ids: list):
    return post("/v1/boardingpasses", token, {"CustomerId": customer_id, "BookingIds": booking_ids})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--token", help="X-AUTH-TOKEN from app traffic (see findings.md #6)")
    group.add_argument("--cookie", help="cookie string from browser (refreshes token automatically)")
    group.add_argument("--cookie-file", help="file containing the cookie string")
    ap.add_argument("--customer-id", help="account ID (required with --cookie)")
    ap.add_argument("--pnr", required=True)
    ap.add_argument("--email", required=True)
    args = ap.parse_args()

    if args.cookie or args.cookie_file:
        if not args.customer_id:
            ap.error("--customer-id is required when using --cookie/--cookie-file")
        cookie = args.cookie or open(args.cookie_file).read().strip()
        token = refresh_token(args.customer_id, cookie)
    else:
        token = args.token

    print(json.dumps(get_boarding_pass_for_flight(token, args.pnr, args.email), indent=2))
