# frontend/

The operator web UI lives under `web/`. It is a Vite + React 18 + TypeScript
single-page application served by nginx in production. Key design choices:

- Static SPA shipped from nginx; no SSR. Avoids a Node.js runtime in the
  production image.
- The API client is a thin fetch wrapper; transport-level concerns
  (authentication, org context) are centralized.
- Internationalization is first-class — the UI ships with multiple language
  bundles and the language switcher is in the header.
- Component library is intentionally small; no design-system dependency.
