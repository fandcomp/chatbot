// k6 load test (spec §98/M15) against the /chat endpoint, checked against
// §46's performance targets (TTFT < 2s p95 for a normal query). This
// exercises the non-streaming endpoint only — k6's http module can't read
// an SSE stream's first-byte timing, so /chat/stream's real TTFT needs a
// browser-based or xk6-sse-based test if that number specifically is
// needed; documented gap, not attempted here.
//
// Usage (requires https://k6.io installed locally — not run in this repo's
// own CI or dev environment, which has no load-test-scale seeded data):
//
//   k6 run --env BASE_URL=http://localhost:8000 \
//          --env EMAIL=owner@example.com --env PASSWORD='...' \
//          --env QUERY='Apa isi Pasal 5?' \
//          infrastructure/load_test/chat_load_test.js
//
// Seed the target org with real ACTIVE documents and a real Voyage/HF key
// before running — against an empty knowledge base every request falls
// through to "insufficient evidence", which measures the wrong path.

import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const EMAIL = __ENV.EMAIL;
const PASSWORD = __ENV.PASSWORD;
const QUERY = __ENV.QUERY || "Apa isi Pasal 5?";

export const options = {
  scenarios: {
    steady_load: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 5),
      duration: __ENV.DURATION || "1m",
    },
  },
  thresholds: {
    // Spec §46: TTFT < 2s p95 for a normal query. /chat is not streaming,
    // so this measures full-response latency, not first-token latency —
    // a stricter bar than TTFT, kept deliberately conservative.
    http_req_duration: ["p(95)<2000"],
    checks: ["rate>0.99"],
  },
};

export function setup() {
  const loginResponse = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(loginResponse, { "login succeeded": (r) => r.status === 200 });
  const cookie = loginResponse.cookies["session"];
  return { sessionCookie: cookie ? cookie[0].value : null };
}

export default function (data) {
  const response = http.post(
    `${BASE_URL}/chat`,
    JSON.stringify({ query: QUERY }),
    {
      headers: { "Content-Type": "application/json" },
      cookies: { session: data.sessionCookie },
    }
  );
  check(response, {
    "status is 200": (r) => r.status === 200,
    "answer present": (r) => JSON.parse(r.body).answer !== undefined,
  });
  sleep(1);
}
