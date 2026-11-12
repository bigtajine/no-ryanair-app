"use strict";

const BP_URL  = "https://mntappbp.ryanair.com/v1/boardingpasses";
const APP_VER = "3.243.0";

function badge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) chrome.action.setBadgeBackgroundColor({ color });
}

// Only background bypasses CORS, via host_permissions.
chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type !== "fetchBoardingPass") return;
  (async () => {
    try {
      const r = await fetch(BP_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AUTH-TOKEN": msg.token,
          "client": "android",
          "client-os": "34",
          "client-version": APP_VER,
          "client-carrier-code": "FR",
          "X-DEVICE-FINGERPRINT": msg.fp
        },
        body: JSON.stringify({ CustomerId: msg.cid, BookingIds: [Number(msg.bookingId)] })
      });
      if (!r.ok) {
        reply({ ok: false, reason: `boarding pass ${r.status}: ${(await r.text()).slice(0, 120)}` });
        return;
      }
      const data = await r.json();
      reply({ ok: true, data: Array.isArray(data) ? data[0] : data });
    } catch (e) {
      reply({ ok: false, reason: e.message || String(e) });
    }
  })();
  return true;
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id || !/^https:\/\/www\.ryanair\.com\/.*\/trip\/manage\//.test(tab.url || "")) {
    badge("!", "#c0262c");
    chrome.action.setTitle({ title: "Open a Manage Trip page on ryanair.com first", tabId: tab?.id });
    return;
  }

  badge("…", "#0A3BA0");
  try {
    const result = await chrome.tabs.sendMessage(tab.id, "run");
    if (!result?.ok) {
      badge("!", "#c0262c");
      chrome.action.setTitle({ title: result?.reason || "failed", tabId: tab.id });
      return;
    }
    await chrome.downloads.download({ url: result.dataUrl, filename: result.filename, saveAs: false });
    badge("✓", "#1a7a34");
    chrome.action.setTitle({ title: `Saved ${result.filename}`, tabId: tab.id });
  } catch (e) {
    badge("!", "#c0262c");
    chrome.action.setTitle({ title: String(e.message || e), tabId: tab.id });
  }
});
