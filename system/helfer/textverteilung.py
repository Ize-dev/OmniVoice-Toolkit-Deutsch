#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lange zweisprachige Szenentexte monoton auf Whisper-Segmente verteilen."""

from __future__ import annotations

import difflib
import math
import re

SATZENDE = re.compile(r'(?<=[.!?…])["\')\]]*\s+|\s+(?=[–—-]\s+)')
WORT = re.compile(r"[a-z0-9äöüß']+", re.IGNORECASE)
MAX_LAUF = 10


def _saeubern(text: str) -> str:
    """Escapes aus Spielelisten glätten, ohne Inhalt zu verwerfen."""
    text = str(text or "")
    text = text.replace("\\r\\n", " ").replace("\\n", " ").replace("\\r", " ")
    text = text.replace("\\_", " ")
    return " ".join(text.split())


def saetze(text: str) -> list[str]:
    """Text in grobe Sätze/Klauseln zerlegen; Satzzeichen bleiben erhalten."""
    text = _saeubern(text)
    if not text:
        return []
    return [teil.strip() for teil in SATZENDE.split(text) if teil.strip()] or [text]


def _normal(text: str) -> str:
    return " ".join(WORT.findall(str(text or "").casefold()))


def _woerter(text: str) -> int:
    return len(WORT.findall(str(text or "")))


def aehnlich(links: str, rechts: str) -> float:
    """Robuste Mischung aus Wortfolge und gemeinsamem Wortvorrat (0 bis 1)."""
    a, b = _normal(links), _normal(rechts)
    if not a or not b:
        return 0.0
    aw, bw = a.split(), b.split()
    # Wortlisten sind bei langen Cutscenes viel schneller als ein Vergleich
    # jedes einzelnen Zeichens und reagieren weniger auf Interpunktion.
    folge = difflib.SequenceMatcher(None, aw, bw, autojunk=False).ratio()
    zaehler_a, zaehler_b = {}, {}
    for wort in aw:
        zaehler_a[wort] = zaehler_a.get(wort, 0) + 1
    for wort in bw:
        zaehler_b[wort] = zaehler_b.get(wort, 0) + 1
    gemeinsam = sum(min(anzahl, zaehler_b.get(wort, 0))
                    for wort, anzahl in zaehler_a.items())
    bestand = (2.0 * gemeinsam / (len(aw) + len(bw))) if aw or bw else 0.0
    return 0.58 * folge + 0.42 * bestand


def _in_bloecke(text: str, ziel: int) -> list[str]:
    """Vollständigen Text auf ungefähr gleich schwere, wortsaubere Blöcke teilen."""
    text = _saeubern(text)
    teile = text.split()
    if not teile:
        return []
    ziel = max(1, min(int(ziel), len(teile)))
    if ziel == 1:
        return [text]

    gewichte = [max(1, len(re.sub(r"\W+", "", teil))) for teil in teile]
    gesamt = sum(gewichte)
    grenzen, lauf, naechste = [], 0, gesamt / ziel
    for index, gewicht in enumerate(gewichte, start=1):
        lauf += gewicht
        rest_woerter = len(teile) - index
        rest_bloecke = ziel - len(grenzen) - 1
        if (lauf >= naechste and rest_woerter >= rest_bloecke
                and len(grenzen) < ziel - 1):
            grenzen.append(index)
            naechste = gesamt * (len(grenzen) + 1) / ziel
    while len(grenzen) < ziel - 1:
        kandidat = len(teile) - (ziel - 1 - len(grenzen))
        if grenzen and kandidat <= grenzen[-1]:
            break
        grenzen.append(kandidat)
    ergebnis, von = [], 0
    for bis in grenzen + [len(teile)]:
        ergebnis.append(" ".join(teile[von:bis]))
        von = bis
    return [block for block in ergebnis if block]


def _buendeln(teile: list[str], ziel: int) -> list[str]:
    """Chronologische Satzteile auf exakt »ziel« grobe Gruppen bündeln."""
    if not teile:
        return []
    ziel = max(1, min(int(ziel), len(teile)))
    if ziel == len(teile):
        return list(teile)
    gewichte = [max(1, _woerter(teil)) for teil in teile]
    gesamt = sum(gewichte)
    gruppen = [[] for _ in range(ziel)]
    gruppe, lauf = 0, 0
    for index, teil in enumerate(teile):
        rest_teile = len(teile) - index
        rest_gruppen = ziel - gruppe - 1
        muss_wechseln = rest_teile <= rest_gruppen
        soll_wechseln = (bool(gruppen[gruppe])
                          and lauf >= gesamt * (gruppe + 1) / ziel)
        if (muss_wechseln or soll_wechseln) and gruppe < ziel - 1:
            gruppe += 1
        gruppen[gruppe].append(teil)
        lauf += gewichte[index]
    return [" ".join(gruppe) for gruppe in gruppen]


def paare(englisch: str, deutsch: str, ziel: int | None = None) -> list[tuple[str, str]]:
    """Beide Gesamttexte in satzverankerte, verlustfreie Blöcke zerlegen."""
    en_text, de_text = _saeubern(englisch), _saeubern(deutsch)
    if not en_text and not de_text:
        return []
    if not en_text:
        return [("", de_text)]
    if not de_text:
        return [(en_text, "")]
    if ziel is None:
        ziel = max(len(saetze(en_text)), len(saetze(de_text)))
    ziel = max(1, min(int(ziel), len(en_text.split()), len(de_text.split())))

    # Erst grob an Satzgrenzen koppeln. So bleibt etwa der dritte deutsche
    # Satz beim dritten englischen Gedanken, auch wenn die Übersetzung dort
    # doppelt so viele Wörter benötigt. Danach werden lange Satzpaare für die
    # Whisper-Ausrichtung weiter unterteilt.
    en_saetze, de_saetze = saetze(en_text), saetze(de_text)
    grob = max(1, min(ziel, len(en_saetze), len(de_saetze)))
    en_grob = _buendeln(en_saetze, grob)
    de_grob = _buendeln(de_saetze, grob)
    kapazitaet = [max(1, min(len(en.split()), len(de.split())))
                  for en, de in zip(en_grob, de_grob)]
    ziel = min(ziel, sum(kapazitaet))
    anzahl = [1 for _ in range(grob)]
    gewicht = [max(1, _woerter(en) + _woerter(de))
               for en, de in zip(en_grob, de_grob)]
    for _ in range(max(0, ziel - grob)):
        kandidaten = [index for index in range(grob)
                       if anzahl[index] < kapazitaet[index]]
        if not kandidaten:
            break
        # Der Block mit dem meisten Text pro bisherigem Unterblock bekommt
        # die nächste Teilung. Das verteilt die Auflösung gleichmäßig.
        index = max(kandidaten, key=lambda i: gewicht[i] / anzahl[i])
        anzahl[index] += 1

    ergebnis = []
    for en, de, teile in zip(en_grob, de_grob, anzahl):
        ergebnis.extend(zip(_in_bloecke(en, teile), _in_bloecke(de, teile)))
    return ergebnis


def verteile(gehoerte: list, englisch: str, deutsch: str,
             max_lauf: int = MAX_LAUF) -> list[str]:
    """Deutschen Gesamttext global und monoton auf Whisper-Abschnitte verteilen."""
    gehoerte = [_saeubern(g) for g in gehoerte]
    if not gehoerte:
        return []
    if not _saeubern(deutsch):
        return ["" for _ in gehoerte]
    if not _saeubern(englisch):
        bloecke = _in_bloecke(deutsch, min(len(gehoerte), len(str(deutsch).split())))
        return bloecke + [""] * (len(gehoerte) - len(bloecke))

    wortgrenze = min(len(_saeubern(englisch).split()), len(_saeubern(deutsch).split()))
    ziel = min(wortgrenze, max(len(gehoerte), len(gehoerte) * 2,
                               len(saetze(englisch)), len(saetze(deutsch))))
    zuordnung = paare(englisch, deutsch, ziel)
    if not zuordnung:
        return ["" for _ in gehoerte]

    n, m = len(gehoerte), len(zuordnung)
    gehoert_woerter = [max(1, _woerter(text)) for text in gehoerte]
    gesamt_gehoert = max(1, sum(gehoert_woerter))
    dp: dict[int, tuple[float, list[int]]] = {0: (0.0, [])}
    for index, gehoert in enumerate(gehoerte):
        neu: dict[int, tuple[float, list[int]]] = {}
        rest_segmente = n - index - 1
        erwartung = m * gehoert_woerter[index] / gesamt_gehoert
        for start, (basis, laeufe) in dp.items():
            uebrig = m - start
            minimum = 0 if m < n else 1
            hoechstens = min(max_lauf, uebrig)
            for lauf in range(minimum, hoechstens + 1):
                danach = uebrig - lauf
                if danach < (rest_segmente if m >= n else 0):
                    continue
                if danach > rest_segmente * max_lauf:
                    continue
                en_teil = " ".join(en for en, _de in zuordnung[start:start + lauf])
                sim = aehnlich(en_teil, gehoert) if lauf else 0.0
                laengenstrafe = abs(lauf - erwartung) * 0.12
                leerstrafe = 1.2 if lauf == 0 and gehoert else 0.0
                punkt = basis + sim * 4.5 - laengenstrafe - leerstrafe
                ende = start + lauf
                alt = neu.get(ende)
                if alt is None or punkt > alt[0]:
                    neu[ende] = (punkt, laeufe + [lauf])
        dp = neu
        if not dp:
            break

    if m not in dp:
        if max_lauf < m:
            return verteile(gehoerte, englisch, deutsch,
                            max(max_lauf + 1, math.ceil(m / max(1, n)) + 4))
        bloecke = _in_bloecke(deutsch, min(n, len(_saeubern(deutsch).split())))
        return bloecke + [""] * (n - len(bloecke))

    laeufe = dp[m][1]
    ergebnis, zeiger = [], 0
    for lauf in laeufe:
        ergebnis.append(" ".join(
            de for _en, de in zuordnung[zeiger:zeiger + lauf] if de
        ).strip())
        zeiger += lauf
    return ergebnis
