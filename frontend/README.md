# Content Studio — Dashboard

Vite + React + Tailwind dashboard for the Content Studio backend. See the
[repo root README](../README.md) for the full quick-start (backend +
frontend together) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for
the overall system.

```bash
npm install
npm run dev      # http://localhost:5173, talks to the backend on :8000
npm run build    # → dist/, served directly by the backend in production
```

`VITE_API_BASE_URL` overrides the backend URL if it's not on
`http://localhost:8000/api` (see `src/lib/api.js`).
