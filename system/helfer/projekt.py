#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Projektverwaltung für den Stapelbetrieb.

Ein Projekt hält alles zusammen, was zu einer Vertonung gehört: die Liste, den
Projektstart, den Ausgabeordner, die Erzeugungs- und Klangeinstellungen sowie
die Merker der bearbeiteten Szenen. Damit muss beim Weiterarbeiten nichts mehr
von Hand eingetragen werden.

Die Datei ist bewusst schlichtes JSON und enthält nur Pfade und Einstellungen -
keine Audiodaten. Die Szenen selbst liegen weiterhin in ihren eigenen Ordnern
unter »Ergebnisse/szenen« und werden dort automatisch gesichert.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ART = "omnivoice-projekt"
VERSION = 1
ENDUNG = ".omniprojekt.json"

# Diese Felder werden gesichert. Alles andere bleibt außen vor, damit eine
# Projektdatei auch nach Umbauten der Oberfläche noch lesbar ist.
FELDER = [
    "csv", "wurzel", "ausgabe", "ueberspringen", "dauer_von_probe", "bericht",
    "arbeiter", "qualitaet", "tempo", "dauer_offset", "stille_weg",
    "laut_modus", "laut_db", "whisper_rating", "tab_autoplay",
]


def voller_pfad(pfad) -> Path:
    """Ergänzt die übliche Endung, wenn keine angegeben wurde."""
    pfad = Path(str(pfad).strip('" ').strip())
    if pfad.suffix.lower() != ".json":
        pfad = pfad.with_name(pfad.name + ENDUNG)
    return pfad


def speichern(pfad, werte: dict, szenen: list = None) -> dict:
    ziel = voller_pfad(pfad)
    daten = {
        "art": ART,
        "version": VERSION,
        "gespeichert": time.strftime("%Y-%m-%d %H:%M:%S"),
        "einstellungen": {name: werte.get(name) for name in FELDER},
        "szenen": list(szenen or []),
    }
    try:
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as fehler:
        return {"ok": False, "meldung": f"Projekt nicht speicherbar: {fehler}"}
    return {"ok": True, "pfad": str(ziel),
            "meldung": f"Projekt gespeichert: {ziel.name}"}


def laden(pfad) -> dict:
    quelle = Path(str(pfad).strip('" ').strip())
    if not quelle.is_file():
        quelle = voller_pfad(pfad)
    if not quelle.is_file():
        return {"ok": False, "meldung": f"Projektdatei nicht gefunden: {quelle}"}
    try:
        daten = json.loads(quelle.read_text(encoding="utf-8"))
    except Exception as fehler:
        return {"ok": False, "meldung": f"Projektdatei nicht lesbar: {fehler}"}
    if daten.get("art") != ART:
        return {"ok": False, "meldung": "Das ist keine OmniVoice-Projektdatei."}

    werte = daten.get("einstellungen") or {}
    return {
        "ok": True,
        "pfad": str(quelle),
        "einstellungen": {name: werte.get(name) for name in FELDER},
        "szenen": daten.get("szenen") or [],
        "meldung": (f"Projekt geladen: {quelle.name} "
                    f"(gespeichert {daten.get('gespeichert', '?')})"),
    }


def merker_pfad(daten_ordner) -> Path:
    """Wo steht, welches Projekt zuletzt offen war."""
    return Path(daten_ordner) / "letztes-projekt.json"


def merke(daten_ordner, pfad) -> None:
    try:
        merker_pfad(daten_ordner).write_text(
            json.dumps({"pfad": str(pfad)}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def letztes(daten_ordner) -> str:
    try:
        datei = merker_pfad(daten_ordner)
        if datei.is_file():
            return str(json.loads(datei.read_text(encoding="utf-8")).get("pfad", ""))
    except Exception:
        pass
    return ""
