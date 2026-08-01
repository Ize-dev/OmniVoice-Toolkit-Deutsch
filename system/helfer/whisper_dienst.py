#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Client, Textaehnlichkeit und persistente Ratings fuer Faster-Whisper."""

import atexit
import collections
import difflib
import json
import os
import queue
import re
import subprocess
import threading
import time
import unicodedata
import uuid
from pathlib import Path

SYSTEM_DIR = Path(__file__).resolve().parent.parent
WHISPER_PYTHON = (
    SYSTEM_DIR / "whisper-umgebung" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
)
WORKER = Path(__file__).resolve().parent / "whisper_worker.py"
ANTWORT = "#WHISPER#"
KEIN_FENSTER = 0x08000000 if os.name == "nt" else 0

MODELLE = [
    "tiny", "base", "small", "medium", "medium.en",
    "large-v2", "large-v3", "distil-large-v3",
]
GERAETE = {
    "Automatisch (NVIDIA, sonst CPU)": "auto",
    "Nur Prozessor (CPU/INT8)": "cpu",
    "NVIDIA CUDA (FP16)": "cuda",
}


def normalisiere_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    text = re.sub(r"[^\w\s']+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def aehnlichkeit(erwartet: str, erkannt: str) -> float:
    """Robuste Prozentzahl aus Zeichenfolge, Wortreihenfolge und Wortmenge."""
    links, rechts = normalisiere_text(erwartet), normalisiere_text(erkannt)
    if not links or not rechts:
        return 0.0
    zeichen = difflib.SequenceMatcher(None, links, rechts, autojunk=False).ratio()
    l_worte, r_worte = links.split(), rechts.split()
    sortiert = difflib.SequenceMatcher(
        None, " ".join(sorted(l_worte)), " ".join(sorted(r_worte)), autojunk=False
    ).ratio()
    l_menge, r_menge = set(l_worte), set(r_worte)
    wortmenge = len(l_menge & r_menge) / max(1, min(len(l_menge), len(r_menge)))
    wert = 100.0 * (0.55 * zeichen + 0.30 * sortiert + 0.15 * wortmenge)
    return round(max(0.0, min(100.0, wert)), 1)


class WhisperDienst:
    def __init__(self) -> None:
        self.prozess = None
        self.ausgaben: queue.Queue = queue.Queue()
        self.fehlerzeilen = collections.deque(maxlen=60)
        self.sperre = threading.RLock()

    def verfuegbar(self) -> bool:
        return WHISPER_PYTHON.is_file() and WORKER.is_file()

    def _lese_stdout(self) -> None:
        try:
            for zeile in self.prozess.stdout:
                self.ausgaben.put(zeile.rstrip("\r\n"))
        except Exception:
            pass

    def _lese_stderr(self) -> None:
        try:
            for zeile in self.prozess.stderr:
                self.fehlerzeilen.append(zeile.rstrip("\r\n"))
        except Exception:
            pass

    def _starte(self) -> None:
        if self.prozess is not None and self.prozess.poll() is None:
            return
        if not self.verfuegbar():
            raise RuntimeError(
                "Faster-Whisper ist noch nicht eingerichtet. "
                "Bitte STARTEN.bat öffnen und »OmniVoice installieren« erneut ausführen."
            )
        self.fehlerzeilen.clear()
        self.ausgaben = queue.Queue()
        self.prozess = subprocess.Popen(
            [str(WHISPER_PYTHON), "-u", str(WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=KEIN_FENSTER,
        )
        threading.Thread(target=self._lese_stdout, daemon=True).start()
        threading.Thread(target=self._lese_stderr, daemon=True).start()

    def transkribiere(self, pfad, sprache: str = "", modell: str = "medium",
                      geraet: str = "auto", timeout: float = 1800.0,
                      segmente: bool = False, szenenmodus: bool = False) -> dict:
        with self.sperre:
            self._starte()
            ident = uuid.uuid4().hex
            auftrag = {
                "id": ident,
                "aktion": "transkribieren",
                "pfad": str(Path(pfad)),
                "sprache": str(sprache or ""),
                "modell": str(modell or "medium"),
                "geraet": GERAETE.get(str(geraet), str(geraet or "auto")),
                "segmente": bool(segmente),
                "szenenmodus": bool(szenenmodus),
            }
            try:
                self.prozess.stdin.write(json.dumps(auftrag, ensure_ascii=False) + "\n")
                self.prozess.stdin.flush()
            except Exception as fehler:
                self.stoppen()
                raise RuntimeError(f"Whisper-Helfer ist nicht erreichbar: {fehler}") from fehler

            ende = time.time() + max(5.0, timeout)
            while time.time() < ende:
                if self.prozess.poll() is not None:
                    details = "\n".join(self.fehlerzeilen)[-2000:]
                    raise RuntimeError(
                        f"Whisper-Helfer wurde unerwartet beendet. {details}".strip()
                    )
                try:
                    zeile = self.ausgaben.get(timeout=0.25)
                except queue.Empty:
                    continue
                if not zeile.startswith(ANTWORT):
                    continue
                try:
                    antwort = json.loads(zeile[len(ANTWORT):])
                except ValueError:
                    continue
                if str(antwort.get("id", "")) != ident:
                    continue
                if not antwort.get("ok"):
                    raise RuntimeError(str(antwort.get("fehler", "Whisper-Fehler")))
                return antwort
            self.stoppen()
            raise TimeoutError(f"Whisper hat nach {int(timeout)} Sekunden nicht geantwortet.")

    def stoppen(self) -> None:
        with self.sperre:
            prozess, self.prozess = self.prozess, None
            if prozess is None or prozess.poll() is not None:
                return
            try:
                prozess.terminate()
                prozess.wait(timeout=5)
            except Exception:
                try:
                    prozess.kill()
                except Exception:
                    pass


class WhisperPool:
    """Mehrere isolierte Whisper-Prozesse für den Listengenerator."""

    def __init__(self, erster: WhisperDienst) -> None:
        self.sperre = threading.RLock()
        self.dienste = [erster]

    def setze_anzahl(self, anzahl: int) -> list[WhisperDienst]:
        anzahl = max(1, min(8, int(anzahl or 1)))
        with self.sperre:
            while len(self.dienste) < anzahl:
                self.dienste.append(WhisperDienst())
            if len(self.dienste) > anzahl:
                uebrig, entfernen = self.dienste[:anzahl], self.dienste[anzahl:]
                self.dienste = uebrig
                for dienst in entfernen:
                    dienst.stoppen()
            return list(self.dienste)

    def reduzieren(self) -> None:
        """Nach parallelen Listenläufen nur den einen Batch-Dienst behalten."""
        self.setze_anzahl(1)

    def stoppen(self) -> None:
        with self.sperre:
            for dienst in self.dienste:
                dienst.stoppen()
            self.dienste = self.dienste[:1]


class BewertungsSpeicher:
    def __init__(self, pfad: Path) -> None:
        self.pfad = Path(pfad)
        self.sperre = threading.RLock()
        self.daten = self._lesen()

    @staticmethod
    def schluessel(pfad) -> str:
        try:
            return str(Path(pfad).resolve()).casefold()
        except OSError:
            return str(Path(pfad)).casefold()

    def _lesen(self) -> dict:
        try:
            daten = json.loads(self.pfad.read_text(encoding="utf-8"))
            return daten if isinstance(daten, dict) else {}
        except Exception:
            return {}

    def hole(self, pfad, erwartet: str) -> dict:
        datei = Path(pfad)
        try:
            stat = datei.stat()
        except OSError:
            return {}
        with self.sperre:
            wert = self.daten.get(self.schluessel(datei), {})
            if (
                isinstance(wert, dict)
                and wert.get("erwartet") == str(erwartet or "")
                and int(wert.get("mtime_ns", -1)) == stat.st_mtime_ns
                and int(wert.get("groesse", -1)) == stat.st_size
            ):
                return dict(wert)
        return {}

    def setze(self, pfad, erwartet: str, rating: float, transkript: str,
              modell: str = "", geraet: str = "") -> None:
        datei = Path(pfad)
        stat = datei.stat()
        wert = {
            "erwartet": str(erwartet or ""),
            "rating": round(float(rating), 1),
            "transkript": str(transkript or ""),
            "modell": str(modell or ""),
            "geraet": str(geraet or ""),
            "mtime_ns": stat.st_mtime_ns,
            "groesse": stat.st_size,
            "geprueft_am": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self.sperre:
            self.daten[self.schluessel(datei)] = wert
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            temporaer = self.pfad.with_suffix(self.pfad.suffix + ".tmp")
            temporaer.write_text(
                json.dumps(self.daten, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(temporaer, self.pfad)


DIENST = WhisperDienst()
POOL = WhisperPool(DIENST)
atexit.register(POOL.stoppen)
