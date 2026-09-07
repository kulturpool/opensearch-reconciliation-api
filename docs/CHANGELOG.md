# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

---

## [Unreleased]

### Hinzugefügt
- **Getty Art & Architecture Thesaurus (AAT)** als zweites Reconciliation-Vokabular unter `/getty`, parallel zur bestehenden GND-Reconciliation am Root-Endpunkt:
  - Gemeinsame Router-Factory ([api/routers/reconciliation.py](../api/routers/reconciliation.py)) erzeugt aus einer vokabularspezifischen `VocabConfig` ([api/vocabularies/base.py](../api/vocabularies/base.py)) alle OpenRefine-Endpunkte (Manifest, Query, Suggest, Extend, Preview) für GND ([api/vocabularies/gnd.py](../api/vocabularies/gnd.py)) und Getty ([api/vocabularies/getty.py](../api/vocabularies/getty.py)).
  - Neue Importer- und Indexer-Pipeline für den Getty-N-Triples-Export ([importer/download_getty.py](../importer/download_getty.py), [importer/normalize_getty.py](../importer/normalize_getty.py), [importer/ntriples.py](../importer/ntriples.py), [indexer/index_getty.py](../indexer/index_getty.py)).
  - [scripts/bootstrap_getty.py](../scripts/bootstrap_getty.py): eigenständiges Bootstrap-Skript mit `--check-only`/`--init`/`--auto`/`--limit`, analog zu `bootstrap_gnd.py`. Rebuilds sind zero-downtime über einen Alias-Switch (`getty` zeigt auf `getty_build_<timestamp>`); der alte Build-Index wird nach dem Switch gelöscht.
  - [scripts/update_getty.py](../scripts/update_getty.py) und [scripts/update_getty_scheduler.py](../scripts/update_getty_scheduler.py): periodischer Voll-Rebuild-Scheduler, da Getty (anders als GND) keine inkrementelle Update-Quelle bereitstellt.
  - `scripts/index_build_state.py` und `scripts/opensearch_index_admin.py` generalisiert, um Build-State, Locks und Alias-Switching für mehrere Vokabulare (`vocab`-Parameter) zu unterstützen, statt GND-spezifisch zu sein.
  - Neue Konfigurationsvariablen in `.env.example` (`GETTY_INDEX_NAME`, `GETTY_VOCABULARIES`, `GETTY_FORCE_REINDEX`, `GETTY_AUTO_UPDATE`, `GETTY_UPDATE_INTERVAL_HOURS`, `GETTY_UPDATE_INITIAL_DELAY_SECONDS`, `GETTY_INDEX_LOCK_STALE_SECONDS`, `GETTY_UPDATE_LOCK_STALE_SECONDS`, `GETTY_RAW_DIR`, `GETTY_DOWNLOAD_URL_TEMPLATE`).
  - README.md- und docs/ARCHITEKTUR.md-Abschnitte zu Getty AAT.
- [docs/ARCHITEKTUR.md](ARCHITEKTUR.md): Architektur- und Datenfluss-Dokumentation.
- [docs/CONTRIBUTING.md](CONTRIBUTING.md): Beitragsrichtlinien.
- Dieses Changelog.

### Geändert
- Entwicklungsdokumentation von `ENTWICKLUNG.md` nach [docs/ENTWICKLUNG.md](ENTWICKLUNG.md) verschoben.
- `GND_UPDATE_INTERVAL_HOURS` Standardwert von 24 auf 168 (wöchentlich) geändert, um an den tatsächlichen DNB-Update-Rhythmus anzupassen.

### Behoben
- Update-Scheduler-Lock (`data/state/update.lock`) konnte nach einem abgebrochenen Container-Lauf dauerhaft bestehen bleiben und alle künftigen Update-Zyklen blockieren. Behoben durch `GND_UPDATE_LOCK_STALE_SECONDS` (Standard: 6h) inkl. Staleness-Check, analog zum bestehenden `index_build.lock`-Mechanismus.
- `scripts/bootstrap_getty.py --check-only` konnte über `initial_setup_required()` versehentlich `adopt_existing_index_if_healthy()` auslösen und damit trotz `--check-only` State schreiben. `--check-only` ist jetzt vollständig lesend; die Adoption eines bestehenden, gesunden Getty-Index erfolgt ausschließlich aus `--auto`/`run_auto()`.

---

## Hinweis

Frühere Änderungen wurden vor Einführung dieses Changelogs nicht systematisch erfasst.
