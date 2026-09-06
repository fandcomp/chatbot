# Load Test (M15)

`chat_load_test.js` is a [k6](https://k6.io) script exercising `POST /chat`
against §46's performance targets. It is not run in this repo's own dev
environment or CI — this milestone ships the tooling, not a load-test
result, since a meaningful run needs a seeded knowledge base at production
scale and real Voyage/HF credentials, neither of which exist in this
sandboxed dev setup.

```bash
k6 run --env BASE_URL=https://staging.example.com \
       --env EMAIL=owner@example.com --env PASSWORD='...' \
       infrastructure/load_test/chat_load_test.js
```

Only `/chat` (non-streaming) is covered. `/chat/stream`'s real
time-to-first-token needs an SSE-aware client (k6's `xk6-sse` extension, or
a small Playwright script) to measure correctly — not attempted here.
