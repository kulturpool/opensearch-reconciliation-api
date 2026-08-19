# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).

---

## [Unreleased]

### Geändert
- Entwicklungsdokumentation von `ENTWICKLUNG.md` nach [docs/ENTWICKLUNG.md](ENTWICKLUNG.md) verschoben.
- `GND_UPDATE_INTERVAL_HOURS` Standardwert von 24 auf 168 (wöchentlich) geändert, um an den tatsächlichen DNB-Update-Rhythmus anzupassen.

### Hinzugefügt
- [docs/ARCHITEKTUR.md](ARCHITEKTUR.md): Architektur- und Datenfluss-Dokumentation.
- [docs/CONTRIBUTING.md](CONTRIBUTING.md): Beitragsrichtlinien.
- Dieses Changelog.

### Behoben
- Update-Scheduler-Lock (`data/state/update.lock`) konnte nach einem abgebrochenen Container-Lauf dauerhaft bestehen bleiben und alle künftigen Update-Zyklen blockieren. Behoben durch `GND_UPDATE_LOCK_STALE_SECONDS` (Standard: 6h) inkl. Staleness-Check, analog zum bestehenden `index_build.lock`-Mechanismus.

---

## Hinweis

Frühere Änderungen wurden vor Einführung dieses Changelogs nicht systematisch erfasst.
