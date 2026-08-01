#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Isolierter Faster-Whisper-Prozess.

Laeuft in system/whisper-umgebung und liest JSON-Auftraege zeilenweise von
stdin. Antworten beginnen mit #WHISPER#, damit Bibliotheksausgaben das
Protokoll nicht verwechseln koennen. Das zuletzt verwendete Modell bleibt
geladen und wird zwischen Dateien wiederverwendet.
"""

import json
import os
import sys
import traceback
from pathlib import Path

SYSTEM_DIR = Path(__file__).resolve().parent.parent
TORCH_LIB = SYSTEM_DIR / "umgebung" / "Lib" / "site-packages" / "torch" / "lib"
ANTWORT = "#WHISPER#"

_modell = None
_schluessel = None
_geraet = ""
_compute = ""
_dll_handles = []
_cuda_vorbereitet = False


def sende(**daten) -> None:
    sys.stdout.write(ANTWORT + json.dumps(daten, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def bereite_cuda_vor() -> None:
    """Macht die von PyTorch mitgelieferten CUDA-/cuDNN-DLLs fuer CTranslate2 sichtbar."""
    global _cuda_vorbereitet

    if _cuda_vorbereitet:
        return
    _cuda_vorbereitet = True
    if os.name != "nt" or not TORCH_LIB.is_dir():
        return
    # Nie pro Audiodatei erneut voranstellen: Windows begrenzt einzelne
    # Umgebungsvariablen auf 32.767 Zeichen.
    torch_lib = str(TORCH_LIB)
    pfade = os.environ.get("PATH", "").split(os.pathsep)
    if not any(pfad.rstrip("\\/").casefold() == torch_lib.rstrip("\\/").casefold()
               for pfad in pfade if pfad):
        os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
    try:
        _dll_handles.append(os.add_dll_directory(str(TORCH_LIB)))
    except (AttributeError, OSError):
        pass


def cuda_verfuegbar() -> bool:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def lade_modell(name: str, wunsch: str):
    global _modell, _schluessel, _geraet, _compute

    name = (name or "medium").strip()
    wunsch = (wunsch or "auto").strip().lower()
    if wunsch not in ("auto", "cpu", "cuda"):
        wunsch = "auto"

    bereite_cuda_vor()
    kandidat = "cuda" if wunsch == "cuda" or (wunsch == "auto" and cuda_verfuegbar()) else "cpu"
    compute = "float16" if kandidat == "cuda" else "int8"
    schluessel = (name, kandidat, compute)
    if _modell is not None and _schluessel == schluessel:
        return _modell

    from faster_whisper import WhisperModel

    try:
        modell = WhisperModel(name, device=kandidat, compute_type=compute)
    except Exception:
        if wunsch != "auto" or kandidat == "cpu":
            raise
        # Automatik bedeutet wirklich universell: unpassende CUDA-Version,
        # zu wenig VRAM oder fehlende DLL -> CPU statt Programmabbruch.
        kandidat, compute = "cpu", "int8"
        schluessel = (name, kandidat, compute)
        modell = WhisperModel(name, device=kandidat, compute_type=compute)

    _modell = modell
    _schluessel = schluessel
    _geraet = kandidat
    _compute = compute
    return modell


def transkribiere(auftrag: dict) -> dict:
    global _modell, _schluessel

    pfad = Path(str(auftrag.get("pfad", "")))
    if not pfad.is_file():
        raise FileNotFoundError(f"Audiodatei fehlt: {pfad}")
    modellname = str(auftrag.get("modell", "medium"))
    geraetewunsch = str(auftrag.get("geraet", "auto"))
    modell = lade_modell(modellname, geraetewunsch)
    sprache = str(auftrag.get("sprache", "")).strip() or None
    szenenmodus = bool(auftrag.get("szenenmodus"))

    def ausfuehren(aktives_modell):
        argumente = {
            "language": sprache,
            "beam_size": max(1, int(auftrag.get("beam_size", 5))),
            "vad_filter": True,
            "condition_on_previous_text": False,
            "word_timestamps": szenenmodus,
        }
        if szenenmodus:
            # Cutscenes enthalten Musik, lange Pausen und kurze Einwürfe. Die
            # normalen zwei Sekunden VAD-Stille verschlucken hier zu viel.
            argumente.update({
                "vad_parameters": {
                    "threshold": 0.35,
                    "min_speech_duration_ms": 80,
                    "max_speech_duration_s": 25.0,
                    "min_silence_duration_ms": 350,
                    "speech_pad_ms": 300,
                },
                "hallucination_silence_threshold": 2.0,
            })
        segmente, info = aktives_modell.transcribe(str(pfad), **argumente)
        teile = []
        for segment in segmente:
            text = segment.text.strip()
            if text:
                start = float(segment.start)
                ende = float(segment.end)
                if szenenmodus:
                    woerter = [
                        wort for wort in (getattr(segment, "words", None) or [])
                        if getattr(wort, "start", None) is not None
                        and getattr(wort, "end", None) is not None
                    ]
                    if woerter:
                        # Segmentgrenzen von Whisper können bei langer Stille
                        # minutenweit reichen. Wortzeiten schneiden exakt auf
                        # tatsächlich erkannte Sprache zurück.
                        start = float(woerter[0].start)
                        ende = float(woerter[-1].end)
                teile.append({
                    "start": round(start, 3),
                    "end": round(max(start + 0.08, ende), 3),
                    "text": text,
                })
        text = " ".join(segment["text"] for segment in teile).strip()
        return text, teile, info

    try:
        text, teile, info = ausfuehren(modell)
    except Exception:
        # Manche CUDA-/cuDNN-Probleme zeigen sich erst beim ersten Rechenschritt,
        # nicht schon beim Laden. Auch dann hält »Automatisch« sein CPU-Versprechen.
        if geraetewunsch.strip().lower() != "auto" or _geraet != "cuda":
            raise
        _modell, _schluessel = None, None
        modell = lade_modell(modellname, "cpu")
        text, teile, info = ausfuehren(modell)
    ergebnis = {
        "ok": True,
        "text": text,
        "sprache": getattr(info, "language", sprache or ""),
        "sprach_wahrscheinlichkeit": float(
            getattr(info, "language_probability", 0.0) or 0.0
        ),
        "dauer": float(getattr(info, "duration", 0.0) or 0.0),
        "geraet": _geraet,
        "compute_type": _compute,
        "modell": str(auftrag.get("modell", "medium")),
    }
    if auftrag.get("segmente"):
        ergebnis["segmente"] = teile
    return ergebnis


def main() -> int:
    bereite_cuda_vor()
    for roh in sys.stdin:
        roh = roh.strip()
        if not roh:
            continue
        ident = ""
        try:
            auftrag = json.loads(roh)
            ident = str(auftrag.get("id", ""))
            aktion = str(auftrag.get("aktion", "transkribieren"))
            if aktion == "ping":
                sende(ok=True, id=ident, bereit=True, cuda=cuda_verfuegbar())
                continue
            if aktion == "beenden":
                sende(ok=True, id=ident)
                return 0
            ergebnis = transkribiere(auftrag)
            ergebnis["id"] = ident
            sende(**ergebnis)
        except Exception as fehler:
            traceback.print_exc(file=sys.stderr)
            sende(ok=False, id=ident,
                  fehler=f"{type(fehler).__name__}: {fehler}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
