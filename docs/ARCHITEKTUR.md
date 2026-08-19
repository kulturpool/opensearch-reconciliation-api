# Architektur

Dieses Dokument beschreibt den Aufbau, die Komponenten und den Datenfluss des GND Reconciliation API Projekts.

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Systemkontext](#systemkontext)
3. [Komponenten](#komponenten)
4. [Datenfluss: Bootstrap / Erstindexierung](#datenfluss-bootstrap--erstindexierung)
5. [Datenfluss: Reconciliation Query](#datenfluss-reconciliation-query)
6. [Datenfluss: Wöchentliche OAI-Updates](#datenfluss-wöchentliche-oai-updates)
7. [Persistenz](#persistenz)
8. [Deployment-Modi](#deployment-modi)
9. [Konfiguration](#konfiguration)

---

## Überblick

Der Service ist ein lokaler, Docker-basierter Reconciliation-Service für die **Gemeinsame Normdatei (GND)**. Er kombiniert:

- einen einmaligen/inkrementellen **Import- und Indexierungsprozess** (GND-LDS-Dumps + EntityFacts-Enrichment),
- einen **OpenSearch-Index** als persistenten Suchindex,
- eine **FastAPI-Anwendung**, die eine OpenRefine-kompatible [Reconciliation API](https://reconciliation-api.github.io/specs/latest/) bereitstellt,
- einen **Scheduler**, der den Index über OAI-PMH inkrementell aktuell hält.

---

## Systemkontext

```mermaid
flowchart LR
    User(["Nutzer:in"]) -->|CSV/TSV/Excel-Spalten reconciliaten| OpenRefine["OpenRefine"]
    OpenRefine -->|HTTP: queries / extend / preview / suggest| API["GND Reconciliation API\n(FastAPI, Port 8083)"]
    API -->|_msearch / _search / _count| OpenSearch[("OpenSearch\nIndex: gnd")]
    Scheduler["OAI Update Scheduler\n(Background Thread)"] -->|Bulk Upsert| OpenSearch
    Scheduler -->|ListRecords| DNB_OAI["DNB OAI-PMH Repository"]
    Bootstrap["Bootstrap / Importer / Indexer\n(einmalig bzw. --force-reindex)"] -->|Bulk Index| OpenSearch
    Bootstrap -->|Download GND-LDS Dumps| DNB_LDS["DNB GND-LDS Dumps"]
    Bootstrap -->|Enrichment| EntityFacts["DNB EntityFacts API"]
```

Der Service läuft vollständig lokal (Docker Compose). Externe Abhängigkeiten bestehen nur zur DNB (GND-LDS-Dumps, EntityFacts, OAI-PMH), nicht zu Drittanbietern.

---

## Komponenten

| Komponente | Pfad | Verantwortung |
|---|---|---|
| FastAPI-App | [api/main.py](../api/main.py) | Route-Definitionen, Service-Manifest, Request-Dispatch |
| Konstanten/Typen | [api/constants.py](../api/constants.py), [api/gnd_types.py](../api/gnd_types.py) | GND-Entitätstypen, unterstützte Properties |
| Reconciliation-Orchestrierung | [api/reconciliation_utils.py](../api/reconciliation_utils.py) | Batch-Aufbereitung der Queries, Timing-Logs |
| OpenSearch-Integration | [api/services/search.py](../api/services/search.py) | Query-Body-Aufbau, `_msearch`-Batching, Scoring |
| Property-Matching | [api/services/property_matching.py](../api/services/property_matching.py) | Generischer Property-Bonus/Penalty |
| Property Registry | [api/services/property_registry.py](../api/services/property_registry.py), [config/gnd_properties.json](../config/gnd_properties.json) | Bekannte GND-Properties inkl. Labels |
| Property Labels | [api/services/property_labels.py](../api/services/property_labels.py) | Auflösung von Property-IDs zu menschenlesbaren Labels |
| Extend API | [api/services/properties.py](../api/services/properties.py) | „Add columns from reconciled values" |
| Preview | [api/services/preview.py](../api/services/preview.py) | HTML-Vorschau für OpenRefine |
| Vocab Resolver | [api/services/vocab_resolver.py](../api/services/vocab_resolver.py), [config/gnd_vocab_labels.json](../config/gnd_vocab_labels.json) | Auflösung von RDF-Vokabular-URIs zu Labels |
| Zentrale Konfiguration | [config/\_\_init\_\_.py](../config/__init__.py) | Liest Environment-Variablen (`.env`), stellt Konstanten für den Rest der App bereit |
| Importer | [importer/](../importer/) | Download der GND-LDS-Dumps, Normalisierung (GND-LDS + EntityFacts) |
| Indexer | [indexer/](../indexer/) | Bulk-Indexierung/Upsert in OpenSearch |
| Scripts | [scripts/](../scripts/) | Bootstrap-Orchestrierung, OAI-Harvesting, Update-Scheduler, Container-Startup |

---

## Datenfluss: Bootstrap / Erstindexierung

```mermaid
sequenceDiagram
    participant SH as start_container_services.sh
    participant BS as bootstrap_gnd.py
    participant IM as importer/download_gnd_lds.py
    participant NM as importer/normalize_gnd_lds.py
    participant IX as indexer/index_gnd_lds.py
    participant EF as scripts/enrich_with_entityfacts.py
    participant OS as OpenSearch

    SH->>BS: python scripts/bootstrap_gnd.py --auto
    BS->>IM: GND-LDS-Dumps herunterladen (falls nötig)
    BS->>NM: Rohdaten normalisieren
    BS->>IX: Bulk-Index in OpenSearch
    IX->>OS: Index "gnd" anlegen/befüllen
    BS->>EF: EntityFacts-Enrichment (Family, sameAs, depiction, ...)
    EF->>OS: Bulk-Update bestehender Dokumente
    BS-->>SH: index_complete.marker schreiben
    SH->>SH: API + Update-Scheduler starten
```

`GND_FORCE_REINDEX=false` und ein vorhandenes `data/state/index_complete.marker` überspringen diesen kompletten Ablauf beim Container-Start (siehe [docs/ENTWICKLUNG.md](ENTWICKLUNG.md)).

---

## Datenfluss: Reconciliation Query

```mermaid
sequenceDiagram
    participant OR as OpenRefine
    participant API as api/main.py
    participant RU as reconciliation_utils.py
    participant SE as services/search.py
    participant OS as OpenSearch

    OR->>API: POST / (queries={...}, ggf. 40.000+ Zeilen als Batches)
    API->>RU: handle_reconciliation_queries(queries)
    RU->>SE: search_gnd_batch(queries)
    SE->>OS: ein einziger _msearch-Request für den ganzen Batch
    OS-->>SE: Kandidaten je Query (reduzierte _source-Felder)
    SE->>SE: normalize_score() + score_date_signals() + calculate_property_bonus()
    SE-->>RU: bewertete/sortierte Kandidaten
    RU-->>API: Ergebnisse je Query-ID
    API-->>OR: JSON-Response (results, match, score)
    RU->>RU: Log: batch_size, properties, total_ms, opensearch_ms, postprocessing_ms
```

Wichtige Design-Entscheidung: **ein** `_msearch`-Request pro Batch statt eines `search_gnd()`-Aufrufs pro Zeile – das war der wesentliche Performance-Hebel für große OpenRefine-Batches. Details zum Scoring stehen im Abschnitt "Performance & Scoring" der [README.md](../README.md).

---

## Datenfluss: Tägliche/Wöchentliche OAI-Updates

```mermaid
sequenceDiagram
    participant SC as scripts/update_scheduler.py
    participant HV as scripts/harvest_gnd_oai.py
    participant UP as indexer/upsert_oai_records.py
    participant DNB as DNB OAI-PMH Repository
    participant OS as OpenSearch

    loop alle GND_UPDATE_INTERVAL_HOURS
        SC->>SC: update.lock anlegen (mit Staleness-Check)
        SC->>HV: ListRecords seit last_oai_harvest
        HV->>DNB: OAI-PMH Request (RDFxml)
        DNB-->>HV: geänderte/gelöschte Records
        HV->>UP: normalisierte Records
        UP->>OS: Bulk-Upsert (kein vollständiger Reindex)
        SC->>SC: data/state/update_state.json aktualisieren
        SC->>SC: update.lock entfernen (finally)
    end
```

Der Scheduler läuft als Hintergrund-Thread im selben Container wie die API (kein separater Service). `update.lock` wird als veraltet erkannt und entfernt, wenn er älter als `GND_UPDATE_LOCK_STALE_SECONDS` ist (Schutz gegen verwaiste Locks nach Container-Abbruch).

---

## Persistenz

| Pfad | Inhalt | Git-Status |
|---|---|---|
| `data/raw/` | Heruntergeladene GND-LDS- und EntityFacts-Dumps | ignoriert |
| `data/processed/` | Normalisierte Zwischendaten | ignoriert |
| `data/state/` | Bootstrap-/Update-/Lock-Status (`index_state.json`, `update_state.json`, `*.lock`, `*.marker`) | ignoriert |
| `data/logs/` | Anwendungs- und Scheduler-Logs | ignoriert |
| `data/opensearch/` bzw. OpenSearch Docker Volume | Eigentlicher Suchindex | Volume, nicht in Git |
| `config/gnd_properties.json`, `config/gnd_vocab_labels.json` | Gecachte Registries/Labels | versioniert |

Runtime- und DevContainer-Modus teilen sich dasselbe OpenSearch-Volume (`local_reconciliation_api_opensearch-data`) – beide dürfen nicht gleichzeitig laufen.

---

## Deployment-Modi

- **Production/Runtime** ([docker-compose.runtime.yml](../docker-compose.runtime.yml), [Dockerfile](../Dockerfile)): Multi-Stage-Build, Code wird ins Image kopiert, minimaler Footprint, Healthcheck gegen `/status/update`.
- **DevContainer** ([.devcontainer/](../.devcontainer/)): Workspace live gemountet, Hot-Reload via `uvicorn --reload`, zusätzliche Entwickler-Tools.

Details und Umschaltprozess: [docs/ENTWICKLUNG.md](ENTWICKLUNG.md) sowie [.devcontainer/README.md](../.devcontainer/README.md).

---

## Konfiguration

Sämtliche Environment-Variablen (OpenSearch-Verbindung, Update-Intervalle, OAI-Endpunkt, Ports) werden zentral in [config/\_\_init\_\_.py](../config/__init__.py) aus `.env` gelesen und von dort in den Rest der Anwendung importiert – siehe `.env.example` für die vollständige Liste mit Standardwerten.
