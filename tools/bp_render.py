"""Render a boarding-pass barcode as an Aztec PNG named <PNR>_<DEPARR>_<DATE>.png,
e.g. XYZ123_STNDUB_20260101.png.

Needs: pip install playwright && playwright install chromium
"""
import json, pathlib

BWIP_PATH = pathlib.Path(__file__).parent / "bwip-js-min.js"


def _ensure_bwip():
    if BWIP_PATH.exists():
        return
    import urllib.request
    urllib.request.urlretrieve(
        "https://cdnjs.cloudflare.com/ajax/libs/bwip-js/4.1.0/bwip-js-min.js", BWIP_PATH)


def derive_filename(bp: dict) -> str:
    pnr  = bp.get("pnr", "PNR")
    dep  = bp.get("departure", {}).get("code", "")
    arr  = bp.get("arrival", {}).get("code", "")
    date = (bp.get("departure", {}).get("date", "")[:10] or "").replace("-", "")
    return f"{pnr}_{dep}{arr}_{date}.png"


def render_to_image(bp: dict, out_path: str = None) -> str:
    out_path = out_path or derive_filename(bp)
    _ensure_bwip()

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<style>*{{margin:0;padding:0}}body{{display:inline-block;background:#fff}}
#bc{{display:block;image-rendering:pixelated}}</style></head>
<body><canvas id="bc"></canvas>
<script>{BWIP_PATH.read_text(encoding='utf-8')}</script>
<script>bwipjs.toCanvas('bc',{{bcid:'azteccode',text:{json.dumps(bp.get('barcode',''))},scale:8,padding:0}});</script>
</body></html>"""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("[render] playwright not installed.\n"
                         "Run:  pip install playwright && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(300)
        page.locator("#bc").screenshot(path=out_path)
        browser.close()

    print(f"[render] saved → {out_path}")
    return out_path
