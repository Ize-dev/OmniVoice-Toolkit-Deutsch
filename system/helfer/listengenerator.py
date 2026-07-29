#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Konfigurierbare Textlisten-Parser und Fuzzy-Zuordnung fuer den CSV-Generator."""

import csv
import difflib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from whisper_dienst import aehnlichkeit, normalisiere_text

AUDIO_ENDUNGEN = {
    ".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a",
    ".aac", ".wma", ".aiff", ".wem",
}
MODI = ["Automatisch", "ID = Text", "Spalten", "Regulärer Ausdruck"]
STANDARD_REGEX = r"^\s*(?P<id>[^=]+?)\s*=\s*(?P<text>.+?)\s*$"


@dataclass
class TextEintrag:
    identifier: str
    text: str
    zeile: int = 0
    normalisiert: str = field(init=False, repr=False)

    def __post_init__(self):
        self.normalisiert = normalisiere_text(self.text)


@dataclass
class ParserOptionen:
    modus: str = "Automatisch"
    trenner: str = "="
    id_spalte: int = 1
    text_spalte: int = 2
    regex: str = STANDARD_REGEX


def lies_text(pfad) -> str:
    letzter = None
    for kodierung in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return Path(pfad).read_text(encoding=kodierung)
        except UnicodeDecodeError as fehler:
            letzter = fehler
        except OSError as fehler:
            raise RuntimeError(f"Textliste lässt sich nicht öffnen: {fehler}") from fehler
    raise RuntimeError(f"Textkodierung wurde nicht erkannt: {letzter}")


def _sauber(wert) -> str:
    return str(wert or "").strip().strip("\ufeff").strip().strip('"').strip()


def id_schluessel(identifier: str) -> str:
    return re.sub(r"\s+", "", _sauber(identifier)).casefold()


def _zeilen(roh: str) -> list[tuple[int, str]]:
    return [
        (nummer, zeile)
        for nummer, zeile in enumerate(roh.splitlines(), start=1)
        if zeile.strip() and not zeile.lstrip().startswith(("#", "//"))
    ]


def _parse_regex(roh: str, muster: str) -> list[TextEintrag]:
    try:
        regex = re.compile(muster)
    except re.error as fehler:
        raise RuntimeError(f"Ungültiger regulärer Ausdruck: {fehler}") from fehler
    ergebnis = []
    for nummer, zeile in _zeilen(roh):
        treffer = regex.search(zeile)
        if not treffer:
            continue
        if "id" in regex.groupindex and "text" in regex.groupindex:
            identifier, text = treffer.group("id"), treffer.group("text")
        elif treffer.lastindex and treffer.lastindex >= 2:
            identifier, text = treffer.group(1), treffer.group(2)
        else:
            raise RuntimeError("Regex braucht Gruppen (?P<id>…) und (?P<text>…) oder Gruppe 1 und 2.")
        identifier, text = _sauber(identifier), _sauber(text)
        if identifier and text:
            ergebnis.append(TextEintrag(identifier, text, nummer))
    return ergebnis


def _parse_trenner(roh: str, trenner: str) -> list[TextEintrag]:
    trenner = str(trenner or "=").replace("\\t", "\t")
    if not trenner:
        raise RuntimeError("Das Trennzeichen darf nicht leer sein.")
    ergebnis = []
    for nummer, zeile in _zeilen(roh):
        if trenner not in zeile:
            continue
        identifier, text = zeile.split(trenner, 1)
        identifier, text = _sauber(identifier), _sauber(text)
        if identifier and text:
            ergebnis.append(TextEintrag(identifier, text, nummer))
    return ergebnis


def _parse_spalten(roh: str, trenner: str, id_spalte: int, text_spalte: int) -> list[TextEintrag]:
    trenner = str(trenner or ";").replace("\\t", "\t")
    if len(trenner) != 1:
        raise RuntimeError("Für den Spaltenmodus muss das Trennzeichen genau ein Zeichen haben.")
    id_index, text_index = max(0, int(id_spalte) - 1), max(0, int(text_spalte) - 1)
    ergebnis = []
    for nummer, felder in enumerate(csv.reader(io.StringIO(roh), delimiter=trenner), start=1):
        if max(id_index, text_index) >= len(felder):
            continue
        identifier, text = _sauber(felder[id_index]), _sauber(felder[text_index])
        if identifier and text:
            ergebnis.append(TextEintrag(identifier, text, nummer))
    return ergebnis


def _parse_json(roh: str) -> list[TextEintrag]:
    daten = json.loads(roh)
    ergebnis = []
    if isinstance(daten, dict):
        iterable = daten.items()
    elif isinstance(daten, list):
        iterable = enumerate(daten, start=1)
    else:
        return []
    for nummer, (schluessel, wert) in enumerate(iterable, start=1):
        if isinstance(wert, str):
            identifier, text = schluessel, wert
        elif isinstance(wert, dict):
            identifier = wert.get("id", wert.get("identifier", schluessel))
            text = wert.get("text", wert.get("value", wert.get("line", "")))
        else:
            continue
        identifier, text = _sauber(identifier), _sauber(text)
        if identifier and text:
            ergebnis.append(TextEintrag(identifier, text, nummer))
    return ergebnis


def parse_liste(pfad, optionen: ParserOptionen) -> list[TextEintrag]:
    roh = lies_text(pfad)
    modus = optionen.modus or "Automatisch"
    if modus == "ID = Text":
        ergebnis = _parse_trenner(roh, optionen.trenner)
    elif modus == "Spalten":
        ergebnis = _parse_spalten(
            roh, optionen.trenner, optionen.id_spalte, optionen.text_spalte
        )
    elif modus == "Regulärer Ausdruck":
        ergebnis = _parse_regex(roh, optionen.regex)
    else:
        ergebnis = []
        if Path(pfad).suffix.lower() == ".json" or roh.lstrip().startswith(("{", "[")):
            try:
                ergebnis = _parse_json(roh)
            except (ValueError, TypeError):
                ergebnis = []
        if not ergebnis:
            ergebnis = _parse_regex(roh, optionen.regex or STANDARD_REGEX)
        if not ergebnis:
            for trenner in (";", "\t", "|", ","):
                kandidat = _parse_spalten(
                    roh, trenner, optionen.id_spalte, optionen.text_spalte
                )
                if len(kandidat) > len(ergebnis):
                    ergebnis = kandidat
    if not ergebnis:
        raise RuntimeError("Keine ID/Text-Zeile erkannt. Parser-Einstellungen prüfen.")
    return ergebnis


def als_index(eintraege: list[TextEintrag]) -> tuple[dict, list[str]]:
    index, doppelt = {}, []
    for eintrag in eintraege:
        key = id_schluessel(eintrag.identifier)
        if not key:
            continue
        if key in index:
            doppelt.append(eintrag.identifier)
            continue
        index[key] = eintrag
    return index, doppelt


def audio_dateien(ordner) -> list[Path]:
    wurzel = Path(str(ordner or "")).expanduser()
    if not wurzel.is_dir():
        raise RuntimeError(f"Audioordner nicht gefunden: {wurzel}")
    dateien = [p for p in wurzel.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_ENDUNGEN]

    def natuerlich(pfad: Path):
        return [int(t) if t.isdigit() else t.casefold()
                for t in re.split(r"(\d+)", str(pfad.relative_to(wurzel)))]

    return sorted(dateien, key=natuerlich)


def bester_treffer(transkript: str, eintraege: list[TextEintrag]) -> tuple[TextEintrag | None, float]:
    suchtext = normalisiere_text(transkript)
    if not suchtext or not eintraege:
        return None, 0.0
    # Bei großen Spiele-Textlisten wäre die vollständige Dreifachbewertung jeder
    # Zeile unnötig teuer. SequenceMatcher wählt zuerst einige Kandidaten aus;
    # nur diese bekommen anschließend das robuste gewichtete Rating.
    texte = [eintrag.normalisiert for eintrag in eintraege if eintrag.normalisiert]
    kandidaten_text = set(
        difflib.get_close_matches(
            suchtext, texte, n=min(12, len(texte)), cutoff=0.0
        )
    )
    kandidaten = [
        eintrag for eintrag in eintraege if eintrag.normalisiert in kandidaten_text
    ] or eintraege
    bester, wert = None, 0.0
    for eintrag in kandidaten:
        aktuell = aehnlichkeit(eintrag.text, transkript)
        if aktuell > wert:
            bester, wert = eintrag, aktuell
    return bester, round(wert, 1)


def schreibe_csv(zeilen: list[tuple[str, str, str]], ziel: Path) -> Path:
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    temporaer = ziel.with_suffix(ziel.suffix + ".tmp")
    with open(temporaer, "w", encoding="utf-8-sig", newline="") as datei:
        schreiber = csv.writer(datei, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        schreiber.writerows(zeilen)
    temporaer.replace(ziel)
    return ziel
