#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Leichte, optionale Audioeffekte ohne zusätzliche Abhängigkeiten."""

from __future__ import annotations


FELDER = [
    "effekt_reverb_an", "effekt_reverb_dauer", "effekt_reverb_decay",
    "effekt_reverb_mix", "effekt_ghost_an", "effekt_ghost_fade",
    "effekt_ghost_mix", "effekt_ghost_streckung", "effekt_ghost_partikel",
    "effekt_ghost_ueberblendung", "effekt_ghost_hall", "effekt_echo_an",
    "effekt_echo_delay", "effekt_echo_decay", "effekt_echo_wiederholungen",
    "effekt_echo_mix", "effekt_bitcrush_an", "effekt_bitcrush_bits",
    "effekt_bitcrush_rate", "effekt_bitcrush_mix",
]

STANDARD = {
    "effekt_reverb_an": False,
    "effekt_reverb_dauer": 1.2,
    "effekt_reverb_decay": 0.55,
    "effekt_reverb_mix": 0.25,
    "effekt_ghost_an": False,
    "effekt_ghost_fade": 0.8,
    "effekt_ghost_mix": 0.35,
    "effekt_ghost_streckung": 2.5,
    "effekt_ghost_partikel": 180,
    "effekt_ghost_ueberblendung": 0.75,
    "effekt_ghost_hall": True,
    "effekt_echo_an": False,
    "effekt_echo_delay": 250,
    "effekt_echo_decay": 0.40,
    "effekt_echo_wiederholungen": 3,
    "effekt_echo_mix": 0.30,
    "effekt_bitcrush_an": False,
    "effekt_bitcrush_bits": 8,
    "effekt_bitcrush_rate": 12000,
    "effekt_bitcrush_mix": 1.0,
}


def _zahl(wert, vorgabe: float, minimum: float, maximum: float) -> float:
    try:
        wert = float(wert)
    except (TypeError, ValueError):
        wert = float(vorgabe)
    return max(minimum, min(maximum, wert))


def konfiguration(werte=None) -> dict:
    """Vervollständigt und begrenzt eine Effektkonfiguration."""
    roh = dict(werte or {})
    cfg = dict(STANDARD)
    cfg.update({name: roh.get(name, STANDARD[name]) for name in FELDER})
    for name in ("effekt_reverb_an", "effekt_ghost_an", "effekt_ghost_hall",
                 "effekt_echo_an", "effekt_bitcrush_an"):
        cfg[name] = bool(cfg[name])
    cfg.update({
        "effekt_reverb_dauer": _zahl(cfg["effekt_reverb_dauer"], 1.2, 0.1, 5.0),
        "effekt_reverb_decay": _zahl(cfg["effekt_reverb_decay"], 0.55, 0.05, 0.95),
        "effekt_reverb_mix": _zahl(cfg["effekt_reverb_mix"], 0.25, 0.0, 1.0),
        "effekt_ghost_fade": _zahl(cfg["effekt_ghost_fade"], 0.8, 0.0, 5.0),
        "effekt_ghost_mix": _zahl(cfg["effekt_ghost_mix"], 0.35, 0.0, 1.0),
        "effekt_ghost_streckung": _zahl(cfg["effekt_ghost_streckung"], 2.5, 0.0, 4.0),
        "effekt_ghost_partikel": int(round(_zahl(
            cfg["effekt_ghost_partikel"], 180, 60, 500))),
        "effekt_ghost_ueberblendung": _zahl(
            cfg["effekt_ghost_ueberblendung"], 0.75, 0.50, 0.90),
        "effekt_echo_delay": int(round(_zahl(cfg["effekt_echo_delay"], 250, 20, 2000))),
        "effekt_echo_decay": _zahl(cfg["effekt_echo_decay"], 0.4, 0.05, 0.95),
        "effekt_echo_wiederholungen": int(round(_zahl(
            cfg["effekt_echo_wiederholungen"], 3, 1, 12))),
        "effekt_echo_mix": _zahl(cfg["effekt_echo_mix"], 0.3, 0.0, 1.0),
        "effekt_bitcrush_bits": int(round(_zahl(cfg["effekt_bitcrush_bits"], 8, 2, 16))),
        "effekt_bitcrush_rate": int(round(_zahl(
            cfg["effekt_bitcrush_rate"], 12000, 1000, 48000))),
        "effekt_bitcrush_mix": _zahl(cfg["effekt_bitcrush_mix"], 1.0, 0.0, 1.0),
    })
    return cfg


def aktive_namen(werte=None) -> list[str]:
    cfg = konfiguration(werte)
    namen = []
    # Reihenfolge entspricht der tatsächlichen Effektkette.
    if cfg["effekt_bitcrush_an"]:
        namen.append("Bitcrush")
    if cfg["effekt_ghost_an"]:
        namen.append("Reverse Reverb/Ghost Voice")
    if cfg["effekt_reverb_an"]:
        namen.append("Hall/Reverb")
    if cfg["effekt_echo_an"]:
        namen.append("Echo")
    return namen


def aktiv(werte=None) -> bool:
    return bool(aktive_namen(werte))


def _trocken_auffuellen(daten, laenge: int):
    import numpy as np

    trocken = np.zeros(laenge, dtype="float32")
    trocken[:len(daten)] = daten
    return trocken


def _hall_nass(daten, rate: int, dauer: float, decay: float):
    """Erzeugt ein dichtes, aber günstiges Netz unregelmäßiger Reflexionen."""
    import numpy as np

    daten = np.asarray(daten, dtype="float32")
    nachhall = max(1, int(round(float(dauer) * rate)))
    nass = np.zeros(len(daten) + nachhall, dtype="float32")
    # Unregelmäßige Abstände vermeiden den metallischen Klang eines einzelnen
    # festen Delays. 18 Taps bleiben auch bei langen Stapeln sehr günstig.
    anteile = np.array([
        .031, .047, .071, .103, .139, .181, .229, .283, .347,
        .419, .503, .593, .677, .757, .829, .893, .947, 1.0,
    ], dtype="float64")
    gewicht = 0.0
    for anteil in anteile:
        versatz = max(1, min(nachhall, int(round(nachhall * float(anteil)))))
        gain = float(decay) ** (0.5 + 5.5 * float(anteil))
        nass[versatz:versatz + len(daten)] += daten * gain
        gewicht += gain
    if gewicht > 1.0:
        nass /= float(gewicht ** 0.5)
    return nass


def _hall(daten, rate: int, dauer: float, decay: float, mix: float):
    import numpy as np

    daten = np.asarray(daten, dtype="float32")
    nass = _hall_nass(daten, rate, dauer, decay)
    trocken = _trocken_auffuellen(daten, len(nass))
    return (trocken * (1.0 - mix) + nass * mix).astype("float32", copy=False)


def _bitcrush(daten, rate: int, bits: int, zielrate: int, mix: float):
    import numpy as np

    trocken = np.asarray(daten, dtype="float32")
    faktor = max(1, int(round(float(rate) / max(1, int(zielrate)))))
    index = (np.arange(len(trocken), dtype="int64") // faktor) * faktor
    gehalten = trocken[index]
    stufen = max(1, (2 ** (int(bits) - 1)) - 1)
    zerlegt = np.round(np.clip(gehalten, -1.0, 1.0) * stufen) / stufen
    return (trocken * (1.0 - mix) + zerlegt * mix).astype("float32", copy=False)


def _ghost(daten, rate: int, cfg: dict):
    """Granular verlängerte Partikel bei unveränderter Gesamtdauer."""
    import numpy as np

    trocken = np.asarray(daten, dtype="float32")
    original_laenge = len(trocken)
    dauer = cfg["effekt_reverb_dauer"]
    decay = cfg["effekt_reverb_decay"]
    streckung = cfg["effekt_ghost_streckung"]
    partikel = max(64, int(round(cfg["effekt_ghost_partikel"] * rate / 1000.0)))
    ueberblendung = cfg["effekt_ghost_ueberblendung"]
    analyse_schritt = max(1, int(round(partikel * (1.0 - ueberblendung))))
    starts = list(range(0, max(1, len(trocken)), analyse_schritt))
    vorlauf = max(1, int(round(dauer * rate)))
    trocken_lang = np.zeros(original_laenge, dtype="float32")
    gewicht = np.zeros(original_laenge, dtype="float32")
    verlaengert = np.zeros(original_laenge, dtype="float32")
    verlaengert_gewicht = np.zeros(original_laenge, dtype="float32")
    preverb_lang = np.zeros(original_laenge, dtype="float32")
    fenster = np.hanning(partikel).astype("float32")
    if not np.any(fenster):
        fenster[:] = 1.0

    for nummer, quelle in enumerate(starts):
        roh = np.zeros(partikel, dtype="float32")
        vorhanden = min(partikel, max(0, len(trocken) - quelle))
        if vorhanden:
            roh[:vorhanden] = trocken[quelle:quelle + vorhanden]
        part = roh * fenster
        trocken_start = quelle
        trocken_ende = min(original_laenge, trocken_start + partikel)
        if trocken_ende > trocken_start:
            breite = trocken_ende - trocken_start
            trocken_lang[trocken_start:trocken_ende] += part[:breite]
            gewicht[trocken_start:trocken_ende] += fenster[:breite]

        # Der Hall entsteht pro Partikel auf der rückwärts laufenden Aufnahme.
        # Nach erneutem Umkehren liegt sein Auslauf *vor* diesem Partikel und
        # überblendet schon in die benachbarten Partikel hinein.
        rueckwaerts = _hall_nass(part[::-1], rate, dauer, decay)[::-1]
        pre_start = trocken_start - vorlauf
        quelle_start = max(0, -pre_start)
        ziel_start = max(0, pre_start)
        ende = min(original_laenge, ziel_start + len(rueckwaerts) - quelle_start)
        if ende > ziel_start:
            preverb_lang[ziel_start:ende] += rueckwaerts[
                quelle_start:quelle_start + ende - ziel_start]

        # »Stimme langziehen« verlängert nicht mehr die Datei. Stattdessen
        # wandert dasselbe Partikel mehrfach gedämpft nach rechts und liegt
        # dadurch über den folgenden Lauten – genau der langgezogene
        # fffff/wwwaaas-Eindruck, ohne die Timeline zu verschieben.
        if streckung > 0.001:
            wiederholungen = max(1, int(round(streckung * 4.0)))
            for wiederholung in range(1, wiederholungen + 1):
                ziel_start = trocken_start + wiederholung * analyse_schritt
                if ziel_start >= original_laenge:
                    break
                ziel_ende = min(original_laenge, ziel_start + partikel)
                breite = ziel_ende - ziel_start
                gain = (1.0 - wiederholung / float(wiederholungen + 1)) ** 1.4
                verlaengert[ziel_start:ziel_ende] += part[:breite] * gain
                verlaengert_gewicht[ziel_start:ziel_ende] += fenster[:breite]

    maske = gewicht > 1e-5
    trocken_lang[maske] /= gewicht[maske]
    trocken_lang[~maske] = trocken[~maske]
    dichte = np.maximum(1.0, verlaengert_gewicht)
    verlaengert /= dichte
    # Viele gleichzeitig ausklingende Partikel dürfen den Pegel nicht mit der
    # Anzahl der Überlappungen vervielfachen.
    pre_spitze = float(np.max(np.abs(preverb_lang))) if len(preverb_lang) else 0.0
    trocken_spitze = float(np.max(np.abs(trocken_lang))) if len(trocken_lang) else 0.0
    if pre_spitze > 0.0 and trocken_spitze > 0.0:
        preverb_lang *= min(1.0, trocken_spitze / pre_spitze)
    mix = cfg["effekt_ghost_mix"]
    streck_anteil = min(0.85, 0.18 + streckung * 0.16) if streckung > 0 else 0.0
    ergebnis = trocken_lang + verlaengert * streck_anteil + preverb_lang * mix
    blende = min(len(ergebnis), int(round(cfg["effekt_ghost_fade"] * rate)))
    if blende > 1:
        ergebnis = np.array(ergebnis, dtype="float32", copy=True)
        ergebnis[:blende] *= np.linspace(0.0, 1.0, blende, dtype="float32")
    if cfg["effekt_ghost_hall"]:
        ergebnis = _hall(ergebnis, rate, dauer, decay,
                         min(0.65, max(0.08, cfg["effekt_reverb_mix"])))
    # Ghost Voice ist ein In-Place-Effekt. Weder Partikelverlängerung noch
    # interner Hall dürfen Schnittmarken oder die ursprüngliche Dauer ändern.
    if len(ergebnis) < original_laenge:
        ergebnis = np.pad(ergebnis, (0, original_laenge - len(ergebnis)))
    return np.asarray(ergebnis[:original_laenge], dtype="float32")


def _echo(daten, rate: int, delay_ms: int, decay: float, wiederholungen: int,
          mix: float):
    import numpy as np

    trocken = np.asarray(daten, dtype="float32")
    schritt = max(1, int(round(delay_ms * rate / 1000.0)))
    laenge = len(trocken) + schritt * int(wiederholungen)
    nass = np.zeros(laenge, dtype="float32")
    for nummer in range(1, int(wiederholungen) + 1):
        start = schritt * nummer
        nass[start:start + len(trocken)] += trocken * (float(decay) ** nummer)
    return (_trocken_auffuellen(trocken, laenge) * (1.0 - mix)
            + nass * mix).astype("float32", copy=False)


def _spitze_begrenzen(daten, grenze_db: float = -1.0):
    import numpy as np

    daten = np.asarray(daten, dtype="float32")
    if not len(daten):
        return daten, 0.0
    grenze = 10.0 ** (float(grenze_db) / 20.0)
    spitze = float(np.max(np.abs(daten)))
    if spitze <= grenze or spitze <= 0.0:
        return daten, 0.0
    faktor = grenze / spitze
    gebremst = 20.0 * float(np.log10(spitze / grenze))
    return (daten * faktor).astype("float32", copy=False), gebremst


def anwenden(daten, rate: int, werte=None, bericht: dict = None):
    """Wendet die aktive Kette Bitcrush → Ghost → Hall → Echo an."""
    import numpy as np

    cfg = konfiguration(werte)
    namen = aktive_namen(cfg)
    if bericht is None:
        bericht = {}
    if not namen or daten is None or len(daten) == 0:
        bericht.update({"aktiv": False, "namen": []})
        return daten

    ergebnis = np.asarray(daten, dtype="float32")
    if cfg["effekt_bitcrush_an"]:
        ergebnis = _bitcrush(
            ergebnis, rate, cfg["effekt_bitcrush_bits"],
            cfg["effekt_bitcrush_rate"], cfg["effekt_bitcrush_mix"])
    if cfg["effekt_ghost_an"]:
        ergebnis = _ghost(ergebnis, rate, cfg)
    if cfg["effekt_reverb_an"]:
        ergebnis = _hall(
            ergebnis, rate, cfg["effekt_reverb_dauer"],
            cfg["effekt_reverb_decay"], cfg["effekt_reverb_mix"])
    if cfg["effekt_echo_an"]:
        ergebnis = _echo(
            ergebnis, rate, cfg["effekt_echo_delay"], cfg["effekt_echo_decay"],
            cfg["effekt_echo_wiederholungen"], cfg["effekt_echo_mix"])

    ergebnis, gebremst = _spitze_begrenzen(ergebnis)
    bericht.update({
        "aktiv": True,
        "namen": namen,
        "kette": " → ".join(namen),
        "gebremst_db": round(float(gebremst), 1),
        "dauer_vorher": round(len(daten) / float(rate), 3),
        "dauer_nachher": round(len(ergebnis) / float(rate), 3),
    })
    return ergebnis
