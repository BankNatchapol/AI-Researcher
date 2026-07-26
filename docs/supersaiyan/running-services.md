# Running the local services

PostgreSQL 16 and GROBID run through Docker Compose. Both services use native
`linux/arm64` images on Apple Silicon.

## Start

Create the local environment file once, then start the stack:

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

Wait until both `postgres` and `grobid` report `healthy`. Confirm each service directly:

```bash
curl -sf http://localhost:8070/api/isalive
psql "$DATABASE_URL" -c "select 1"
```

The GROBID request prints `true`; the PostgreSQL query returns one row containing `1`.

## Stop

Stop and remove the containers while preserving the database:

```bash
docker compose down
```

PostgreSQL data remains in the named volume `ai-researcher-postgres-data`.

## Reset

To remove all local PostgreSQL data and return to a clean slate:

```bash
docker compose down --volumes
```

This permanently removes the `ai-researcher-postgres-data` volume. The next
`docker compose up -d` creates an empty database.
