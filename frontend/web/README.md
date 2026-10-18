# Operator web UI

Vite + React 18 + TypeScript single-page application.

## Development

```bash
npm install
npm run dev
```

Open `http://localhost:8080`. The default org slug can be changed via the org
input in the header; it is persisted to localStorage.

## Build

```bash
npm run build
```

Produces a static bundle in `dist/` that the production Dockerfile copies
into an nginx image.

## Project layout

```
src/api/         — typed API client and response shapes
src/components/  — Layout, TimelineEvent, BPMN/DMN viewers, etc.
src/pages/       — Queue, CaseDetail, Audit, Reports, Connections, UAPF
src/main.tsx     — router + app entry
src/index.css    — Tailwind imports
```
