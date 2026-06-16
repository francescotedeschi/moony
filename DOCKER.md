# Docker — Moony

## Prerequisiti

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installato e avviato
- File `catalog/catalog.json` presente (il tuo export MOSS)
- File `.env` nella root del progetto

## Setup iniziale (una volta)

```bash
cd ~/Projects/moony

# Se non hai .env:
cp .env.example .env
# Modifica .env e inserisci JAMENDO_CLIENT_ID (già fatto)
# MUSIXMATCH_API_KEY può restare vuoto per ora

# Verifica catalogo
ls -lh catalog/catalog.json
```

## Avvio sviluppo

```bash
make up
# oppure
docker compose up --build
```

| Servizio | URL | Descrizione |
|----------|-----|-------------|
| **web** | http://localhost:5173 | React + Vite (hot reload) |
| **api** | http://localhost:8000 | FastAPI |
| **health** | http://localhost:8000/health | Stato + conteggio tracce |
| **postgres** | localhost:5433 | DB (user/pass/db: `moony`) — porta 5433 per evitare conflitti con Postgres locale |

In background:

```bash
make up-d
make logs      # tutti i log
make health    # verifica API
make down      # stop
```

## Struttura servizi

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  web :5173  │────▶│  api :8000  │────▶│ postgres     │
│  (React)    │     │  (FastAPI)  │     │  (opzionale) │
└─────────────┘     └──────┬──────┘     └──────────────┘
                           │
                    catalog.json (volume read-only)
```

- Il **catalogo** è montato da `./catalog` → `/app/catalog` (modifiche al JSON visibili dopo restart API)
- Il codice **backend** e **frontend** sono montati con hot reload
- `node_modules` del frontend sta in un volume Docker (`web_node_modules`) per evitare conflitti Mac/Linux

## File `.env` per Docker

```env
JAMENDO_CLIENT_ID=your_id
MUSIXMATCH_API_KEY=
CATALOG_PATH=catalog/catalog.json
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
DATABASE_URL=postgresql://moony:moony@postgres:5432/moony
VITE_API_URL=http://localhost:8000
```

`VITE_API_URL` punta a `localhost:8000` perché il **browser** (sul tuo Mac) chiama l’API esposta sulla porta mappata — non il nome servizio Docker `api`.

## Problemi comuni

### Porta 5432 già in uso

Moony usa **5433** sul Mac per default (`5433:5432` nel compose). Se anche 5433 è occupata, cambia in `docker-compose.yml`:

```yaml
postgres:
  ports:
    - "5434:5432"
```

### Porta 8000 o 5173 occupata

Cambia il mapping, es. `"8001:8000"` e aggiorna `VITE_API_URL=http://localhost:8001`.

### API: catalog not loaded / 0 tracks

```bash
docker compose exec api ls -la /app/catalog/
# deve esserci catalog.json

docker compose restart api
curl http://localhost:8000/health
```

### Frontend non parte / node_modules

```bash
docker compose down
docker volume rm moony_web_node_modules 2>/dev/null || true
docker compose up --build
```

### Ricostruire da zero

```bash
docker compose down -v   # ATTENZIONE: cancella anche dati postgres
docker compose up --build
```

## Produzione (Railway)

Per Railway non usi questo compose completo:

1. **API** — build `backend/Dockerfile`, monta/bake `catalog.json`
2. **Web** — build `frontend/Dockerfile` target `production`, arg `VITE_API_URL`

Vedi `railway.toml` e README principale.
