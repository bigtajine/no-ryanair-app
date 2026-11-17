"use strict";

// Same-origin fetches run here because they need the page's cookies.
// The cross-origin boarding-pass call goes through background.js.

async function fingerprint() {
  const { fp } = await chrome.storage.local.get("fp");
  if (fp) return fp;
  const bytes = crypto.getRandomValues(new Uint8Array(20));
  const hex = [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
  await chrome.storage.local.set({ fp: hex });
  return hex;
}

async function getToken(cid) {
  const tr = await fetch(`/api/usrprof/v2/accounts/${cid}/sessionToken`, {
    credentials: "include",
    headers: { "Accept": "application/json", "client": "desktop", "client-version": "0.162.0 (desktop)" }
  });
  if (!tr.ok) throw new Error(`sessionToken ${tr.status}: log in to ryanair.com first`);
  return (await tr.json()).token;
}

async function resolveTrip() {
  const m = location.pathname.match(/\/trip\/manage\/([0-9a-f-]{36})/i);
  if (!m) throw new Error("not a manage-trip page");
  const tripId = m[1];

  const cid = sessionStorage.getItem("myRyanairID");
  if (!cid) throw new Error("not logged in (no myRyanairID)");

  const token = await getToken(cid);
  const r = await fetch(`/api/orders/v2/orders/${cid}/trips/${tripId}`, {
    credentials: "include",
    headers: { "Accept": "application/json", "X-AUTH-TOKEN": token, "client": "desktop", "client-version": "0.162.0 (desktop)" }
  });
  if (!r.ok) throw new Error(`trip ${r.status}`);
  const trip = await r.json();

  const flight = trip.flights?.[0];
  if (!flight) throw new Error("no flight on this trip");

  return { cid, bookingId: flight.bookingId };
}

function fileName(bp) {
  const pnr  = bp.pnr || "PNR";
  const dep  = bp.departure?.code || "";
  const arr  = bp.arrival?.code || "";
  const date = (bp.departure?.date || "").slice(0, 10).replace(/-/g, "");
  return `${pnr}_${dep}${arr}_${date}.png`;
}

function renderDataUrl(barcode) {
  const canvas = document.createElement("canvas");
  bwipjs.toCanvas(canvas, { bcid: "azteccode", text: barcode, scale: 8, padding: 0 });
  return canvas.toDataURL("image/png");
}

async function run() {
  const { cid, bookingId } = await resolveTrip();
  const fp = await fingerprint();
  const token = await getToken(cid); // fresh: tokens are short-lived
  const bp = await chrome.runtime.sendMessage({
    type: "fetchBoardingPass",
    cid, bookingId, token, fp
  });
  if (!bp?.ok) throw new Error(bp?.reason || "boarding pass fetch failed");
  if (!bp.data?.barcode) throw new Error("no barcode in response (checked in yet?)");

  return { ok: true, filename: fileName(bp.data), dataUrl: renderDataUrl(bp.data.barcode) };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg === "run") {
    run().then(reply).catch(e => reply({ ok: false, reason: e.message || String(e) }));
    return true; // keep the message channel open for the async reply
  }
});
