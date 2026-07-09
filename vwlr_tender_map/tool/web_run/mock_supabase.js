// Local stand-in for the VWLR Supabase PostgREST API, seeded with the real
// rows. Lets the Flutter web build be driven end-to-end on a machine where
// *.supabase.co is unreachable (e.g. a locked-down CI sandbox). Point the app
// at it by setting Config.supabaseUrl to http://127.0.0.1:54321 for the run.
//
//   node tool/web_run/mock_supabase.js         # serves on :54321
//
// Endpoints mirror what lib/services/tender_repository.dart calls:
//   GET   /rest/v1/org_profile?select=*&id=eq.1        (single object)
//   GET   /rest/v1/tenders?select=*&order=deadline.asc.nullslast
//   GET   /rest/v1/locations?select=*
//   PATCH /rest/v1/tenders?id=eq.<uuid>                (heart / status write-back -> 204)
const http = require('http');

const org = {"id":1,"name":"Vedanta Washery & Logistic Solutions","railway_code":"VWLR","lat":21.9833,"lng":83.1,"address":"VWLR Railway Siding, Kharsia, Dist. Raigarh, Chhattisgarh","avg_turnover_inr":100000000,"net_worth_inr":50000000,"paid_up_capital_inr":20000000,"max_experience_mt":160000,"experience_window_months":7,"max_single_month_mt":23000,"is_msme":true,"operating_radius_km":300};

let tenders = [
  {"id":"14f2b7c2-5126-4f10-9706-079060a93fd2","ref_no":"NSPCL/SSC-CS/Rourkela-CoalTransport","title":"Coal loading, unloading & road transportation to NSPCL Rourkela","authority":"NSPCL (NTPC-SAIL Power Co.)","portal":"GeM","source_field":"MCL Ib Valley Coalfield","value_inr":93095746.59,"emd_inr":1000000,"pbg_inr":4654787,"deadline":"2026-05-13T09:30:00+00:00","tech_open":"2026-05-13T10:00:00+00:00","contract_months":7,"qr_min_turnover_inr":86800000,"qr_experience_mt":155800,"qr_experience_window_months":7,"qr_networth_pct":100,"eligibility_notes":"Also needs >=22,300 MT in any single month in one contract. Class-I local supplier only. MSE EMD exemption possible (not for traders). ePBG 5% of value valid 11 months via SBI.","pdf_url":null,"status":"closed","hearted":true},
  {"id":"4940b892-f6d3-46ea-a90c-ce837ad73585","ref_no":"eGR2994","title":"Coal road transportation (RCR) for NALCO CPP","authority":"NALCO","portal":"GeM (Limited / Invitation-only)","source_field":"MCL Ib Valley / Talcher Coalfield","value_inr":49400000,"emd_inr":450000,"pbg_inr":40000000,"deadline":null,"tech_open":null,"contract_months":null,"qr_min_turnover_inr":null,"qr_experience_mt":null,"qr_experience_window_months":null,"qr_networth_pct":null,"eligibility_notes":"Invitation-only limited tender for NALCO-enlisted vendors (no separate PQC). Max 110 km mine-to-siding. GST/PAN/EPF/ESI + Pre-Contract Integrity Pact mandatory. Verify deadline on GeM.","pdf_url":null,"status":"live","hearted":false}
];

const locations = [
  {"id":"e0662803-b080-48b9-ab5c-2876275101ff","tender_id":"14f2b7c2-5126-4f10-9706-079060a93fd2","role":"mine","name":"MCL Belpahar railhead (Ib Valley)","lat":21.7,"lng":83.63,"district":"Jharsuguda","state":"Odisha","pin":null,"road_km_from_base":110,"notes":"Road haul from mine; rail-loadable siding"},
  {"id":"c46cdc70-aae5-4ef4-9d12-c095db32d499","tender_id":"14f2b7c2-5126-4f10-9706-079060a93fd2","role":"plant","name":"NSPCL Rourkela CPP - HSPG Siding","lat":22.227,"lng":84.81,"district":"Sundergarh","state":"Odisha","pin":"769011","road_km_from_base":180,"notes":"Consignee: NSPCL Store CPP II, Rourkela Steel Plant"},
  {"id":"42437f01-13d8-45f2-9ccf-8519782a0985","tender_id":"14f2b7c2-5126-4f10-9706-079060a93fd2","role":"base","name":"VWLR Kharsia (home siding)","lat":21.9833,"lng":83.1,"district":"Raigarh","state":"Chhattisgarh","pin":null,"road_km_from_base":0,"notes":"Optional staging/blending route"},
  {"id":"176ad4bd-b7cb-41ef-b557-e701e34671db","tender_id":"4940b892-f6d3-46ea-a90c-ce837ad73585","role":"mine","name":"MCL Ib Valley (Jharsuguda/Belpahar)","lat":21.7,"lng":83.63,"district":"Jharsuguda","state":"Odisha","pin":null,"road_km_from_base":110,"notes":"Diesel ref at Jharsuguda points here"},
  {"id":"3d7efb83-5d4c-4745-a47a-a4aa49b396f8","tender_id":"4940b892-f6d3-46ea-a90c-ce837ad73585","role":"mine","name":"MCL Talcher Coalfield","lat":20.95,"lng":85.23,"district":"Angul","state":"Odisha","pin":null,"road_km_from_base":320,"notes":"Alternate source per Engineer-in-Charge"},
  {"id":"5520e517-2be0-453c-af81-553cb668b437","tender_id":"4940b892-f6d3-46ea-a90c-ce837ad73585","role":"plant","name":"NALCO CPP Angul","lat":20.84,"lng":85.1,"district":"Angul","state":"Odisha","pin":"759145","road_km_from_base":300,"notes":"Captive power plant / smelter complex"}
];

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,DELETE,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
}
function orderedTenders() {
  return [...tenders].sort((a, b) => {
    if (a.deadline == null && b.deadline == null) return 0;
    if (a.deadline == null) return 1;
    if (b.deadline == null) return -1;
    return new Date(a.deadline) - new Date(b.deadline);
  });
}
const idFrom = q => { const m = /(?:^|&)id=eq\.([^&]+)/.exec(q || ''); return m ? decodeURIComponent(m[1]) : null; };

const server = http.createServer((req, res) => {
  cors(res);
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
  const u = new URL(req.url, 'http://localhost');
  const single = (req.headers['accept'] || '').includes('pgrst.object');
  const send = (code, body) => { res.writeHead(code, { 'Content-Type': 'application/json' });
    res.end(body == null ? '' : JSON.stringify(body)); console.log(req.method, req.url, '->', code); };

  if (u.pathname === '/rest/v1/org_profile') return send(200, single ? org : [org]);
  if (u.pathname === '/rest/v1/locations') return send(200, locations);
  if (u.pathname === '/rest/v1/tenders') {
    if (req.method === 'GET') return send(200, orderedTenders());
    if (req.method === 'PATCH') {
      const id = idFrom(u.search.slice(1)); let raw = '';
      req.on('data', c => raw += c);
      req.on('end', () => { try { const patch = raw ? JSON.parse(raw) : {};
        const row = tenders.find(t => t.id === id); if (row) Object.assign(row, patch);
        res.writeHead(204); res.end(); console.log('PATCH', req.url, '-> 204');
      } catch (e) { send(400, { message: String(e) }); } });
      return;
    }
  }
  send(200, []); // benign default (e.g. /auth/v1/*)
});
const PORT = process.env.MOCK_PORT || 54321;
server.listen(PORT, '127.0.0.1', () => console.log('mock supabase on http://127.0.0.1:' + PORT));
