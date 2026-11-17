"""Fetch a boarding pass from the Ryanair app API with your own X-AUTH-TOKEN or browser cookie.

See docs/technical-writeup.md for how the API was found.
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

# The server accepts any SHA1 hex as the device ID.
_DEVICE_FINGERPRINT = hashlib.sha1(b"ryanair-client-00000001").hexdigest()


def refresh_token(customer_id: str, session_cookie: str) -> str:
    """Exchange a web SESSION_COOKIE for a fresh X-AUTH-TOKEN."""
    req = urllib.request.Request(
        f"{USRPROF}/{customer_id}/sessionToken",
        headers={
            "Accept": "application/json, text/plain, */*",
            "client": "desktop",
            "client-version": "0.162.0 (desktop)",
            "Cookie": session_cookie.encode("latin-1", errors="replace").decode("latin-1"),
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
    group.add_argument("--token", help="X-AUTH-TOKEN (see docs/technical-writeup.md §6)")
    group.add_argument("--cookie", help="cookie string from browser (refreshes token automatically)")
    group.add_argument("--cookie-file", help="file containing the cookie string")
    ap.add_argument("--customer-id", help="myRyanair account ID (required with --cookie)")
    ap.add_argument("--pnr", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--png", action="store_true",
                    help="save barcode PNG named <PNR>_<DEPARR>_<DATE>.png (requires playwright)")
    ap.add_argument("--out", metavar="FILE.png",
                    help="override the PNG output path (implies --png)")
    args = ap.parse_args()

    if args.cookie or args.cookie_file:
        if not args.customer_id:
            ap.error("--customer-id is required when using --cookie/--cookie-file")
        cookie = args.cookie or open(args.cookie_file).read().strip()
        token = refresh_token(args.customer_id, cookie)
    else:
        token = args.token

    data = get_boarding_pass_for_flight(token, args.pnr, args.email)

    if args.png or args.out:
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from bp_render import render_to_image
        # API returns a list; render the first
        bp = data[0] if isinstance(data, list) else data
        render_to_image(bp, args.out)
    else:
        print(json.dumps(data, indent=2))
