# web/

Next.js front end for StockScanner. Requests to `/api/*` are proxied to the
FastAPI backend (`BACKEND_URL`, default `http://localhost:8000`).

```bash
npm install
npm run dev      # http://localhost:3000
npm run lint
npm run typecheck
npm run build
```
