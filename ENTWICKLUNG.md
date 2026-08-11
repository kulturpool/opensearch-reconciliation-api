# Entwicklungshandbuch

Dieses Dokument beschreibt die Entwicklungsumgebung und Best Practices für die Arbeit am GND Reconciliation API Projekt.

---

## Inhaltsverzeichnis

1. [Entwicklungsumgebung einrichten](#entwicklungsumgebung-einrichten)
2. [Projektstruktur](#projektstruktur)
3. [Code-Qualität](#code-qualität)
4. [Testing](#testing)
5. [Debugging](#debugging)
6. [Häufige Entwicklungsaufgaben](#häufige-entwicklungsaufgaben)
7. [Best Practices](#best-practices)

---

## Entwicklungsumgebung einrichten

### Option 1: DevContainer (empfohlen)

**Vorteile**:
- ✅ Konsistente Umgebung für alle Entwickler
- ✅ Keine lokale Python-Installation nötig
- ✅ Automatische Konfiguration
- ✅ VS Code Extensions vorinstalliert

**Voraussetzungen**:
- VS Code mit Extension **Dev Containers** installieren
- Docker und Docker Compose

**Setup**:
```bash
# Repository klonen
git clone <REPOSITORY_URL>
cd <REPOSITORY_NAME>

# In VS Code öffnen
code .

# Command Palette: Ctrl+Shift+P
# -> "Dev Containers: Reopen in Container"
```

**Beim ersten Start wird automatisch**:
- Python 3.12 Container gebaut
- Alle Dependencies aus `requirements-dev.txt` installiert
- OpenSearch gestartet
- GND-Index aufgebaut (falls nicht vorhanden)
- API auf Port 8083 gestartet

**Siehe**: [.devcontainer/README.md](.devcontainer/README.md) für Details

---

### Option 2: Lokale Installation

**Voraussetzungen**:
- Python 3.12+
- Docker und Docker Compose (für OpenSearch)

**Setup**:
```bash
# Repository klonen
git clone <REPOSITORY_URL>
cd <REPOSITORY_NAME>

# Virtual Environment erstellen
python3.12 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install --upgrade pip
pip install -r requirements-dev.txt

# OpenSearch starten
docker compose -f docker-compose.runtime.yml up opensearch -d

# Environment-Variablen konfigurieren
cp .env.example .env
# .env bearbeiten: OPENSEARCH_HOST=localhost

# GND-Index aufbauen
python scripts/bootstrap_gnd.py --auto

# API starten
uvicorn api.main:app --reload --host 0.0.0.0 --port 8083
```

---

## Projektstruktur

```
Local_Reconciliation_API/
├── .devcontainer/              # DevContainer-Konfiguration für VS Code
│   ├── devcontainer.json       # VS Code DevContainer Settings
│   ├── docker-compose.yml      # Docker Compose für Entwicklung
│   ├── Dockerfile              # DevContainer Image
│   └── README.md               # DevContainer Dokumentation
│
├── api/                        # FastAPI Anwendung
│   ├── __init__.py
│   ├── main.py                 # FastAPI App und Route-Definitionen
│   ├── constants.py            # Konstanten (GND-Typen, Properties)
│   ├── reconciliation_utils.py # Reconciliation Helper-Funktionen
│   ├── gnd_types.py            # GND Entitätstypen und Mappings
│   ├── models/
│   │   └── openapi_models.py   # Pydantic Models für API
│   └── services/               # Business Logic
│       ├── preview.py          # HTML-Preview-Generierung
│       ├── properties.py       # Extend API (Add columns)
│       ├── property_labels.py  # Property-Label-Auflösung
│       ├── property_matching.py # Property-Vergleich und Scoring
│       ├── property_registry.py # GND Property Registry
│       ├── search.py           # OpenSearch-Integration
│       └── vocab_resolver.py   # RDF Vocabulary Resolver
│
├── config/                     # Konfigurationsdateien
│   ├── __init__.py             # Zentrale Konfiguration (liest .env)
│   ├── gnd_properties.json     # GND Property Registry
│   └── gnd_vocab_labels.json   # Cached Vocab Labels
│
├── data/                       # Datenverzeichnis (git-ignored)
│   ├── raw/                    # Rohe GND-Dumps
│   ├── processed/              # Verarbeitete Daten
│   ├── state/                  # Application State (PIDs, Update-Status)
│   ├── logs/                   # Log-Dateien
│   ├── opensearch/             # OpenSearch Daten
│   └── index/                  # Index-Build-Artefakte
│
├── importer/                   # GND-Daten Download
│   ├── download_gnd_lds.py     # Download GND-LDS-Dumps
│   ├── inspect_gnd_lds.py      # GND-Dumps inspizieren
│   └── normalize_*.py          # Normalisierung
│
├── indexer/                    # OpenSearch Indexierung
│   ├── index_gnd_lds.py        # GND-Daten indexieren
│   ├── index_entityfacts.py    # EntityFacts indexieren
│   ├── upsert_gnd_ids.py       # GND-IDs aktualisieren
│   └── upsert_oai_records.py   # OAI-Records aktualisieren
│
├── scripts/                    # Utility-Scripts
│   ├── bootstrap_gnd.py        # Kompletter GND-Setup
│   ├── fetch_gnd_property_registry.py
│   ├── fetch_gnd_vocab_labels.py
│   ├── harvest_gnd_oai.py      # OAI-PMH Harvesting
│   ├── update_scheduler.py     # Automatische Updates
│   ├── start_container_services.sh  # Container-Startup
│   └── start_dev_services.sh   # DevContainer-Startup
│
├── tests/                      # Tests (TODO: erweitern)
│
├── .env.example                # Environment-Variablen-Template
├── .gitignore
├── docker-compose.runtime.yml  # Production Docker Compose
├── Dockerfile                  # Production Docker Image
├── README.md                   # Hauptdokumentation
├── ENTWICKLUNG.md             # Dieses Dokument
└── requirements-dev.txt        # Python Dependencies

```

### Wichtige Module

| Modul | Zweck |
|-------|-------|
| `api/main.py` | FastAPI App, Route-Definitionen |
| `api/constants.py` | GND-Typen, Properties, Konstanten |
| `api/reconciliation_utils.py` | Reconciliation Helper-Funktionen |
| `api/services/search.py` | OpenSearch-Integration, Scoring |
| `api/services/properties.py` | Extend API Implementation |
| `api/services/preview.py` | HTML-Preview-Generierung |
| `config/__init__.py` | Zentrale Konfiguration (Environment-Variablen) |
| `indexer/index_gnd_lds.py` | Hauptlogik für GND-Indexierung |
| `scripts/bootstrap_gnd.py` | Kompletter Setup-Prozess |

---

## Code-Qualität

### Linting und Formatting mit Ruff

Das Projekt verwendet **Ruff** für Linting und Code-Formatting.

**Installation** (in DevContainer automatisch):
```bash
pip install ruff
```

**Formatting anwenden**:
```bash
# Alle Python-Dateien formatieren
python -m ruff format .

# Nur bestimmte Dateien
python -m ruff format api/main.py api/services/search.py
```

**Linting**:
```bash
# Alle Probleme anzeigen
python -m ruff check .

# Mit automatischer Korrektur
python -m ruff check --fix .

# Nur Import-Sortierung
python -m ruff check --select I --fix .
```

**VS Code Integration**:
Im DevContainer automatisch konfiguriert:
- Format on Save: aktiviert
- Auto-Import-Sortierung: aktiviert
- Ruff als Default Formatter

---

### Code-Stil-Richtlinien

**Type Hints verwenden**:
```python
# ✅ Gut
def search_gnd(query: str, type_filter: str | None = None) -> dict[str, Any]:
    pass


# ❌ Vermeiden
def search_gnd(query, type_filter=None):
    pass
```

**Pathlib statt os.path**:
```python
# ✅ Gut
from pathlib import Path

data_dir = Path(__file__).parent / "data"

# ❌ Vermeiden
import os

data_dir = os.path.join(os.path.dirname(__file__), "data")
```

**Spezifische Exception-Handling**:
```python
# ✅ Gut
from opensearchpy import NotFoundError, OpenSearchException

try:
    result = client.get(index="gnd", id=gnd_id)
except NotFoundError:
    return None
except OpenSearchException as e:
    logger.error(f"OpenSearch error: {e}")
    raise

# ❌ Vermeiden
try:
    result = client.get(index="gnd", id=gnd_id)
except Exception as e:
    pass
```

**Import-Reihenfolge** (automatisch von Ruff):
1. Standard Library
2. Third-Party
3. Local Modules

---

## Testing

### Manuelle API-Tests

**Service Manifest**:
```bash
curl http://localhost:8083/
```

**Reconciliation**:
```bash
curl -X POST "http://localhost:8083/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'queries={"q1":{"query":"Goethe","type":"DifferentiatedPerson"}}'
```

**Extend API**:
```bash
curl -X POST "http://localhost:8083/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'extend={"ids":["118540238"],"properties":[{"id":"preferredName"},{"id":"dateOfBirth"}]}'
```

**Preview**:
```bash
curl "http://localhost:8083/preview?id=118540238"
```

---

### REST Client (VS Code Extension)

Im DevContainer ist die Extension **REST Client** vorinstalliert.

Erstelle eine Datei `api-tests.http`:

```http
### Service Manifest
GET http://localhost:8083/

### Reconciliation
POST http://localhost:8083/
Content-Type: application/x-www-form-urlencoded

queries={"q1":{"query":"Goethe","type":"DifferentiatedPerson"}}

### Extend
POST http://localhost:8083/
Content-Type: application/x-www-form-urlencoded

extend={"ids":["118540238"],"properties":[{"id":"preferredName"}]}

### Preview
GET http://localhost:8083/preview?id=118540238

### Update Status
GET http://localhost:8083/status/update
```

Klicke auf "Send Request" über der Zeile.

---

### Unit Tests (TODO)

```bash
python -m pytest tests/
```

---

## Debugging

### Python Debugger in VS Code

**Breakpoint setzen**:
1. Klick auf die Zeile links (roter Punkt erscheint)
2. F5 oder "Run and Debug" Panel

**Debug-Konfiguration** (`.vscode/launch.json`):
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "api.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8083"
      ],
      "jinja": true,
      "justMyCode": false
    }
  ]
}
```

---

### Logging

**Logs anzeigen** (im Container):
```bash
# API Logs (stdout)
docker compose -f .devcontainer/docker-compose.yml logs -f devcontainer

# OpenSearch Logs
docker compose -f .devcontainer/docker-compose.yml logs -f opensearch
```

**Logging im Code**:
```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

---

## Häufige Entwicklungsaufgaben

### GND-Index neu aufbauen

```bash
# Kompletter Rebuild (Daten neu downloaden)
python scripts/bootstrap_gnd.py --force-reindex

# Nur neu indexieren (vorhandene Dumps verwenden)
python indexer/index_gnd_lds.py --force
```

---

### Einzelnes GND-Record inspizieren

```bash
# In OpenSearch
curl -X GET "http://localhost:9200/gnd/_doc/118540238?pretty"

# Über Python
python -c "
from api.services.search import get_gnd_record_by_id
import json
record = get_gnd_record_by_id('118540238')
print(json.dumps(record, indent=2, ensure_ascii=False))
"
```

---

### Property Registry aktualisieren

```bash
python scripts/fetch_gnd_property_registry.py
# Aktualisiert: config/gnd_properties.json
```

---

### Vocab Labels aktualisieren

```bash
python scripts/fetch_gnd_vocab_labels.py
# Aktualisiert: config/gnd_vocab_labels.json
```

---

### OAI-Updates manuell testen

```bash
# OAI-Records harvesten
python scripts/harvest_gnd_oai.py

# In Index einpflegen
python indexer/upsert_oai_records.py
```

---

### Update-State zurücksetzen

```bash
# Letzten Update-Zeitpunkt löschen
rm -f data/state/update_state.json

# Oder auf bestimmtes Datum setzen
cat > data/state/update_state.json <<'JSON'
{
  "last_oai_harvest": "2026-08-01T00:00:00Z"
}
JSON
```

---

### OpenSearch direkt abfragen

```bash
# Cluster Health
curl "http://localhost:9200/_cluster/health?pretty"

# Index Stats
curl "http://localhost:9200/gnd/_stats?pretty"

# Anzahl Dokumente
curl "http://localhost:9200/gnd/_count?pretty"

# Index Mapping anzeigen
curl "http://localhost:9200/gnd/_mapping?pretty"

# Suche testen
curl -X POST "http://localhost:9200/gnd/_search?pretty" \
  -H "Content-Type: application/json" \
  -d '{
    "query": {
      "match": {
        "preferredName": "Goethe"
      }
    }
  }'
```

---

## Best Practices

### 1. Environment-Variablen zentral verwalten

**Alle Environment-Variablen** werden in `config/__init__.py` gelesen:

```python
from config import OPENSEARCH_HOST, OPENSEARCH_PORT, INDEX_NAME

# ❌ Nicht direkt os.getenv() in anderen Modulen verwenden
# ✅ Immer über config importieren
```

---

### 2. Nie .env in Git committen

`.env` ist in `.gitignore` und darf **niemals** committed werden!

```bash
# ✅ Änderungen in .env.example dokumentieren
# ❌ .env niemals mit git add hinzufügen
```

---

### 3. Ruff vor Commit ausführen

```bash
# Vor jedem Commit
python -m ruff format .
python -m ruff check --fix .

# Oder Pre-Commit Hook einrichten
```

---

### 4. Imports organisieren

Imports werden automatisch von Ruff sortiert:

```python
# 1. Standard Library
import json
import sys
from pathlib import Path
from typing import Any

# 2. Third-Party
from fastapi import FastAPI, Query
from opensearchpy import OpenSearch

# 3. Local Modules
from api.constants import GND_TYPES
from api.services.search import search_gnd
from config import DATA_DIR
```

---

### 5. Type Hints verwenden

```python
from typing import Any


def process_record(record: dict[str, Any], boost: float = 1.0) -> dict[str, Any]:
    """
    Process a GND record.

    Args:
        record: The GND record to process
        boost: Score boost multiplier

    Returns:
        Processed record with additional fields
    """
    # Implementation
    pass
```

---

### 6. Logging statt print()

```python
import logging

logger = logging.getLogger(__name__)

# ❌ Vermeiden
print("Debug info:", some_value)

# ✅ Besser
logger.debug(f"Debug info: {some_value}")
logger.info(f"Processing record: {record_id}")
logger.error(f"Failed to process: {error}")
```

---

### 7. Exceptions spezifisch fangen

```python
from opensearchpy import NotFoundError, OpenSearchException

# ✅ Spezifisch
try:
    result = client.get(index="gnd", id=gnd_id)
except NotFoundError:
    return None
except OpenSearchException as e:
    logger.error(f"OpenSearch error: {e}")
    raise

# ❌ Zu allgemein
try:
    result = client.get(index="gnd", id=gnd_id)
except Exception:
    pass
```

---

### 8. Pathlib verwenden

```python
from pathlib import Path

# ✅ Modern
data_dir = Path(__file__).parent.parent / "data"
state_file = data_dir / "state" / "update_state.json"

if state_file.exists():
    content = state_file.read_text()

# ❌ Alt
import os

data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
state_file = os.path.join(data_dir, "state", "update_state.json")

if os.path.exists(state_file):
    with open(state_file) as f:
        content = f.read()
```

---

## Weiterführende Ressourcen

- **FastAPI Dokumentation**: https://fastapi.tiangolo.com/
- **OpenSearch Python Client**: https://opensearch.org/docs/latest/clients/python/
- **Ruff Dokumentation**: https://docs.astral.sh/ruff/
- **OpenRefine Reconciliation API**: https://reconciliation-api.github.io/specs/latest/
- **GND-Ontologie**: https://d-nb.info/standards/elementset/gnd
- **EntityFacts**: https://www.dnb.de/entityfacts

---

## Fragen und Probleme

Bei Fragen oder Problemen:
1. [README.md](README.md) konsultieren
2. [.devcontainer/README.md](.devcontainer/README.md) für DevContainer-Probleme
3. Issue im Repository öffnen
