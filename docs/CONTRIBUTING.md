# Beitragsrichtlinien (Contributing)

Danke für dein Interesse, zu diesem Projekt beizutragen! Diese kurze Anleitung beschreibt den erwarteten Ablauf für Änderungen.

---

## Voraussetzungen

Vor der Arbeit an Änderungen bitte [docs/ENTWICKLUNG.md](ENTWICKLUNG.md) lesen (Entwicklungsumgebung einrichten, Code-Stil, Testing) und bei größeren strukturellen Änderungen zusätzlich [docs/ARCHITEKTUR.md](ARCHITEKTUR.md).

---

## Ablauf

1. **Branch erstellen** von `main` mit einem sprechenden Namen, z.B. `fix/update-scheduler-lock` oder `feat/property-suggest-caching`.
2. **Änderungen umsetzen**, dabei nur das ändern, was für den jeweiligen Zweck notwendig ist (kein unnötiges Refactoring nebenbei).
3. **Lokal testen**:
   ```bash
   python -m ruff format .
   python -m ruff check --fix .
   ```
   Manuelle API-Tests wie in [docs/ENTWICKLUNG.md](ENTWICKLUNG.md#testing) beschrieben durchführen.
4. **Commit-Nachrichten**: kurz, im Imperativ, mit Kontext warum (nicht nur was) geändert wurde.
5. **Pull Request öffnen** mit Beschreibung der Änderung, Testschritten und ggf. betroffenen Environment-Variablen.
6. **CHANGELOG.md aktualisieren** ([docs/CHANGELOG.md](CHANGELOG.md)) unter `[Unreleased]` bei nutzer- oder betriebsrelevanten Änderungen.

---

## Code-Stil

- Python 3.12, Type Hints verwenden.
- Formatierung/Linting über **Ruff** (`python -m ruff format .` / `python -m ruff check --fix .`).
- `pathlib.Path` statt `os.path`.
- Spezifische Exceptions fangen (z.B. `NotFoundError`, `OpenSearchException`), keine nackten `except Exception: pass`.
- Environment-Variablen ausschließlich über `config/__init__.py` lesen, nicht direkt per `os.getenv()` in anderen Modulen.
- Logging (`logging.getLogger(__name__)`) statt `print()`.

Details und Beispiele: [docs/ENTWICKLUNG.md](ENTWICKLUNG.md#code-qualität).

---

## Was nicht committet werden darf

- `.env` (enthält lokale/host-spezifische Werte) – Änderungen stattdessen in `.env.example` dokumentieren.
- Inhalte aus `data/` (Dumps, Index-State, Logs) – dieser Ordner ist git-ignored.

---

## Fragen

Bei Unklarheiten vor größeren Änderungen ein Issue im Repository öffnen, um die Herangehensweise kurz abzustimmen.
