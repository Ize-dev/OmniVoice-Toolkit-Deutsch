#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemeinsamer Modell-Unterbau fuer die Oberflaeche und die Arbeiter-Prozesse.

Hier steht alles, was mit OmniVoice selbst zu tun hat: Geraetewahl, Laden des
Modells, Erzeugen von Audio und Schreiben der WAV-Datei. Sowohl
oberflaeche.py (Hauptprozess) als auch arbeiter.py (Stapel-Arbeiter)
benutzen genau diesen Code - so kann es keine Unterschiede zwischen
Einzelstueck und Stapel geben.
"""

import sys
import time
from pathlib import Path

MODELL = "k2-fsa/OmniVoice"
ABTASTRATE = 24_000

# Grober Speicherbedarf eines Modells im Grafikspeicher (Gewichte, Zwischen-
# ergebnisse und Reserve). Dient nur der Empfehlung in den Einstellungen.
VRAM_JE_ARBEITER = 3.5


def sag(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


class Motor:
    def __init__(self) -> None:
        self.modell = None
        self.geraet = "cpu"
        self.geraetename = "Prozessor"
        self.dtype_name = "float32"
        self.vram_gb = 0.0

    def waehle_geraet(self):
        import torch

        try:
            if torch.cuda.is_available():
                self.geraet = "cuda:0"
                self.geraetename = torch.cuda.get_device_name(0)
                self.dtype_name = "float16"
                self.vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
                return torch.float16
        except Exception:
            pass
        try:
            if hasattr(torch, "xpu") and torch.xpu.is_available():
                self.geraet = "xpu:0"
                self.geraetename = torch.xpu.get_device_name(0)
                self.dtype_name = "float16"
                return torch.float16
        except Exception:
            pass
        self.geraet = "cpu"
        self.geraetename = "Prozessor (CPU)"
        self.dtype_name = "float32"
        return torch.float32

    def laden(self, still: bool = False) -> None:
        import torch  # noqa: F401
        from omnivoice import OmniVoice

        dtype = self.waehle_geraet()
        if not still:
            sag(f"Gerät: {self.geraetename}  ({self.geraet}, {self.dtype_name})")
            sag("Sprachmodell wird in den Speicher geladen – das dauert einen Moment …")
        beginn = time.time()
        try:
            self.modell = OmniVoice.from_pretrained(MODELL, device_map=self.geraet, dtype=dtype)
        except TypeError:
            self.modell = OmniVoice.from_pretrained(MODELL, device_map=self.geraet)
        if not still:
            sag(f"Modell bereit nach {time.time() - beginn:.1f} Sekunden.")

    def erzeuge(self, **argumente):
        """Ruft generate() auf und laesst Argumente weg, die diese Fassung nicht kennt."""
        optional = ["duration", "speed", "num_step"]
        for _versuch in range(len(optional) + 1):
            try:
                return self.modell.generate(**argumente)
            except TypeError as fehler:
                name = next((n for n in optional if n in argumente and n in str(fehler)), None)
                if name is None:
                    name = next((n for n in optional if n in argumente), None)
                if name is None:
                    raise
                sag(f"Hinweis: »{name}« kennt diese OmniVoice-Fassung nicht und wird weggelassen.")
                argumente.pop(name)
                optional.remove(name)
        return self.modell.generate(**argumente)


MOTOR = Motor()


def empfohlene_arbeiter(vram_gb: float) -> int:
    """Wie viele Arbeiter passen grob in den Grafikspeicher?"""
    if vram_gb <= 0:
        return 1
    return max(1, min(8, int((vram_gb - 2.0) / VRAM_JE_ARBEITER)))


def als_array(ergebnis):
    import numpy as np

    if isinstance(ergebnis, (list, tuple)):
        if not ergebnis:
            raise RuntimeError("Das Modell hat kein Audio zurückgegeben.")
        ergebnis = ergebnis[0]
    daten = np.asarray(ergebnis)
    if daten.ndim > 1:
        daten = daten.reshape(-1)
    return daten.astype("float32", copy=False)


def schreibe_wav(daten, ziel: Path) -> None:
    import soundfile as sf

    ziel.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(ziel), daten, ABTASTRATE)


def audiolaenge(pfad) -> float:
    """Laenge einer Audiodatei in Sekunden (0.0, wenn nicht lesbar)."""
    if not pfad:
        return 0.0
    try:
        import soundfile as sf

        return float(sf.info(str(pfad)).duration)
    except Exception:
        pass
    try:
        import wave

        with wave.open(str(pfad), "rb") as datei:
            rate = datei.getframerate()
            return datei.getnframes() / rate if rate else 0.0
    except Exception:
        return 0.0


def ziel_dauer(auftrag: dict) -> float:
    """
    Gewuenschte Laenge der Ausgabe in Sekunden (0 = keine Vorgabe).

    Entweder fest vorgegeben oder von der Sprachprobe uebernommen, jeweils
    zuzueglich des eingestellten Versatzes.
    """
    if auftrag.get("duration"):
        return float(auftrag["duration"])
    if auftrag.get("dauer_von_probe") and auftrag.get("ref_audio"):
        laenge = audiolaenge(auftrag["ref_audio"]) + float(auftrag.get("dauer_offset", 0.0))
        return laenge if laenge > 0.2 else 0.0
    return 0.0


def baue_argumente(auftrag: dict) -> dict:
    argumente = {
        "text": auftrag["text"],
        "num_step": int(auftrag.get("num_step", 32)),
        "speed": float(auftrag.get("speed", 1.0)),
    }
    if auftrag.get("ref_audio"):
        argumente["ref_audio"] = auftrag["ref_audio"]
    if auftrag.get("ref_text"):
        argumente["ref_text"] = auftrag["ref_text"]

    dauer = ziel_dauer(auftrag)
    if dauer > 0:
        argumente["duration"] = dauer
        # OmniVoice legt in der Nachbearbeitung 0,1 s Stille an JEDE Seite
        # (pad_duration). Die Datei waere damit immer 0,2 s laenger als die
        # Vorlage - fuer eine Vertonung unbrauchbar. Also abschalten.
        argumente["pad_duration"] = 0.0
    return argumente


# ------------------------------------------------------------
# Klangbearbeitung nach dem Erzeugen
# ------------------------------------------------------------

def _rms(daten) -> float:
    import numpy as np

    if daten is None or len(daten) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(daten, dtype="float64"))))


def stille_kuerzen(daten, schwelle_db: float = -45.0, rand: float = 0.03):
    """Entfernt die Stille am Anfang und laesst einen kleinen Vorlauf stehen."""
    import numpy as np

    if daten is None or len(daten) == 0:
        return daten
    spitze = float(np.max(np.abs(daten)))
    if spitze <= 0.0:
        return daten
    grenze = spitze * (10.0 ** (schwelle_db / 20.0))
    laut = np.flatnonzero(np.abs(daten) > grenze)
    if len(laut) == 0:
        return daten
    start = max(0, int(laut[0]) - int(rand * ABTASTRATE))
    return daten[start:]


def lautstaerke_anpassen(daten, modus: str, db: float = 0.0, referenz: str = ""):
    """
    »db«           feste Verstaerkung in Dezibel
    »wie_original« gleicht die Lautheit der englischen Aufnahme an
    In beiden Faellen wird eine Uebersteuerung abgefangen.
    """
    import numpy as np

    if daten is None or len(daten) == 0 or modus in ("", "aus", None):
        return daten
    faktor = 1.0
    if modus == "db":
        if abs(float(db)) < 0.01:
            return daten
        faktor = 10.0 ** (float(db) / 20.0)
    elif modus == "wie_original":
        try:
            import soundfile as sf

            vorlage, _rate = sf.read(str(referenz), dtype="float32", always_2d=False)
            if getattr(vorlage, "ndim", 1) > 1:
                vorlage = vorlage.reshape(-1)
            ziel, ist = _rms(vorlage), _rms(daten)
            if ziel <= 0.0 or ist <= 0.0:
                return daten
            faktor = float(np.clip(ziel / ist, 0.1, 10.0))
        except Exception:
            return daten
    else:
        return daten

    daten = daten * faktor
    spitze = float(np.max(np.abs(daten)))
    if spitze > 0.99:
        daten = daten * (0.99 / spitze)
    return daten.astype("float32", copy=False)


def laenge_erzwingen(daten, sekunden: float, ausblenden: float = 0.015):
    """
    Bringt die Aufnahme auf genau die gewuenschte Laenge.

    Noetig, weil OmniVoice die Vorgabe nur ungefaehr trifft: die eigene
    Nachbearbeitung schneidet Stille weg und legt Ruhe an die Raender. Zu lang
    darf eine Vertonung aber nie sein - sie passt sonst nicht in ihren Platz.
    Zu kurz wird mit Stille aufgefuellt, zu lang wird mit kurzer Ausblendung
    abgeschnitten (sonst knackt es).

    Liefert (Daten, Korrektur in Sekunden): positiv = gekuerzt, negativ = verlaengert.
    """
    import numpy as np

    ziel = int(round(float(sekunden) * ABTASTRATE))
    if ziel <= 0 or daten is None or len(daten) == ziel:
        return daten, 0.0
    abweichung = (len(daten) - ziel) / float(ABTASTRATE)
    if len(daten) > ziel:
        daten = np.array(daten[:ziel], dtype="float32", copy=True)
        blende = min(int(ausblenden * ABTASTRATE), len(daten))
        if blende > 1:
            daten[-blende:] *= np.linspace(1.0, 0.0, blende, dtype="float32")
    else:
        daten = np.concatenate([np.asarray(daten, dtype="float32"),
                                np.zeros(ziel - len(daten), dtype="float32")])
    return daten, abweichung


def nachbearbeiten(daten, auftrag: dict):
    """
    Stille kuerzen, Lautstaerke anpassen, Laenge einhalten.
    Gilt fuer Einzelstueck und Stapel gleichermassen.

    Liefert (Daten, Korrektur in Sekunden).
    """
    if auftrag.get("stille_weg"):
        daten = stille_kuerzen(daten)
    modus = auftrag.get("lautstaerke_modus", "aus")
    if modus and modus != "aus":
        daten = lautstaerke_anpassen(daten, modus, auftrag.get("lautstaerke_db", 0.0),
                                     auftrag.get("ref_audio", ""))
    korrektur = 0.0
    dauer = ziel_dauer(auftrag)
    if dauer > 0 and auftrag.get("laenge_erzwingen", True):
        daten, korrektur = laenge_erzwingen(daten, dauer)
    return daten, korrektur


def fuehre_auftrag_aus(auftrag: dict) -> dict:
    """
    Erzeugt eine einzelne Datei. Wird sowohl im Hauptprozess als auch in den
    Arbeiter-Prozessen benutzt und wirft niemals - Fehler kommen als Ergebnis
    zurueck, damit ein Stapel daran nicht zerbricht.
    """
    beginn = time.time()
    try:
        daten = als_array(MOTOR.erzeuge(**baue_argumente(auftrag)))
        daten, korrektur = nachbearbeiten(daten, auftrag)
        schreibe_wav(daten, Path(auftrag["ziel"]))
        return {
            "id": auftrag.get("id"),
            "ok": True,
            "sekunden": time.time() - beginn,
            "ton": len(daten) / ABTASTRATE,
            "korrektur": korrektur,
            "fehler": "",
        }
    except Exception as fehler:
        return {
            "id": auftrag.get("id"),
            "ok": False,
            "sekunden": time.time() - beginn,
            "ton": 0.0,
            "korrektur": 0.0,
            "fehler": f"{type(fehler).__name__}: {fehler}",
        }
