# Local GND Reconciliation API

A local, OpenRefine-compatible reconciliation service for the **Gemeinsame Normdatei (GND)** using DNB GND LDS dumps, FastAPI and OpenSearch.

The service lets you reconcile names, places, corporate bodies, works, subject headings and other GND entities locally in OpenRefine. It also supports OpenRefine data extension, so you can add columns from reconciled GND values such as preferred names, variant names, life dates, affiliated bodies, places, professions, broader terms and many other GND properties.

---

## Current status

Implemented:

- Local GND LDS download and indexing pipeline
- Streaming JSON-LD import into OpenSearch
- FastAPI reconciliation service
- OpenRefine-compatible service manifest
- `GET /` and `POST /` reconciliation endpoint
- `/reconcile` compatibility aliases
- `/suggest/entity`
- `/suggest/type`
- `/suggest/property`
- `/properties`
- `/preview` and `/preview/{id}`
- `/extend` and root `POST /` data extension
- Dynamic property registry based on the public GND/lobid reconciliation API
- Dynamic property value lookup via `propertiesFlat`
- GND URI resolution for extended values
- GND vocabulary label resolution, for example geographic area codes
- Reconciled entity values in OpenRefine data extension where applicable
- Configurable data extension settings in OpenRefine:
  - `content = literal`
  - `content = id`
  - `limit`
- Runtime Docker Compose setup
- DevContainer setup
- Bootstrap script for first-run setup
- Persistent local `data/` folder
- Persistent OpenSearch index via Docker volume

Currently intentionally deferred:

- Image enrichment in previews
- EntityFacts enrichment
- OAI-PMH incremental updates
- Production-grade scoring calibration
- Automated regression test suite

---

## Architecture

```text
DNB GND LDS dumps
        ↓
Downloader
        ↓
Streaming JSON-LD parser
        ↓
Normalizer
        ↓
OpenSearch index
        ↓
FastAPI reconciliation API
        ↓
OpenRefine
```

### Main components

```text
api/
  FastAPI app and OpenRefine-compatible API endpoints

api/services/
  Search, properties, labels, vocabulary resolution and preview rendering

importer/
  Download and normalization code for GND LDS data

indexer/
  OpenSearch mapping and streaming indexer

scripts/
  Bootstrap, full indexing and container startup scripts

config/
  Local property registry and vocabulary label cache

data/
  Runtime data, logs and state files
  This directory is not versioned in git
```

---

## Data sources

The service uses the DNB GND LDS full dumps from:

```text
https://data.dnb.de/opendata/
```

The type-specific GND LDS dumps are used for:

- `person`
- `koerperschaft`
- `kongress`
- `geografikum`
- `sachbegriff`
- `werk`

For `werk`, a dated JSON-LD dump can be used if no stable undated JSON-LD link is available.

The public GND/lobid reconciliation API is used as a reference for property proposals and OpenRefine behaviour:

```text
https://reconcile.gnd.network
```

---

## Runtime data and persistence

The `data/` directory is intentionally not tracked by git.

It is created automatically on first run:

```text
data/
├── raw/
├── processed/
├── state/
└── logs/
```

### What is stored where?

```text
data/raw/
  Downloaded GND LDS dump files

data/state/gnd_state.json
  Bootstrap state and import status

data/logs/
  Bootstrap and API logs

OpenSearch Docker volume
  Actual OpenSearch index files
```

The OpenSearch index is not stored directly in the repository. It is stored in the OpenSearch Docker volume, normally mounted inside the OpenSearch container at:

```text
/usr/share/opensearch/data
```

Do not run `docker compose down -v` unless you intentionally want to delete the OpenSearch index volume.

---

## Environment configuration

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Recommended runtime values:

```env
API_PORT=8083
HOST_API_PORT=8083
PUBLIC_BASE_URL=http://127.0.0.1:8083

OPENSEARCH_HOST=opensearch
OPENSEARCH_PORT=9200
GND_INDEX_NAME=gnd

GND_AUTO_BOOTSTRAP=true
GND_FORCE_REINDEX=false
```

If port `8083` is already used, choose another host port, for example:

```env
API_PORT=8083
HOST_API_PORT=8084
PUBLIC_BASE_URL=http://127.0.0.1:8084
```

In that case OpenRefine should use:

```text
http://127.0.0.1:8084
```

---

## Running with Docker Compose

The runtime setup is intended for users who want to run the service without opening the DevContainer.

### Start

```bash
docker compose -f docker-compose.runtime.yml up --build
```

### Start in background

```bash
docker compose -f docker-compose.runtime.yml up --build -d
```

### Show logs

```bash
docker compose -f docker-compose.runtime.yml logs -f
```

Only API logs:

```bash
docker compose -f docker-compose.runtime.yml logs -f gnd-api
```

Only OpenSearch logs:

```bash
docker compose -f docker-compose.runtime.yml logs -f opensearch
```

### Stop

```bash
docker compose -f docker-compose.runtime.yml down
```

Do not use `-v` unless you want to delete the OpenSearch index volume.

---

## First startup behaviour

On startup, the container runs:

```bash
python scripts/bootstrap_gnd.py --auto
```

The bootstrap script:

1. Creates the local `data/` folders if missing
2. Waits for OpenSearch
3. Checks if the GND index exists
4. Checks `data/state/gnd_state.json`
5. If this is the first run:
   - downloads missing GND LDS dumps
   - fetches the property registry if needed
   - fetches vocabulary labels if needed
   - builds the full OpenSearch index
   - writes bootstrap state
6. If the index is already initialized:
   - skips full setup
   - starts the API immediately

Expected log line after a completed full import:

```text
State written. Indexed documents: 10,197,852
```

The exact number can vary depending on the dump version and normalization logic.

---

## Forcing a reindex

To force a full reindex on next start, set in `.env`:

```env
GND_FORCE_REINDEX=true
```

Then run:

```bash
docker compose -f docker-compose.runtime.yml down
docker compose -f docker-compose.runtime.yml up --build
```

After successful reindexing, set it back to:

```env
GND_FORCE_REINDEX=false
```

---

## DevContainer workflow

The DevContainer is still useful for development.

Open the project in VS Code and run:

```text
Dev Containers: Reopen in Container
```

The DevContainer can use:

```json
"postStartCommand": "bash scripts/start_dev_services.sh"
```

This starts bootstrap checks and runs FastAPI with reload support.

---

## Manual commands

### Check bootstrap state

```bash
python scripts/bootstrap_gnd.py --check-only
```

### Run automatic bootstrap

```bash
python scripts/bootstrap_gnd.py --auto
```

### Run explicit initialization

```bash
python scripts/bootstrap_gnd.py --init
```

### Test initialization with limit per source

```bash
python scripts/bootstrap_gnd.py --init --limit 1000
```

### Download all GND LDS dumps

```bash
python -m importer.download_gnd_lds --source all
```

### Download one source

```bash
python -m importer.download_gnd_lds --source person
python -m importer.download_gnd_lds --source sachbegriff
python -m importer.download_gnd_lds --source geografikum
```

### Index all sources

```bash
python scripts/index_all_gnd_lds.py
```

### Index all sources with a test limit

```bash
python scripts/index_all_gnd_lds.py --limit 1000
```

### Index all sources except persons

```bash
python scripts/index_all_gnd_lds.py --skip-person
```

---

## OpenRefine setup

Start OpenRefine and add the reconciliation service:

```text
Column menu
→ Reconcile
→ Start reconciling
→ Add Standard Service
```

Service URL:

```text
http://127.0.0.1:8083
```

If you use a different host port, for example `8084`, use:

```text
http://127.0.0.1:8084
```

Do not append `/reconcile`.

Correct:

```text
http://127.0.0.1:8083
```

Incorrect:

```text
http://127.0.0.1:8083/reconcile
```

---

## Recommended OpenRefine workflow

Example input data:

```csv
name
Goethe
Mark Twain
Mozart
Berlin
Abakus
Deutsche Nationalbibliothek
Don Giovanni
```

Use a suitable type in OpenRefine where possible:

```text
Person
Place or Geographic Name
Corporate Body
Subject Heading
Work
```

For ambiguous values such as `Goethe`, `Berlin`, `Paris` or `Mozart`, type selection and detail columns improve results significantly.

---

## Use values as identifiers

OpenRefine's **Use values as identifiers...** can be used if a column already contains GND IDs such as:

```text
118540238
118624822
4000030-8
```

After using values as identifiers, you can add columns from reconciled values.

Important: this workflow assumes values are valid identifiers. It is not a full reconciliation search.

Useful checks:

```bash
curl "http://localhost:8083/preview?id=118540238"
```

```bash
curl -X POST "http://localhost:8083/"   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode 'extend={"ids":["118540238"],"properties":[{"id":"preferredName"}]}'
```

---

## Data extension

After reconciliation in OpenRefine:

```text
Edit column
→ Add columns from reconciled values
```

The local API supports:

- dynamic property proposals
- property suggestions
- configurable data extension settings
- ID or literal output
- value limits
- GND URI resolution
- GND vocabulary label resolution
- reconciled entity values for GND entity references where applicable

Example:

```bash
curl -X POST "http://localhost:8083/"   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode 'extend={"ids":["118624822"],"properties":[{"id":"preferredName"},{"id":"variantName"},{"id":"dateOfBirth"},{"id":"dateOfDeath"}]}'
```

### Configure options in OpenRefine

The manifest exposes property settings for data extension:

```text
Content:
  literal
  id

Limit:
  maximum number of returned values
```

`content = literal` returns readable values where possible.

`content = id` returns stored identifiers or URI-like values.

---

## Property registry

The local API can mirror the property suggestions of the public GND reconciliation API.

Run:

```bash
python scripts/fetch_gnd_property_registry.py
```

This creates:

```text
config/gnd_properties.json
```

Used by:

```text
/properties
/suggest/property
```

---

## Vocabulary labels

Controlled GND vocabulary values, for example geographic area codes, can be resolved locally.

Run:

```bash
python scripts/fetch_gnd_vocab_labels.py
```

This creates:

```text
config/gnd_vocab_labels.json
```

Example conversion:

```text
https://d-nb.info/standards/vocab/gnd/geographic-area-code#XA-AT
→ Österreich (XA-AT)
```

---

## Preview

The preview is implemented in:

```text
api/services/preview.py
```

The preview is generic and type-aware.

It supports:

- broad type detection
- different field profiles for:
  - Person
  - CorporateBody
  - ConferenceOrEvent
  - PlaceOrGeographicName
  - SubjectHeading
  - Work
- GND URI label resolution
- GND vocabulary label resolution
- clickable links
- readable literals

Image display is currently optional and not a core feature. It will only render if image-like properties are available in the local index. Image enrichment is deferred for a later EntityFacts enrichment step.

Preview endpoints:

```text
/preview?id=<gnd_id>
/preview/<gnd_id>
```

Example:

```bash
curl "http://localhost:8083/preview?id=1036893200"
```

---

## Reconciliation scoring

The scoring currently combines:

- exact identifier matches
- preferred name matches
- variant name matches
- token overlap
- substring matches
- OpenSearch fallback score
- optional type bonus
- optional property/detail-column bonus from OpenRefine

OpenRefine's option:

```text
Also use relevant details from other columns
```

is supported by reading reconciliation query `properties` and applying a generic property-matching bonus against top-level fields and `propertiesFlat`.

The scoring is still under active tuning. Some score distributions can still differ from the public GND/lobid API.

---

## API examples

### Service manifest

```bash
curl http://localhost:8083/
```

### Reconcile GET

```bash
curl "http://localhost:8083/reconcile?query=Goethe"
```

### Reconcile POST

```bash
curl -X POST "http://localhost:8083/"   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode 'queries={"q1":{"query":"Goethe","type":"Person"}}'
```

### Reconcile POST with detail properties

```bash
curl -X POST "http://localhost:8083/"   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode 'queries={"q1":{"query":"Goethe","type":"Person","properties":[{"pid":"dateOfBirth","v":"1749"},{"pid":"dateOfDeath","v":"1832"}]}}'
```

### Suggest entity

```bash
curl "http://localhost:8083/suggest/entity?prefix=Goethe"
```

### Suggest type

```bash
curl "http://localhost:8083/suggest/type?prefix=Person"
```

### Suggest property

```bash
curl "http://localhost:8083/suggest/property?prefix=beruf"
```

### Property proposals

```bash
curl "http://localhost:8083/properties?type=Person&limit=50"
```

### Extend

```bash
curl -X POST "http://localhost:8083/"   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode 'extend={"ids":["118540238"],"properties":[{"id":"preferredName"},{"id":"dateOfBirth"},{"id":"dateOfDeath"}]}'
```

### Extend with settings

```bash
curl -X POST "http://localhost:8083/"   -H "Content-Type: application/x-www-form-urlencoded"   --data-urlencode 'extend={"ids":["118540238"],"properties":[{"id":"geographicAreaCode","settings":{"content":"literal","limit":"1"}}]}'
```

---

## Checking the index

If OpenSearch is exposed to the host:

```bash
curl "http://localhost:9200/gnd/_count?pretty"
```

If OpenSearch is only available inside Docker Compose:

```bash
docker compose -f docker-compose.runtime.yml exec gnd-api   curl "http://opensearch:9200/gnd/_count?pretty"
```

Index size and document count:

```bash
curl "http://localhost:9200/_cat/indices/gnd?v&h=index,docs.count,store.size"
```

Type distribution:

```bash
curl "http://localhost:9200/gnd/_search?pretty"   -H "Content-Type: application/json"   -d '{
    "size": 0,
    "aggs": {
      "types": {
        "terms": {
          "field": "type",
          "size": 100
        }
      }
    }
  }'
```

---

## Troubleshooting

### Port 9200 already allocated

Error:

```text
Bind for 0.0.0.0:9200 failed: port is already allocated
```

Cause: another OpenSearch container is already using host port `9200`.

Fix options:

- stop the other OpenSearch container
- remove the host port mapping for OpenSearch in the runtime Compose file
- map OpenSearch to another host port, for example `9201:9200`

The API only needs internal Compose access to:

```text
opensearch:9200
```

### Port 8083 already allocated

Use another host port in `.env`:

```env
API_PORT=8083
HOST_API_PORT=8084
PUBLIC_BASE_URL=http://127.0.0.1:8084
```

Then connect OpenRefine to:

```text
http://127.0.0.1:8084
```

### Preview points to the wrong port

Check the manifest:

```bash
curl http://localhost:8083/
```

Ensure `PUBLIC_BASE_URL` matches the host URL used by OpenRefine.

If the port changed, remove and re-add the reconciliation service in OpenRefine.

### OpenRefine preview shows old content

OpenRefine can cache service metadata.

Remove the service and add it again:

```text
http://127.0.0.1:8083
```

### Runtime code changes not visible

The runtime Docker image copies source code into the image. After code changes, rebuild:

```bash
docker compose -f docker-compose.runtime.yml down
docker compose -f docker-compose.runtime.yml up --build
```

### Data extension returns URIs instead of labels

Check whether the target entity exists in the local index:

```bash
docker compose -f docker-compose.runtime.yml exec gnd-api   curl "http://opensearch:9200/gnd/_doc/<GND_ID>?pretty"
```

If the target exists, URI resolution should normally return a readable label.

For vocabulary values, ensure the vocabulary cache exists:

```text
config/gnd_vocab_labels.json
```

---

## Update strategy

Currently implemented:

```text
Initial full import
Bootstrap state detection
Reusing existing dumps and index across restarts
Manual forced full reindex
```

Planned:

```text
Remote dump update detection
Interactive update confirmation
Shadow index strategy
OAI-PMH / GND change service incremental updates
Redirect/deletion handling
```

The long-term goal is to avoid full reindexing when only incremental changes are available.

---

## Future work

Planned improvements:

- Better scoring calibration against the public GND/lobid API
- Regression tests for common reconciliation cases
- EntityFacts enrichment
- Better preview enrichment
- Optional image support via enriched sources
- OAI-PMH incremental update harvesting
- Redirect and deletion handling
- Shadow-index updates with alias switching
- Packaged Docker release for simple reuse by other users

---

## Useful files

```text
api/main.py
  FastAPI routes and service manifest

api/services/search.py
  OpenSearch queries, scoring and result formatting

api/services/properties.py
  Dynamic property values and proposals

api/services/property_registry.py
  Local mirrored GND property registry

api/services/property_labels.py
  Human-readable labels for properties

api/services/vocab_resolver.py
  GND vocabulary URI label resolution

api/services/preview.py
  Generic type-aware preview rendering

importer/download_gnd_lds.py
  GND LDS dump downloader

importer/normalize_gnd_lds.py
  JSON-LD normalization

indexer/index_gnd_lds.py
  OpenSearch index creation and streaming import

scripts/bootstrap_gnd.py
  First-run setup and state handling

scripts/index_all_gnd_lds.py
  Full indexing workflow for all sources

scripts/start_dev_services.sh
  DevContainer startup helper

scripts/start_container_services.sh
  Runtime container startup helper
```

---

## References

- DNB Open Data: `https://data.dnb.de/opendata/`
- Public GND Reconciliation Service: `https://reconcile.gnd.network`
- OpenRefine Reconciliation API documentation: `https://openrefine.org/docs/technical-reference/reconciliation-api`
- Reconciliation Service API v0.2: `https://www.w3.org/community/reports/reconciliation/CG-FINAL-specs-0.2-20230410/`
- GND Geographic Area Codes: `https://d-nb.info/standards/vocab/gnd/geographic-area-code`