/**
 * VWLR Tender Map — daily Tender247 → Supabase ingestion.
 *
 * Reads Tender247 alert emails from Gmail, extracts each tender (id, title,
 * document link, authority, location, value, deadline) and posts them to the
 * Supabase RPC `ingest_tender247_batch`, which filters to coal-transport
 * relevance, de-dupes, attaches the document link, and publishes the good ones.
 *
 * SETUP (once, ~3 min):
 *   1. script.google.com → New project → paste this file (replace Code.gs).
 *   2. Run  ingestTender247  once → approve the Gmail + external-request prompts.
 *   3. Triggers (clock icon) → Add Trigger → function ingestTender247,
 *      event source "Time-driven" → Day timer → e.g. 7–8am. Save.
 * That's it — it now runs every morning. Run it manually any time to catch up.
 */

// ---- config (all values below are your own project's; safe to keep here) ----
var SUPABASE_URL  = 'https://sysicrpylpnzpcuvpvjc.supabase.co';
var ANON_KEY      = 'sb_publishable_-nuAQ96NVJqLQNc9wr6DpA_p6nLz0u7';
var INGEST_SECRET = '016c545fdf6b7c144d2ed6683fa7e805f2fb';
// newer_than:30d gives a one-run month-long backfill; the daily trigger then
// only ever finds the day's new (unlabeled) alerts. Widen to 60d/90d once if
// you want to sweep further back.
var GMAIL_QUERY   = 'from:admin@bidsnrfp.com subject:"New Tender/s" newer_than:30d';
var DONE_LABEL    = 'Tender247-Ingested';

// Matches one tender block in a Tender247 alert email.
var TENDER_RE =
  'T247 ID :\\s*<label[^>]*>(\\d+)<\\/label>' +          // 1: T247 id
  '[\\s\\S]*?<a href="([^"]+)"[^>]*>([\\s\\S]*?)<\\/a>' + // 2: doc link, 3: title html
  '[\\s\\S]*?<span style="color: #000;[^"]*">([^<]+)<\\/span>' + // 4: authority
  '[\\s\\S]*?<br\\/>\\s*<br\\/>\\s*([^<]+?)\\s*<\\/p>' +  // 5: location
  '[\\s\\S]*?<span style="color: black;">([^<]*)<\\/span>' + // 6: value
  '[\\s\\S]*?<br\\/>\\s*<br\\/>\\s*([\\d-]+)\\s*<\\/p>';  // 7: deadline (DD-MM-YYYY)

function ingestTender247() {
  var label = GmailApp.getUserLabelByName(DONE_LABEL) || GmailApp.createLabel(DONE_LABEL);
  var threads = GmailApp.search(GMAIL_QUERY + ' -label:' + DONE_LABEL, 0, 50);
  var items = [], done = [];

  threads.forEach(function (th) {
    th.getMessages().forEach(function (msg) {
      var html = msg.getBody(), re = new RegExp(TENDER_RE, 'g'), m;
      while ((m = re.exec(html)) !== null) {
        items.push({
          source_uid: m[1],
          doc_url:    m[2],
          title:      cleanTitle(m[3]),
          authority:  (m[4] || '').trim(),
          state:      parseState(m[5]),
          value_inr:  parseValue(m[6]),
          deadline:   parseDate(m[7]),
          ref_no:     'T247-' + m[1],
          portal:     'Tender247'
        });
      }
    });
    done.push(th);
  });

  if (!items.length) { Logger.log('No new Tender247 tenders.'); return; }

  var resp = UrlFetchApp.fetch(SUPABASE_URL + '/rest/v1/rpc/ingest_tender247_batch', {
    method: 'post', contentType: 'application/json',
    headers: { apikey: ANON_KEY, Authorization: 'Bearer ' + ANON_KEY },
    payload: JSON.stringify({ p_secret: INGEST_SECRET, p_items: items }),
    muteHttpExceptions: true
  });
  Logger.log('Sent ' + items.length + ' tenders → ' + resp.getResponseCode() + ' ' + resp.getContentText());
  if (resp.getResponseCode() === 200) done.forEach(function (th) { th.addLabel(label); });
}

function cleanTitle(html) {
  return html.replace(/<[^>]+>/g, '')
             .replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
             .replace(/\s+/g, ' ').trim()
             .replace(/\s*\|\s*quantity.*$/i, '').trim()
             .substring(0, 300);
}
function parseState(loc) {
  var p = (loc || '').split(',').map(function (x) { return x.trim(); });
  return p.length >= 2 ? p[p.length - 2] : (p[0] || null);   // "City, State, India" → State
}
function parseValue(s) {
  if (!s || /refer/i.test(s)) return null;
  var m = s.match(/([\d.,]+)\s*(cr|crore|lac|lakh|lacs|lakhs)?/i);
  if (!m) return null;
  var n = parseFloat(m[1].replace(/,/g, '')); if (isNaN(n)) return null;
  var u = (m[2] || '').toLowerCase();
  if (u.indexOf('cr') === 0) return Math.round(n * 1e7);
  if (u.indexOf('lac') === 0 || u.indexOf('lakh') === 0) return Math.round(n * 1e5);
  return Math.round(n);
}
function parseDate(s) {
  var m = (s || '').match(/(\d{2})-(\d{2})-(\d{4})/);
  return m ? (m[3] + '-' + m[2] + '-' + m[1]) : null;   // DD-MM-YYYY → YYYY-MM-DD
}
