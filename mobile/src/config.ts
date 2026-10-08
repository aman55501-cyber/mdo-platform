// Shares CFO — app config. EDIT THESE TWO VALUES before running.
//
// 1) API_BASE — your PC's LAN IP (NOT "localhost" — the phone can't reach the PC's
//    localhost). On your PC run `ipconfig` and use the IPv4 address, e.g.
//    http://192.168.1.23:8000 . If you use Tailscale, use its 100.x.y.z address.
// 2) CFO_API_TOKEN — must match CFO_API_TOKEN in your backend .env exactly.

export const CONFIG = {
  API_BASE: "http://192.168.1.23:8000",
  CFO_API_TOKEN: "paste_your_CFO_API_TOKEN_here",

  // How often the Dashboard re-pulls during use (ms). 20s is smooth and safe.
  REFRESH_MS: 20000,
};
