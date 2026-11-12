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
import json
import sys
import urllib.request
import urllib.error

BASE = "https://mntappbp.ryanair.com"


def post(path: str, token: str, body: dict) -> object:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-AUTH-TOKEN": token,
            # app identifies itself with these on every call (ApiBuildConfiguration.m()/h());
            # harmless to include, included for fidelity with what the real app sends
            "User-Agent": "Ryanair/3.243.0 (Android)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        raise


def get_boarding_pass_for_flight(token: str, pnr: str, email: str):
    return post("/v1/boardingpass", token, {"pnr": pnr, "email": email})


def get_boarding_passes_for_bookings(token: str, customer_id: str, booking_ids: list):
    return post("/v1/boardingpasses", token, {"customerId": customer_id, "bookingsId": booking_ids})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="your own X-AUTH-TOKEN, captured by you (see findings.md #6)")
    ap.add_argument("--pnr", required=True)
    ap.add_argument("--email", required=True)
    args = ap.parse_args()
    print(json.dumps(get_boarding_pass_for_flight(args.token, args.pnr, args.email), indent=2))
