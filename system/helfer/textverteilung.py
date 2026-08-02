#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Einen langen deutschen Text auf die Segmente einer Szene verteilen.

Ausgangslage beim Vertonen langer Aufnahmen: In der Liste steht zu **einer**
Datei der komplette englische und der komplette deutsche Text, oft ein Dutzend
Saetze am Stueck. Whisper zerlegt die Aufnahme in Sprechabschnitte und liefert
dazu den englischen Wortlaut - der deutsche Text lag bisher ungenutzt daneben
und musste von Hand auf die Abschnitte verteilt werden.

Hier passiert genau das automatisch: Beide Texte werden in Saetze zerlegt und
paarweise zugeordnet. Danach bekommt jeder Sprechabschnitt die deutschen
Saetze, deren englische Gegenstuecke am besten zu dem passen, was Whisper an
dieser Stelle gehoert hat. Die Reihenfolge bleibt dabei erhalten - ein
Abschnitt kann nie Saetze bekommen, die vor denen des Vorgaengers stehen.
"""

from __future__ import annotations

import difflib
import re

# Satzende: Punkt, Ruf-, Fragezeichen oder Auslassungspunkte, gefolgt von
# Leerraum. Auf einen Grossbuchstaben wird bewusst nicht bestanden - in
# Spieltexten geht es oft mit "..." und klein weiter.
SATZENDE = re.compile(r'(?<=[.!?…])["\')\]]*\s+')
MAX_LAUF = 8          # so viele Saetze darf ein Abschnitt hoechstens bekommen


def saetze(text: str) -> list:
    """Text in Saetze zerlegen, Satzzeichen bleiben dran."""
    text = " ".join(str(text or "").split())
    if not text:
        return []
    teile = [t.strip() for t in SATZENDE.split(text) if t and t.strip()]
    return teile or [text]


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß ]+", " ", str(text or "").lower())


def aehnlich(links: str, rechts: str) -> float:
    """Wie sehr aehneln sich zwei Texte (0 bis 1)?"""
    a, b = " ".join(_normal(links).split()), " ".join(_normal(rechts).split())
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def paare(englisch: str, deutsch: str) -> list:
    """
    Englische und deutsche Saetze einander zuordnen.

    Im Normalfall stehen auf beiden Seiten gleich viele Saetze - dann ist die
    Zuordnung eindeutig. Weicht die Zahl ab (eine Uebersetzung fasst zwei
    Saetze zusammen oder teilt einen), werden die Saetze der laengeren Seite
    nach Textlaenge auf die kuerzere verteilt. So bleibt die Reihenfolge
    erhalten und es geht nichts verloren.
    """
    en, de = saetze(englisch), saetze(deutsch)
    if not en and not de:
        return []
    if not de:
        return [(satz, "") for satz in en]
    if not en:
        return [("", satz) for satz in de]
    if len(en) == len(de):
        return list(zip(en, de))

    # Ungleich: die laengere Seite wird gebuendelt.
    if len(de) > len(en):
        return list(zip(en, _buendeln(de, len(en))))
    return list(zip(_buendeln(en, len(de)), de))


def _buendeln(teile: list, ziel: int) -> list:
    """
    »teile« auf genau »ziel« Gruppen zusammenfassen, nach Textlaenge gewichtet.

    Jede Gruppe bekommt garantiert mindestens einen Teil - eine leere Gruppe
    wuerde spaeter einen Satz ohne Gegenstueck bedeuten und die Zuordnung
    verschieben.
    """
    ziel = max(1, min(ziel, len(teile)))
    if ziel == len(teile):
        return list(teile)
    laengen = [max(1, len(t)) for t in teile]
    gesamt = sum(laengen)
    gruppen = [[] for _ in range(ziel)]
    aktuell, lauf = 0, 0
    for i, teil in enumerate(teile):
        rest_teile = len(teile) - i
        rest_gruppen = ziel - aktuell - 1
        # Weiterruecken, wenn sonst eine Gruppe leer bliebe ...
        muss = rest_teile <= rest_gruppen
        # ... oder wenn diese Gruppe ihren Anteil beisammen hat.
        darf = bool(gruppen[aktuell]) and lauf >= gesamt * (aktuell + 1) / ziel
        if (muss or darf) and aktuell < ziel - 1:
            aktuell += 1
        gruppen[aktuell].append(teil)
        lauf += laengen[i]
    return [" ".join(g) for g in gruppen]


def verteile(gehoerte: list, englisch: str, deutsch: str,
             max_lauf: int = MAX_LAUF) -> list:
    """
    Den deutschen Text auf die Sprechabschnitte verteilen.

    »gehoerte« sind die englischen Wortlaute der Abschnitte in Zeitreihenfolge
    (von Whisper). Zurueck kommt je Abschnitt der deutsche Text.

    Der Ablauf ist bewusst schlicht und vorwaertsgerichtet: Fuer jeden
    Abschnitt wird geprueft, ob ein Satz, zwei Saetze oder mehr am besten zu
    dem passen, was dort gesprochen wird. Der beste Lauf wird genommen, der
    Zeiger rueckt weiter. Dadurch kann nichts durcheinandergeraten, und der
    letzte Abschnitt bekommt immer den Rest.
    """
    gehoerte = [str(g or "") for g in gehoerte]
    zuordnung = paare(englisch, deutsch)
    if not gehoerte:
        return []
    if not zuordnung:
        return ["" for _ in gehoerte]

    # Gibt es genauso viele Saetze wie Abschnitte, ist die Sache klar.
    if len(zuordnung) == len(gehoerte):
        return [de for _en, de in zuordnung]

    ergebnis, zeiger = [], 0
    for nummer, gehoert in enumerate(gehoerte):
        rest_abschnitte = len(gehoerte) - nummer - 1
        uebrig = len(zuordnung) - zeiger
        if uebrig <= 0:
            ergebnis.append("")
            continue
        if nummer == len(gehoerte) - 1:
            ergebnis.append(" ".join(de for _en, de in zuordnung[zeiger:] if de).strip())
            zeiger = len(zuordnung)
            continue

        # Wie viele Saetze duerfen es sein? Fuer jeden weiteren Abschnitt muss
        # mindestens ein Satz uebrig bleiben.
        hoechstens = max(1, min(max_lauf, uebrig - rest_abschnitte))
        bester_lauf, bester_wert = 1, -1.0
        for laenge in range(1, hoechstens + 1):
            en_teil = " ".join(en for en, _de in zuordnung[zeiger:zeiger + laenge] if en)
            wert = aehnlich(en_teil, gehoert)
            # Ein laengerer Lauf muss spuerbar besser passen, sonst gewinnt der
            # kuerzere - das haelt die Verteilung gleichmaessig.
            wert -= 0.02 * (laenge - 1)
            if wert > bester_wert:
                bester_lauf, bester_wert = laenge, wert
        ergebnis.append(
            " ".join(de for _en, de in zuordnung[zeiger:zeiger + bester_lauf] if de).strip())
        zeiger += bester_lauf
    return ergebnis
