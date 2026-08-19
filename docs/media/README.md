# Media

GIFs/Screenshots, die im Haupt-[README.md](../../README.md) eingebunden werden.

Aktuell referenzierte Dateien (noch zu ergänzen):

- `openrefine-add-service.gif`: Standard Reconciliation Service in OpenRefine hinzufügen (`Add Standard Service` + URL eintragen).
- `openrefine-reconcile.gif`: Eine Spalte auswählen, reconciling starten und passenden Typ wählen.
- `openrefine-add-columns.gif`: Über `Add columns from reconciled values` zusätzliche Properties ergänzen.

## Aufnahme-Empfehlungen

- Tool: z.B. [peek](https://github.com/phw/peek) (Linux, nur X11 - funktioniert unter Wayland nicht), [Kooha](https://github.com/SeaDve/Kooha) (Linux, Wayland-nativ), GNOME-Bordmittel (`Strg+Umschalt+Alt+R`), [ScreenToGif](https://www.screentogif.com/) (Windows) oder `ffmpeg`.
- Unter Wayland (`echo $XDG_SESSION_TYPE`) funktioniert Peek nicht zuverlässig - stattdessen Kooha, OBS Studio oder `wf-recorder` verwenden.
- Auflösung möglichst klein halten (z.B. Browserfenster auf ~1000–1200px Breite), damit die GIF-Dateigröße im Repo überschaubar bleibt.
- Aufnahme direkt als GIF exportieren, oder als `.mp4`/`.mov` aufnehmen und mit `ffmpeg` konvertieren:

  ```bash
  ffmpeg -i input.mp4 -vf "fps=10,scale=1000:-1:flags=lanczos" -loop 0 output.gif
  ```

- Dateigröße prüfen (`ls -lh docs/media/*.gif`) - GitHub/GitLab rendern auch große GIFs, aber halten sie unter ein paar MB für schnelle Ladezeiten.
