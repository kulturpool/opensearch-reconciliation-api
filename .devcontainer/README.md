# DevContainer Entwicklungsumgebung

Diese DevContainer-Konfiguration ermöglicht die lokale Entwicklung mit VS Code.

## Was ist ein DevContainer?

Ein DevContainer ist eine vollständige Entwicklungsumgebung, die in Docker läuft. VS Code verbindet sich mit diesem Container und ermöglicht:

- ✅ Konsistente Entwicklungsumgebung für alle Teammitglieder
- ✅ Keine lokale Python-Installation erforderlich
- ✅ Automatische Installation aller Dependencies
- ✅ Vorinstallierte VS Code Extensions
- ✅ Direkter Zugriff auf OpenSearch-Container
- ✅ Hot-Reload für Code-Änderungen

## Voraussetzungen

- **VS Code** mit der Extension **Dev Containers** ([ms-vscode-remote.remote-containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers))
- **Docker** und **Docker Compose**

## Schnellstart

1. **Repository öffnen** in VS Code
2. **Command Palette** öffnen: `Ctrl+Shift+P` (Linux/Windows) oder `Cmd+Shift+P` (Mac)
3. **"Dev Containers: Reopen in Container"** auswählen
4. **Warten**, bis der Container gebaut und gestartet ist (~5-10 Minuten beim ersten Mal)
5. **Automatisch** wird:
   - Python 3.12 installiert
   - Alle Pakete aus `requirements-dev.txt` installiert
   - OpenSearch gestartet
   - GND-Bootstrap durchgeführt (falls noch kein Index existiert)
   - API auf Port 8083 gestartet

## Wichtige Unterschiede zu Runtime

| Aspekt | DevContainer (diese Config) | Runtime (`docker-compose.runtime.yml`) |
|--------|----------------------------|----------------------------------------|
| **Zweck** | Lokale Entwicklung | Production/Deployment |
| **Code** | Live aus Workspace-Ordner | Kopiert in Image beim Build |
| **Hot-Reload** | ✅ Ja (uvicorn --reload) | ❌ Nein |
| **Tools** | vim, httpie, tree, etc. | Minimal |
| **VS Code** | Integriert | Nicht integriert |
| **OpenSearch Volume** | Shared mit Runtime | Shared mit DevContainer |

## OpenSearch Volume Sharing

⚠️ **WICHTIG**: DevContainer und Runtime teilen sich das gleiche OpenSearch-Volume (`local_reconciliation_api_opensearch-data`).

**Vorteil**: GND-Index muss nur einmal gebaut werden (~3 GB Download + Indexierung).

**Nachteil**: **Beide dürfen nicht gleichzeitig laufen!**

### Wechsel von Runtime zu DevContainer

```bash
# Runtime stoppen
docker compose -f docker-compose.runtime.yml down

# VS Code: "Reopen in Container"
```

### Wechsel von DevContainer zu Runtime

```bash
# DevContainer stoppen (in VS Code: "Reopen Folder Locally")
docker compose -f .devcontainer/docker-compose.yml down

# Runtime starten
docker compose -f docker-compose.runtime.yml up --build
```

## Dateien in diesem Ordner

- **`devcontainer.json`**: Hauptkonfiguration für VS Code DevContainers
  - Definiert Services, Extensions, Settings
  - Port-Forwarding (8083, 9200)
  - Post-Create und Post-Start Commands

- **`docker-compose.yml`**: Docker Compose für Entwicklung
  - `devcontainer` Service: Python 3.12 mit Tools
  - `opensearch` Service: Lokale Suchmaschine

- **`Dockerfile`**: Image für den DevContainer
  - Basiert auf Microsoft's Python 3.12 DevContainer Image
  - Zusätzliche Tools: curl, jq, httpie, vim, etc.

## Entwicklungsworkflow

### API testen

Die API läuft automatisch auf `http://localhost:8083`:

```bash
# Service Manifest
curl http://localhost:8083/

# Reconciliation Query
curl -X POST "http://localhost:8083/" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode 'queries={"q1":{"query":"Goethe","type":"DifferentiatedPerson"}}'
```

### OpenSearch testen

OpenSearch läuft auf `http://localhost:9200`:

```bash
# Cluster Health
curl http://localhost:9200/_cluster/health?pretty

# Index Stats
curl http://localhost:9200/gnd/_stats?pretty

# Anzahl Dokumente
curl http://localhost:9200/gnd/_count?pretty
```

### Code-Änderungen

- Code-Änderungen werden **sofort** aktiv (uvicorn --reload)
- Nach Änderungen in `requirements-dev.txt`: `pip install -r requirements-dev.txt`
- Nach Änderungen an der DevContainer-Config: "Dev Containers: Rebuild Container"

### Terminal im Container

VS Code öffnet automatisch ein Terminal im Container. Alle Scripts können direkt ausgeführt werden:

```bash
# Manuell OpenSearch überprüfen
python -c "from config import get_opensearch_client; print(get_opensearch_client().info())"

# Manuelles OAI-Update
python scripts/harvest_gnd_oai.py

# Index neu aufbauen
python scripts/bootstrap_gnd.py --force-reindex

# Tests ausführen
python -m pytest tests/
```

## Troubleshooting

### Container startet nicht

```bash
# Logs anschauen
docker compose -f .devcontainer/docker-compose.yml logs

# Container komplett neu bauen
docker compose -f .devcontainer/docker-compose.yml down -v
# In VS Code: "Dev Containers: Rebuild Container"
```

### OpenSearch läuft nicht

```bash
# OpenSearch Logs
docker compose -f .devcontainer/docker-compose.yml logs opensearch

# OpenSearch Status
curl http://localhost:9200/_cluster/health?pretty
```

### GND-Index fehlt

```bash
# Bootstrap manuell starten
python scripts/bootstrap_gnd.py --auto
```

### Volume-Konflikte

```bash
# Alle Container stoppen
docker compose -f docker-compose.runtime.yml down
docker compose -f .devcontainer/docker-compose.yml down

# Volume neu erstellen (ACHTUNG: Löscht GND-Index!)
docker volume rm local_reconciliation_api_opensearch-data
docker volume create local_reconciliation_api_opensearch-data
```

## VS Code Extensions

Diese Extensions werden automatisch installiert:

- **Python** (ms-python.python): Python Language Support
- **Pylance** (ms-python.vscode-pylance): Fast Python Language Server
- **Docker** (ms-azuretools.vscode-docker): Docker Management
- **YAML** (redhat.vscode-yaml): YAML Support
- **REST Client** (humao.rest-client): API Testing in VS Code
- **Ruff** (charliermarsh.ruff): Fast Python Linter & Formatter

## Weitere Informationen

- [VS Code Dev Containers Documentation](https://code.visualstudio.com/docs/devcontainers/containers)
- [Dev Containers Specification](https://containers.dev/)
- Hauptprojekt-README: `../README.md`
