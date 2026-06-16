# Moony E2E (Playwright)

Prerequisiti: stack Docker avviato (`docker compose up` o `make up`).

```bash
# dalla root del repo
docker compose up -d

# install (una volta)
cd frontend
npm install
npx playwright install chromium

# test
npm run test:e2e
```

Variabili:

- `PLAYWRIGHT_BASE_URL` — default `http://localhost:5190` (porta `WEB_HOST_PORT` in compose)

Report HTML: `npx playwright show-report` dopo una run fallita.
