# Isthmus frontend (Vite + React + TypeScript, deck.gl + MapLibre)

```bash
npm install
npm run dev        # http://localhost:5173 — expects the backend on :8000 (see backend/README.md)
npm run lint && npm run build
```

- Basemap: CARTO Dark Matter (free, no API key).
- API URL: `VITE_API_URL` (see `.env.example`).
- Response shape: `src/types.ts` mirrors `contracts/api_response.json`.
- The top-right badge shows where results come from (placeholder / mock engine / live engine).

Layout: `src/components/` (map, controls, wind dial, cards, timeline, legend, tooltip),
`src/tabs/` (Planning, Assumptions), `src/lib/` (colors, formatting, geometry, derived data).
