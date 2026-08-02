#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Übersetzen über deep-translator.

Bewusst getrennt gehalten: Das ist die **einzige** Stelle im Toolkit, die
Daten aus dem Haus gibt. Aufgerufen wird nur, wenn jemand ausdrücklich auf
»übersetzen« drückt - Audio verlässt den Rechner nie, es gehen ausschließlich
die Texte an den gewählten Dienst.

Google braucht keinen Schlüssel und ist deshalb voreingestellt. DeepL und
Microsoft liefern die besseren Ergebnisse, verlangen aber einen eigenen
Schlüssel; der wird in den Einstellungen abgelegt und sonst nirgends benutzt.
"""

from __future__ import annotations

import re
import threading
import time

DIENSTE = ["Google (ohne Schlüssel)", "DeepL (Schlüssel nötig)",
           "Microsoft (Schlüssel nötig)", "MyMemory (ohne Schlüssel)"]

# Wie viele Zeichen ein Dienst am Stück verträgt. Absichtlich vorsichtig -
# lieber ein Aufruf mehr als eine abgeschnittene Zeile.
GRENZE = 4000
PAUSE = 0.34          # Sekunden zwischen zwei Aufrufen, gegen Sperren

_sperre = threading.RLock()
_letzter = [0.0]


def verfuegbar() -> bool:
    try:
        import deep_translator  # noqa: F401

        return True
    except Exception:
        return False


def fehlt_hinweis() -> str:
    return ("deep-translator ist nicht eingerichtet. Im Studio einmal "
            "»Reparieren« laufen lassen – danach steht das Übersetzen bereit.")


def _bauen(dienst: str, von: str, nach: str, schluessel: str):
    from deep_translator import (DeeplTranslator, GoogleTranslator,
                                 MicrosoftTranslator, MyMemoryTranslator)

    dienst = str(dienst or "")
    if dienst.startswith("DeepL"):
        if not schluessel.strip():
            raise ValueError("Für DeepL fehlt der Schlüssel (Einstellungen).")
        return DeeplTranslator(api_key=schluessel.strip(), source=von, target=nach)
    if dienst.startswith("Microsoft"):
        if not schluessel.strip():
            raise ValueError("Für Microsoft fehlt der Schlüssel (Einstellungen).")
        return MicrosoftTranslator(api_key=schluessel.strip(), source=von, target=nach)
    if dienst.startswith("MyMemory"):
        # MyMemory will vollstaendige Sprachkennungen.
        lang = {"en": "en-GB", "de": "de-DE"}
        return MyMemoryTranslator(source=lang.get(von, von), target=lang.get(nach, nach))
    return GoogleTranslator(source=von, target=nach)


def _stuecke(text: str, grenze: int = GRENZE) -> list:
    """Langen Text an Satzgrenzen teilen, damit nichts abgeschnitten wird."""
    text = str(text or "")
    if len(text) <= grenze:
        return [text]
    teile, rest = [], text
    while len(rest) > grenze:
        schnitt = rest.rfind(" ", 0, grenze)
        for zeichen in (". ", "! ", "? ", "\n"):
            stelle = rest.rfind(zeichen, 0, grenze)
            if stelle > grenze // 2:
                schnitt = stelle + len(zeichen)
                break
        if schnitt <= 0:
            schnitt = grenze
        teile.append(rest[:schnitt])
        rest = rest[schnitt:]
    if rest:
        teile.append(rest)
    return teile


def uebersetze(text: str, dienst: str = DIENSTE[0], von: str = "en", nach: str = "de",
               schluessel: str = "") -> str:
    """
    Einen Text übersetzen. Wirft bei Fehlern - der Aufrufer entscheidet.

    Reine Satzzeichen, Zahlen oder leere Texte gehen gar nicht erst raus.
    """
    text = str(text or "").strip()
    if not text or not re.search(r"[A-Za-zÀ-ÿ]", text):
        return text
    werkzeug = _bauen(dienst, von, nach, schluessel)
    ergebnis = []
    for stueck in _stuecke(text):
        with _sperre:
            wartezeit = PAUSE - (time.time() - _letzter[0])
            if wartezeit > 0:
                time.sleep(wartezeit)
            teil = werkzeug.translate(stueck)
            _letzter[0] = time.time()
        ergebnis.append(str(teil or ""))
    return "".join(ergebnis).strip()


def uebersetze_viele(texte, dienst: str = DIENSTE[0], von: str = "en", nach: str = "de",
                     schluessel: str = "", melde=None) -> list:
    """
    Mehrere Texte nacheinander. Liefert je Eintrag (Text, Fehlermeldung).

    Ein einzelner Fehlschlag beendet den Lauf nicht - sonst wäre bei einer
    langen Liste alles verloren, sobald ein Dienst einmal zickt.
    """
    ergebnisse = []
    for nummer, text in enumerate(texte, start=1):
        try:
            ergebnisse.append((uebersetze(text, dienst, von, nach, schluessel), ""))
        except Exception as fehler:
            ergebnisse.append(("", f"{type(fehler).__name__}: {fehler}"))
        if melde:
            melde(nummer, len(texte))
    return ergebnisse
