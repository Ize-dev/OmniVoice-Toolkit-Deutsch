#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Laedt das OmniVoice-Sprachmodell von Hugging Face herunter.

Dieses Skript laeuft INNERHALB der Arbeitsumgebung (venv), weil nur dort
huggingface_hub installiert ist. Es meldet den Fortschritt zeilenweise als

    #FORTSCHRITT#{"fertig": 123, "gesamt": 456, "datei": "..."}

an das OmniVoice Studio zurueck. Alles andere ist normaler Text fuers Protokoll.

Rueckgabecode: 0 = erfolgreich, 1 = fehlgeschlagen.
Abgebrochene Downloads werden beim naechsten Aufruf fortgesetzt.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

STANDARD_REPO = "k2-fsa/OmniVoice"
STANDARD_GROESSE = 3_270_000_000

# Dateien, die fuer den Betrieb nicht gebraucht werden.
NICHT_NOETIG = ["*.md", "*.gitattributes", ".gitignore"]


def melde(**werte) -> None:
    sys.stdout.write("#FORTSCHRITT#" + json.dumps(werte, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def sag(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def cache_wurzel() -> Path:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return Path(HF_HUB_CACHE)
    except Exception:
        basis = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
        if basis:
            pfad = Path(basis)
            return pfad if pfad.name == "hub" else pfad / "hub"
        return Path.home() / ".cache" / "huggingface" / "hub"


def repo_ordner(repo: str) -> Path:
    return cache_wurzel() / ("models--" + repo.replace("/", "--"))


def gesamtgroesse(repo: str) -> int:
    """Fragt die Dateigroessen im Repository ab (0 = unbekannt)."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo, files_metadata=True)
        summe = 0
        for datei in info.siblings or []:
            name = getattr(datei, "rfilename", "") or ""
            if name.endswith(".md") or name.endswith(".gitattributes"):
                continue
            summe += getattr(datei, "size", None) or 0
        return summe
    except Exception as fehler:
        sag(f"Hinweis: Die Groesse liess sich nicht abfragen ({type(fehler).__name__}).")
        return 0


def ordner_bytes(pfad: Path) -> int:
    summe = 0
    try:
        for wurzel, _ordner, dateien in os.walk(pfad):
            for name in dateien:
                try:
                    summe += os.path.getsize(os.path.join(wurzel, name))
                except OSError:
                    pass
    except OSError:
        pass
    return summe


def dateizustand(ordner: Path) -> str:
    blobs = ordner / "blobs"
    if not blobs.exists():
        return "Verbindung wird aufgebaut …"
    fertig = laufend = 0
    try:
        for eintrag in blobs.iterdir():
            if eintrag.name.endswith(".incomplete"):
                laufend += 1
            else:
                fertig += 1
    except OSError:
        pass
    if laufend:
        return f"{fertig} Dateien fertig, {laufend} laufen gerade"
    return f"{fertig} Dateien fertig"


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else STANDARD_REPO

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sag("FEHLER: huggingface_hub ist nicht installiert. Bitte die Installation wiederholen.")
        return 1

    ziel = repo_ordner(repo)
    vorhanden = ordner_bytes(ziel)
    gesamt = gesamtgroesse(repo) or STANDARD_GROESSE

    sag(f"Modell    : {repo}")
    sag(f"Ablage    : {ziel}")
    sag(f"Groesse   : rund {gesamt / 1024 ** 3:.2f} GB")
    if vorhanden > 50_000_000:
        sag(f"Bereits vorhanden: {vorhanden / 1024 ** 3:.2f} GB - es wird fortgesetzt.")
    sag("")

    ergebnis: dict = {}

    def arbeite() -> None:
        try:
            ergebnis["pfad"] = snapshot_download(
                repo_id=repo,
                repo_type="model",
                ignore_patterns=NICHT_NOETIG,
                max_workers=4,
            )
        except Exception as fehler:
            ergebnis["fehler"] = f"{type(fehler).__name__}: {fehler}"

    arbeiter = threading.Thread(target=arbeite, daemon=True)
    arbeiter.start()

    melde(fertig=vorhanden, gesamt=gesamt, datei="Verbindung wird aufgebaut …")
    while arbeiter.is_alive():
        time.sleep(1.0)
        melde(fertig=ordner_bytes(ziel), gesamt=gesamt, datei=dateizustand(ziel))
    arbeiter.join()

    if "fehler" in ergebnis:
        sag("")
        sag("FEHLER beim Herunterladen: " + str(ergebnis["fehler"]))
        sag("Bereits geladene Teile bleiben erhalten und werden beim naechsten Mal weiterverwendet.")
        return 1

    endgroesse = ordner_bytes(ziel)
    melde(fertig=max(endgroesse, gesamt), gesamt=gesamt, datei="fertig")
    sag("")
    sag(f"Fertig. Auf der Platte liegen jetzt {endgroesse / 1024 ** 3:.2f} GB.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sag("Abgebrochen.")
        sys.exit(1)
