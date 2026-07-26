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
    if auftrag.get("duration"):
        argumente["duration"] = float(auftrag["duration"])
    elif auftrag.get("dauer_von_probe") and auftrag.get("ref_audio"):
        # Ausgabe genauso lang machen wie die Sprachprobe - fuer Vertonungen,
        # bei denen die deutsche Zeile ins Zeitfenster der englischen passen soll.
        laenge = audiolaenge(auftrag["ref_audio"])
        if laenge > 0.05:
            argumente["duration"] = laenge
    return argumente


def fuehre_auftrag_aus(auftrag: dict) -> dict:
    """
    Erzeugt eine einzelne Datei. Wird sowohl im Hauptprozess als auch in den
    Arbeiter-Prozessen benutzt und wirft niemals - Fehler kommen als Ergebnis
    zurueck, damit ein Stapel daran nicht zerbricht.
    """
    beginn = time.time()
    try:
        daten = als_array(MOTOR.erzeuge(**baue_argumente(auftrag)))
        schreibe_wav(daten, Path(auftrag["ziel"]))
        return {
            "id": auftrag.get("id"),
            "ok": True,
            "sekunden": time.time() - beginn,
            "ton": len(daten) / ABTASTRATE,
            "fehler": "",
        }
    except Exception as fehler:
        return {
            "id": auftrag.get("id"),
            "ok": False,
            "sekunden": time.time() - beginn,
            "ton": 0.0,
            "fehler": f"{type(fehler).__name__}: {fehler}",
        }
