#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verwaltung der OmniVoice-Arbeiter fuer den Stapelbetrieb.

Zwei Betriebsarten hinter derselben Schnittstelle:

  * LokalerBetrieb - rechnet im Hauptprozess (ein Auftrag nach dem anderen).
    Braucht keinen zusaetzlichen Grafikspeicher. Das ist die Einstellung
    "1 Arbeiter".

  * ArbeiterPool  - startet mehrere eigene Prozesse (arbeiter.py), von denen
    jeder ein eigenes Modell im Grafikspeicher haelt und wirklich parallel
    rechnet. Das ist die Einstellung "2 und mehr Arbeiter".

Schnittstelle in beiden Faellen:

    betrieb.bereit_anzahl()      wie viele Arbeiter koennen Auftraege annehmen
    betrieb.lebende()            wie viele Arbeiter leben ueberhaupt noch
    betrieb.freier()             Nummer eines freien Arbeiters oder None
    betrieb.sende(nummer, auftrag)
    betrieb.antwort(timeout)     naechstes Ergebnis oder None
    betrieb.meldungen            Queue mit Protokolltexten
    betrieb.stoppen()
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

KEIN_FENSTER = 0x08000000 if os.name == "nt" else 0
ARBEITER_SKRIPT = Path(__file__).resolve().parent / "arbeiter.py"


# ------------------------------------------------------------
# Ein Arbeiter im Hauptprozess
# ------------------------------------------------------------

class LokalerBetrieb:
    """Rechnet im Hauptprozess - kein zusaetzlicher Grafikspeicher."""

    art = "lokal"

    def __init__(self) -> None:
        self.anzahl = 1
        self.antworten: queue.Queue = queue.Queue()
        self.meldungen: queue.Queue = queue.Queue()
        self._frei = True

    def bereit_anzahl(self) -> int:
        return 1

    def lebende(self) -> int:
        return 1

    def freier(self) -> Optional[int]:
        return 0 if self._frei else None

    def sende(self, nummer: int, auftrag: dict) -> None:
        self._frei = False

        def arbeite() -> None:
            from motor import fuehre_auftrag_aus

            ergebnis = fuehre_auftrag_aus(auftrag)
            self._frei = True
            self.antworten.put(ergebnis)

        threading.Thread(target=arbeite, daemon=True).start()

    def antwort(self, timeout: float = 0.4) -> Optional[dict]:
        try:
            return self.antworten.get(timeout=timeout)
        except queue.Empty:
            return None

    def stoppen(self) -> None:
        return

    def zustand(self) -> str:
        return "1 Arbeiter im Hauptprozess"


# ------------------------------------------------------------
# Mehrere Arbeiter als eigene Prozesse
# ------------------------------------------------------------

class ArbeiterPool:
    """Startet und verwaltet mehrere arbeiter.py-Prozesse."""

    art = "pool"

    def __init__(self, anzahl: int, python_pfad: str = "") -> None:
        self.anzahl = max(1, int(anzahl))
        self.python_pfad = python_pfad or sys.executable
        self.antworten: queue.Queue = queue.Queue()
        self.meldungen: queue.Queue = queue.Queue()
        self.sperre = threading.RLock()
        self.arbeiter: list[dict] = []
        self.gestartet = 0.0

    # -- Start und Ende ------------------------------------------
    def starten(self) -> None:
        self.gestartet = time.time()
        for nummer in range(self.anzahl):
            eintrag = {"nummer": nummer, "prozess": None, "bereit": False,
                       "frei": False, "tot": False, "auftrag": None, "geraet": ""}
            try:
                prozess = subprocess.Popen(
                    [self.python_pfad, "-u", str(ARBEITER_SKRIPT), f"--nummer={nummer}"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=KEIN_FENSTER,
                    bufsize=1,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError as fehler:
                eintrag["tot"] = True
                self.meldungen.put(f"Arbeiter {nummer + 1} ließ sich nicht starten: {fehler}")
                self.arbeiter.append(eintrag)
                continue
            eintrag["prozess"] = prozess
            self.arbeiter.append(eintrag)
            threading.Thread(target=self._lesen, args=(eintrag,), daemon=True).start()
        self.meldungen.put(f"{self.anzahl} Arbeiter werden vorbereitet – "
                           f"jeder lädt sein eigenes Modell.")

    def _lesen(self, eintrag: dict) -> None:
        """Liest die Ausgabe eines Arbeiters, bis er sich beendet."""
        prozess = eintrag["prozess"]
        nummer = eintrag["nummer"]
        try:
            for roh in prozess.stdout:
                text = roh.strip()
                if not text:
                    continue
                if not text.startswith("{"):
                    self.meldungen.put(f"[Arbeiter {nummer + 1}] {text}")
                    continue
                try:
                    nachricht = json.loads(text)
                except ValueError:
                    self.meldungen.put(f"[Arbeiter {nummer + 1}] {text}")
                    continue

                typ = nachricht.get("typ")
                if typ == "bereit":
                    with self.sperre:
                        eintrag["bereit"] = True
                        eintrag["frei"] = True
                        eintrag["geraet"] = nachricht.get("geraet", "")
                    self.meldungen.put(
                        f"Arbeiter {nummer + 1} ist bereit "
                        f"(nach {time.time() - self.gestartet:.0f} s).")
                elif typ == "ergebnis":
                    with self.sperre:
                        eintrag["frei"] = True
                        eintrag["auftrag"] = None
                    self.antworten.put(nachricht)
                elif typ == "tot":
                    self.meldungen.put(f"Arbeiter {nummer + 1} konnte nicht starten: "
                                       f"{nachricht.get('fehler', '')}")
        except Exception as fehler:
            self.meldungen.put(f"[Arbeiter {nummer + 1}] Verbindung verloren: {fehler}")
        finally:
            self._verabschieden(eintrag)

    def _verabschieden(self, eintrag: dict) -> None:
        """Arbeiter ist weg - offenen Auftrag als Fehler zurueckmelden."""
        with self.sperre:
            eintrag["tot"] = True
            eintrag["bereit"] = False
            eintrag["frei"] = False
            offen = eintrag.get("auftrag")
            eintrag["auftrag"] = None
        if offen is not None:
            self.antworten.put({
                "typ": "ergebnis", "id": offen, "ok": False, "sekunden": 0.0, "ton": 0.0,
                "fehler": f"Arbeiter {eintrag['nummer'] + 1} hat sich unerwartet beendet",
            })
        self.meldungen.put(f"Arbeiter {eintrag['nummer'] + 1} ist beendet.")

    # -- Zustand -------------------------------------------------
    def bereit_anzahl(self) -> int:
        with self.sperre:
            return sum(1 for a in self.arbeiter if a["bereit"] and not a["tot"])

    def lebende(self) -> int:
        with self.sperre:
            return sum(1 for a in self.arbeiter if not a["tot"])

    def beschaeftigt(self) -> int:
        with self.sperre:
            return sum(1 for a in self.arbeiter if a["bereit"] and not a["frei"] and not a["tot"])

    def freier(self) -> Optional[int]:
        with self.sperre:
            for eintrag in self.arbeiter:
                if eintrag["bereit"] and eintrag["frei"] and not eintrag["tot"]:
                    return eintrag["nummer"]
        return None

    def zustand(self) -> str:
        bereit = self.bereit_anzahl()
        if bereit == self.anzahl:
            return f"{bereit} von {self.anzahl} Arbeitern bereit"
        if self.lebende() == 0:
            return "kein Arbeiter läuft"
        return f"{bereit} von {self.anzahl} Arbeitern bereit – der Rest lädt noch"

    # -- Betrieb -------------------------------------------------
    def sende(self, nummer: int, auftrag: dict) -> None:
        with self.sperre:
            eintrag = self.arbeiter[nummer]
            eintrag["frei"] = False
            eintrag["auftrag"] = auftrag.get("id")
            prozess = eintrag["prozess"]
        try:
            prozess.stdin.write(json.dumps(auftrag, ensure_ascii=False) + "\n")
            prozess.stdin.flush()
        except Exception as fehler:
            self.meldungen.put(f"Arbeiter {nummer + 1} nicht erreichbar: {fehler}")
            self._verabschieden(self.arbeiter[nummer])

    def antwort(self, timeout: float = 0.4) -> Optional[dict]:
        try:
            return self.antworten.get(timeout=timeout)
        except queue.Empty:
            return None

    def stoppen(self) -> None:
        for eintrag in self.arbeiter:
            prozess = eintrag.get("prozess")
            if prozess is None:
                continue
            try:
                if prozess.poll() is None:
                    prozess.stdin.write("ENDE\n")
                    prozess.stdin.flush()
                    prozess.stdin.close()
            except Exception:
                pass
        ende = time.time() + 8.0
        for eintrag in self.arbeiter:
            prozess = eintrag.get("prozess")
            if prozess is None:
                continue
            try:
                prozess.wait(timeout=max(0.5, ende - time.time()))
            except Exception:
                try:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(prozess.pid)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=KEIN_FENSTER, timeout=10)
                    else:
                        prozess.kill()
                except Exception:
                    pass
        with self.sperre:
            for eintrag in self.arbeiter:
                eintrag["tot"] = True
                eintrag["bereit"] = False
                eintrag["frei"] = False


# ------------------------------------------------------------
# Verwaltung: haelt den laufenden Pool ueber mehrere Stapel hinweg
# ------------------------------------------------------------

class Verwaltung:
    def __init__(self) -> None:
        self.pool: Optional[ArbeiterPool] = None
        self.lokal = LokalerBetrieb()

    def betrieb(self, anzahl: int):
        """Liefert den passenden Betrieb und startet ihn bei Bedarf."""
        anzahl = max(1, int(anzahl))
        if anzahl <= 1:
            return self.lokal
        if self.pool is not None and self.pool.anzahl == anzahl and self.pool.lebende() > 0:
            return self.pool
        self.stoppen()
        self.pool = ArbeiterPool(anzahl)
        self.pool.starten()
        return self.pool

    def laufend(self) -> Optional[ArbeiterPool]:
        if self.pool is not None and self.pool.lebende() > 0:
            return self.pool
        return None

    def stoppen(self) -> None:
        if self.pool is not None:
            self.pool.stoppen()
            self.pool = None

    def zustand(self) -> str:
        pool = self.laufend()
        if pool is None:
            return "keine zusätzlichen Arbeiter – es rechnet der Hauptprozess"
        return pool.zustand()


VERWALTUNG = Verwaltung()
