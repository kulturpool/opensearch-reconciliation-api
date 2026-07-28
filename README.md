# Local GND Reconciliation API

Lokaler OpenRefine-kompatibler Reconciliation Service für die Gemeinsame Normdatei (GND) auf Basis der DNB-GND-LDS-Gesamtabzüge und OpenSearch.

Das Projekt stellt eine lokale Reconciliation API bereit, die mit OpenRefine verwendet werden kann, um Namen, Orte, Körperschaften, Werke, Sachbegriffe und weitere GND-Entitäten gegen einen lokal indexierten GND-Bestand abzugleichen.

Die API orientiert sich an der Reconciliation Service API v0.2, die von OpenRefine unterstützt wird. Die Spezifikation sieht unter anderem ein Service Manifest, Reconciliation Queries, Suggest Services, Preview und Data Extension vor.

---

## Features

- Lokaler GND-Reconciliation-Service für OpenRefine
- FastAPI-basierte Reconciliation API
- OpenSearch als lokaler Suchindex
- Streaming-Import der DNB-GND-LDS-Dumps
- Unterstützung typgetrennter GND-Gesamtabzüge:
  - Personen
  - Körperschaften
  - Konferenzen/Ereignisse
  - Geografika
  - Sachbegriffe
  - Werke
- OpenRefine-kompatible Endpunkte:
  - `GET /`
  - `POST /`
  - `GET /reconcile`
  - `POST /reconcile`
  - `GET /suggest/entity`
  - `GET /suggest/type`
  - `GET /suggest/property`
  - `GET /properties`
  - `GET /preview/{gnd_id}`
  - `GET /extend`
  - `POST /extend`
- Automatischer Bootstrap beim Containerstart
- Runtime-Vorbereitung für späteres `docker compose up`
- Persistente OpenSearch-Indizes via Docker Volume
- Lokale Property Registry auf Basis der öffentlichen GND-Reconciliation API
- Lokale Vokabularauflösung, z.B. für GND Geographic Area Codes

---

## Datenquellen

Die GND-LDS-Daten werden von der Deutschen Nationalbibliothek unter folgender Adresse bereitgestellt:

```text
https://data.dnb.de/opendata/
```

Dort finden sich typgetrennte GND-Gesamtabzüge für Personen, Körperschaften, Kongresse, Geografika, Sachbegriffe und Werke sowie weitere RDF-Serialisierungen.

Dieses Projekt verwendet primär die typgetrennten GND-LDS-Dateien im JSON-LD-Format, soweit verfügbar. Für Werke kann aktuell ein datierter JSON-LD-Abzug verwendet werden, falls kein stabiler undatierter JSON-LD-Link verfügbar ist.

Die öffentliche GND-Reconciliation API von lobid/GND dient als funktionale Referenz für OpenRefine-Integration, Property-Proposals, Suggest-Endpunkte und Extend-Verhalten:

```text
https://reconcile.gnd.network
```

---

## Architektur

```text
DNB GND LDS Dumps
        ↓
Downloader
        ↓
Streaming JSON-LD Parser
        ↓
Normalizer
        ↓
OpenSearch Index
        ↓
FastAPI Reconciliation API
        ↓
OpenRefine
```

### Komponenten

```text
api/
  FastAPI App und OpenRefine-kompatible API-Endpunkte

importer/
  Downloader, Inspector und Normalisierung der GND-LDS-Daten

indexer/
  OpenSearch-Mapping und Streaming-Indexer

scripts/
  Bootstrap, Gesamtindexierung, Runtime-Startscripts

config/
  Property Registry und Vokabular-Labels

data/
  Lokale Rohdaten, Logs und State-Dateien
  Wird nicht versioniert
```

---

## Voraussetzungen

Für die Entwicklung:

- Docker
- Docker Compose
- VS Code mit Dev Containers Erweiterung
- OpenRefine lokal oder separat gestartet
- Ausreichend Speicherplatz für GND-Dumps und OpenSearch-Index

Für den vollständigen GND-Import sollte ausreichend Speicherplatz vorhanden sein. Der GND-Gesamtbestand ist groß und kann mehrere Stunden Importzeit und mehrere GB Speicherplatz benötigen.

---

## Start im DevContainer

### 1. Repository öffnen

```bash
code .
```

Dann in VS Code:

```text
Dev Containers: Reopen in Container
```

Der DevContainer startet die Entwicklungsumgebung sowie OpenSearch.

---

### 2. Automatischer Start

Beim Start des DevContainers kann automatisch folgendes ausgeführt werden:

```json
"postStartCommand": "bash scripts/start_dev_services.sh"
```

Das Script führt aus:

```text
1. data/ Ordner erstellen
2. Bootstrap prüfen
3. GND-Index initialisieren, falls notwendig
4. FastAPI auf Port 8083 starten
```

Danach ist die API erreichbar unter:

```text
http://127.0.0.1:8083
```

---

## Manuelle Initialisierung

Falls du den Bootstrap manuell ausführen möchtest:

```bash
python scripts/bootstrap_gnd.py --check-only
```

Initialisierung nur wenn nötig:

```bash
python scripts/bootstrap_gnd.py --auto
```

Explizite Initialisierung:

```bash
python scripts/bootstrap_gnd.py --init
```

Testinitialisierung mit Limit pro Quelle:

```bash
python scripts/bootstrap_gnd.py --init --limit 1000
```

---

## GND-Daten herunterladen

Alle konfigurierten GND-LDS-Quellen herunterladen:

```bash
python -m importer.download_gnd_lds --source all
```

Einzelne Quelle herunterladen:

```bash
python -m importer.download_gnd_lds --source person
python -m importer.download_gnd_lds --source sachbegriff
python -m importer.download_gnd_lds --source geografikum
```

Die Dateien werden nach `data/raw/` geschrieben.

---

## Gesamten GND-Index aufbauen

Alle GND-LDS-Quellen in einen gemeinsamen OpenSearch-Index importieren:

```bash
python scripts/index_all_gnd_lds.py
```

Testlauf mit Limit pro Quelle:

```bash
python scripts/index_all_gnd_lds.py --limit 1000
```

Ohne Personenbestand testen:

```bash
python scripts/index_all_gnd_lds.py --skip-person
```

Der erste Import erstellt den Index neu. Danach werden die weiteren Quellen in denselben Index importiert.

---

## FastAPI starten

Im DevContainer:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8083 --reload --access-log
```

Oder automatisch über:

```bash
bash scripts/start_dev_services.sh
```

API testen:

```bash
curl http://localhost:8083/
```

Reconciliation testen:

```bash
curl "http://localhost:8083/reconcile?query=Goethe"
```

OpenRefine-kompatibler POST-Test:

```bash
curl -X POST "http://localhost:8083/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'queries={"q1":{"query":"Goethe","type":"Person"}}'
```

---

## OpenRefine-Anbindung

In OpenRefine:

```text
Column
→ Reconcile
→ Start reconciling
→ Add Standard Service
```

Service URL:

```text
http://127.0.0.1:8083
```

Wichtig: Nicht `/reconcile` anhängen. Die Reconciliation API erwartet, dass der Service-Endpoint selbst ein Manifest liefert und POST-Queries am Basis-Endpunkt verarbeiten kann.

---

## Beispiel-Testdaten

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

Je nach Spaltentyp sollte in OpenRefine ein passender GND-Typ gewählt werden:

```text
Person
Place or Geographic Name
Corporate Body
Subject Heading
Work
```

---

## OpenRefine Data Extension

Nach erfolgreicher Reconciliation können zusätzliche Spalten erzeugt werden über:

```text
Edit column
→ Add columns from reconciled values
```

Die Property-Liste wird lokal aus einer Property Registry bereitgestellt, die von der öffentlichen GND-Reconciliation API gespiegelt werden kann.

Beispiel via curl:

```bash
curl -X POST "http://localhost:8083/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'extend={"ids":["118624822"],"properties":[{"id":"preferredName"},{"id":"variantName"},{"id":"dateOfBirth"},{"id":"dateOfDeath"}]}'
```

---

## Lokale Property Registry aktualisieren

Die Property Registry kann aus der öffentlichen GND-Reconciliation API erzeugt werden:

```bash
python scripts/fetch_gnd_property_registry.py
```

Die Ausgabe liegt unter:

```text
config/gnd_properties.json
```

Diese Datei wird von den lokalen Endpunkten verwendet:

```text
/properties
/suggest/property
```

---

## GND-Vokabularlabels aktualisieren

Für kontrollierte GND-Vokabulare wie Geographic Area Codes kann ein lokaler Label-Cache erzeugt werden:

```bash
python scripts/fetch_gnd_vocab_labels.py
```

Die Ausgabe liegt unter:

```text
config/gnd_vocab_labels.json
```

Damit werden Werte wie:

```text
https://d-nb.info/standards/vocab/gnd/geographic-area-code#XA-DE
```

lokal in lesbare Labels wie:

```text
Deutschland (XA-DE)
```

aufgelöst.

---

## Runtime Docker Setup

Neben dem DevContainer gibt es eine vorbereitete Runtime-Variante.

### Build und Start

```bash
cp .env.example .env
docker compose -f docker-compose.runtime.yml up --build
```

Danach ist die API erreichbar unter:

```text
http://localhost:8083
```

### Hintergrundstart

```bash
docker compose -f docker-compose.runtime.yml up -d
```

Logs anzeigen:

```bash
docker compose -f docker-compose.runtime.yml logs -f
```

Stoppen:

```bash
docker compose -f docker-compose.runtime.yml down
```

Wichtig: Nicht `-v` verwenden, wenn die OpenSearch-Indexdaten erhalten bleiben sollen.

---

## Persistenz

### Rohdaten

Die heruntergeladenen GND-Dumps liegen unter:

```text
data/raw/
```

### Bootstrap-State

```text
data/state/gnd_state.json
```

### Logs

```text
data/logs/
```

### OpenSearch-Index

Der OpenSearch-Index liegt nicht im Projektordner, sondern im Docker Volume des OpenSearch-Containers:

```text
/usr/share/opensearch/data
```

Je nach Compose-Konfiguration wird dieses Verzeichnis über ein Docker Volume wie `opensearch-data` persistiert.

---

## Index prüfen

Dokumentanzahl:

```bash
curl "http://opensearch:9200/gnd/_count?pretty"
```

Indexgröße:

```bash
curl "http://opensearch:9200/_cat/indices/gnd?v&h=index,docs.count,store.size"
```

Typverteilung:

```bash
curl "http://opensearch:9200/gnd/_search?pretty" \
  -H "Content-Type: application/json" \
  -d '{
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

## Update-Strategie

Aktuell unterstützt das Projekt:

```text
Initialer Full Import
Bootstrap-Check
Wiederverwendung bestehender Daten und Indizes
```

Ein zukünftiger Schritt ist die Unterstützung inkrementeller Updates über den DNB-GND-Änderungsdienst bzw. die DNB-OAI-Schnittstelle.

Geplante Skripte:

```text
scripts/check_gnd_updates.py
scripts/harvest_gnd_oai.py
scripts/update_gnd.py
```

---

## Troubleshooting

### Port 9200 ist bereits belegt

Fehler:

```text
Bind for 0.0.0.0:9200 failed: port is already allocated
```

Ursache: Ein anderer OpenSearch-Container läuft bereits.

Lösung: Im Runtime-Compose den OpenSearch-Port nicht nach außen veröffentlichen oder einen anderen Host-Port nutzen:

```yaml
ports:
  - "9201:9200"
```

Für die API reicht die interne Adresse:

```text
opensearch:9200
```

---

### Port 8083 ist belegt

Prüfen:

```bash
lsof -i :8083
```

Oder laufende Uvicorn-Prozesse anzeigen:

```bash
pgrep -af "uvicorn api.main:app"
```

Beenden:

```bash
pkill -f "uvicorn api.main:app"
```

---

### Service in OpenRefine nicht erreichbar

Prüfen:

```bash
curl http://localhost:8083/
```

Wenn das funktioniert, aber OpenRefine nicht:

- VS Code Port Forwarding prüfen
- OpenRefine-Service-URL `http://127.0.0.1:8083` verwenden
- Falls OpenRefine in Docker läuft, ggf. `host.docker.internal` verwenden

---

### OpenRefine meldet 405 Method Not Allowed

Dann fehlt wahrscheinlich `POST /`.

Die Reconciliation API erwartet, dass Reconciliation Queries per `POST` am Service-Endpunkt mit Form-Feld `queries` unterstützt werden.

---

### Reconciled values liefern URLs statt Labels

Normale GND-URIs wie:

```text
https://d-nb.info/gnd/1008453-8
```

werden gegen den lokalen Index aufgelöst.

GND-Vokabularwerte wie:

```text
https://d-nb.info/standards/vocab/gnd/geographic-area-code#XA-DE
```

werden über `config/gnd_vocab_labels.json` aufgelöst.

Wenn ein Link weiterhin nicht aufgelöst wird, ist der referenzierte Datensatz eventuell nicht lokal indexiert oder gehört zu einem anderen Vokabular.

---

## Entwicklung

### Wichtige Scripts

```bash
python scripts/bootstrap_gnd.py --check-only
python scripts/bootstrap_gnd.py --auto
python scripts/bootstrap_gnd.py --init
python scripts/index_all_gnd_lds.py
python scripts/fetch_gnd_property_registry.py
python scripts/fetch_gnd_vocab_labels.py
bash scripts/start_dev_services.sh
bash scripts/start_container_services.sh
```

### API lokal starten

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8083 --reload --access-log
```

---

## Projektstatus

Aktuell implementiert:

- Lokaler GND-LDS-Import
- OpenSearch-Index
- OpenRefine-kompatible Reconciliation API
- Vorschläge für Entitäten, Typen und Properties
- Preview
- Data Extension
- Lokale Property Registry
- Vokabular-Label-Auflösung
- DevContainer-Automatisierung
- Runtime-Docker-Vorbereitung

In Arbeit / geplant:

- Scoring-Verbesserungen
- Regressionstests für Matching-Qualität
- OAI-PMH-basierte inkrementelle Updates
- Shadow-Index-Strategie für Zero-Downtime-Reindexing
- Bessere EntityFacts-Anreicherung für Preview und Extend

---

## Referenzen

- DNB Open Data: https://data.dnb.de/opendata/
- GND Reconciliation Service: https://reconcile.gnd.network
- OpenRefine Reconciliation API: https://openrefine.org/docs/technical-reference/reconciliation-api
- Reconciliation Service API v0.2: https://www.w3.org/community/reports/reconciliation/CG-FINAL-specs-0.2-20230410/
- GND Geographic Area Codes: https://d-nb.info/standards/vocab/gnd/geographic-area-code
