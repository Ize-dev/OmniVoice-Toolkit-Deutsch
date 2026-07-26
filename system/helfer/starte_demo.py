#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Startet die OmniVoice-Weboberflaeche INNERHALB der Arbeitsumgebung (venv).

Statt die Datei omnivoice-demo.exe aufzurufen, wird der Startpunkt ueber die
Paketinformationen ermittelt. Das funktioniert auch dann noch, wenn die .exe
fehlt oder anders heisst.

Alle Argumente werden unveraendert an OmniVoice weitergereicht, zum Beispiel:
    python starte_demo.py --ip 127.0.0.1 --port 7860
"""

import sys


def sag(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def finde_startpunkt():
    """Sucht den Eintrag 'omnivoice-demo' in den installierten Paketen."""
    try:
        from importlib import metadata

        for eintrag in metadata.entry_points().select(group="console_scripts"):
            if eintrag.name == "omnivoice-demo":
                return eintrag.load()
    except Exception as fehler:
        sag(f"Hinweis: Startpunkt nicht ueber die Paketinformationen gefunden "
            f"({type(fehler).__name__}: {fehler}).")

    for modulname in ("omnivoice.cli.demo", "omnivoice.demo", "omnivoice.bin.demo"):
        try:
            modul = __import__(modulname, fromlist=["main"])
            if hasattr(modul, "main"):
                return modul.main
        except Exception:
            continue
    return None


def main() -> int:
    argumente = sys.argv[1:]
    sag("OmniVoice wird vorbereitet - das Laden der Bibliotheken dauert einen Moment …")

    startpunkt = finde_startpunkt()
    if startpunkt is None:
        sag("FEHLER: Die OmniVoice-Weboberflaeche wurde nicht gefunden.")
        sag("Bitte im Hauptmenue »Reparieren« waehlen.")
        return 2

    sys.argv = ["omnivoice-demo"] + argumente
    sag("Sprachmodell wird geladen …")
    try:
        startpunkt()
    except KeyboardInterrupt:
        sag("OmniVoice wurde beendet.")
        return 0
    except SystemExit as ende:
        return int(ende.code or 0)
    except Exception as fehler:
        sag("")
        sag(f"FEHLER beim Start: {type(fehler).__name__}: {fehler}")
        import traceback

        traceback.print_exc()
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
