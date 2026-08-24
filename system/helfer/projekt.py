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
VERSION = 2
ENDUNG = ".omniprojekt.json"
ORDNER = "Projekte"      # Standardablage neben STARTEN.bat


def standard_ordner() -> Path:
    """Der Ordner »Projekte« im Toolkit - liegt neben STARTEN.bat."""
    return Path(__file__).resolve().parent.parent.parent / ORDNER


def vorschlag() -> str:
    """Was im leeren Feld stehen soll: der Ordner, noch ohne Dateinamen."""
    return str(standard_ordner()) + "\\"

# Diese Felder werden gesichert. Alles andere bleibt außen vor, damit eine
# Projektdatei auch nach Umbauten der Oberfläche noch lesbar ist.
FELDER = [
    "csv", "wurzel", "ausgabe", "ueberspringen", "dauer_von_probe", "bericht",
    "arbeiter", "qualitaet", "tempo", "dauer_offset", "stille_weg",
    "laut_modus", "laut_db", "ziel_pegel", "whisper_rating", "tab_autoplay",
    "text_ersetzungen", "text_anhang",
]


def voller_pfad(pfad) -> Path:
    """
    Ergänzt die übliche Endung und legt relative Angaben in »Projekte« ab.

    So genügt es, im Feld einen Namen einzutippen - die Datei landet dann im
    Projekte-Ordner des Toolkits und nicht irgendwo im Arbeitsverzeichnis.
    """
    roh = str(pfad).strip('" ').strip()
    pfad = Path(roh)
    if not pfad.is_absolute():
        pfad = standard_ordner() / pfad
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
        # Auch ohne Endung angegeben? Dann im Projekte-Ordner nachsehen.
        name = Path(str(pfad).strip('" ').strip()).name
        ersatz = standard_ordner() / name
        if ersatz.is_file():
            quelle = ersatz
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


def vorhandene(zusatz: str = "") -> list:
    """
    Alle Projektdateien im Ordner »Projekte«, neueste zuerst.

    »zusatz« ist ein Pfad, der mit aufgenommen wird, auch wenn er woanders
    liegt - damit ein von Hand gewaehltes Projekt in der Liste stehen bleibt.
    """
    gefunden = []
    try:
        ordner = standard_ordner()
        if ordner.is_dir():
            gefunden = sorted((p for p in ordner.glob("*.json") if p.is_file()),
                              key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        gefunden = []
    namen = [str(p) for p in gefunden]
    zusatz = str(zusatz or "").strip()
    if zusatz and zusatz not in namen and Path(zusatz).is_file():
        namen.insert(0, zusatz)
    return namen


def kurzname(pfad) -> str:
    """Anzeigename: im Projekte-Ordner nur der Name, sonst der ganze Pfad."""
    pfad = Path(str(pfad))
    name = pfad.name
    for endung in (ENDUNG, ".json"):
        if name.lower().endswith(endung.lower()):
            name = name[: -len(endung)]
            break
    try:
        if pfad.parent == standard_ordner():
            return name
    except OSError:
        pass
    return f"{name}   ({pfad.parent})"


def waehlen(anfang: str = "") -> str:
    """
    Windows-Dateidialog zum Aussuchen einer Projektdatei.

    Laeuft im selben Rechner wie die Oberflaeche, deshalb ist ein echter
    Dialog moeglich - anders als bei einem Hochladefeld bleibt der richtige
    Pfad erhalten und nicht bloss eine Kopie im Zwischenspeicher.
    """
    import tkinter as tk
    from tkinter import filedialog

    start = Path(str(anfang or "").strip('" ')) if anfang else standard_ordner()
    if start.is_file():
        start = start.parent
    if not start.is_dir():
        start = standard_ordner()
    try:
        start.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    fenster = tk.Tk()
    fenster.withdraw()
    fenster.attributes("-topmost", True)      # sonst hinter dem Browser
    try:
        gewaehlt = filedialog.askopenfilename(
            parent=fenster,
            title="Projektdatei öffnen",
            initialdir=str(start),
            filetypes=[("OmniVoice-Projekt", "*.json"), ("Alle Dateien", "*.*")],
        )
    finally:
        fenster.destroy()
    return str(gewaehlt or "")


def letztes(daten_ordner) -> str:
    try:
        datei = merker_pfad(daten_ordner)
        if datei.is_file():
            return str(json.loads(datei.read_text(encoding="utf-8")).get("pfad", ""))
    except Exception:
        pass
    return ""
