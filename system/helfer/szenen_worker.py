#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Isolierte Stem-Trennung und Sprecher-Diarisierung für lange Szenen."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

MARKER = "#SZENE#"


def melde(phase: str, text: str, **daten) -> None:
    daten.update({"phase": phase, "text": text})
    sys.stdout.write(MARKER + json.dumps(daten, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def finde_stem(wurzel: Path, name: str) -> Path:
    treffer = sorted(wurzel.rglob(name))
    if not treffer:
        raise FileNotFoundError(f"Demucs hat »{name}« nicht erzeugt.")
    return treffer[0]


def bereite_audio_vor(quelle: Path, ausgabe: Path) -> Path:
    """Erzeugt stets Stereo-PCM; Demucs darf keine 5.1/7.1/Atmos-Kanäle verlieren."""
    ffmpeg = os.environ.get("OMNIVOICE_FFMPEG", "").strip()
    if not ffmpeg or not Path(ffmpeg).is_file():
        if quelle.suffix.lower() in {".wav", ".wave"}:
            return quelle
        raise RuntimeError("FFmpeg fehlt für die Vorbereitung der Cutscene.")
    ziel = ausgabe / "eingabe.wav"
    melde(
        "vorbereitung",
        "Originalton wird inklusive Center-Kanal auf 44,1-kHz-Stereo heruntergemischt.",
    )
    ergebnis = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(quelle), "-map", "0:a:0", "-vn",
            "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(ziel),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if ergebnis.returncode != 0 or not ziel.is_file():
        raise RuntimeError("Das Eingabeformat konnte nicht in WAV umgewandelt werden: "
                           + ergebnis.stderr[-1000:])
    return ziel


def normalisiere_stimme(quelle: Path, ziel: Path) -> Path:
    """Hebt die Analysespur an, ohne den für den späteren Mix benutzten Rest zu verändern."""
    ffmpeg = os.environ.get("OMNIVOICE_FFMPEG", "").strip()
    if not ffmpeg or not Path(ffmpeg).is_file():
        shutil.copy2(quelle, ziel)
        return ziel
    ergebnis = subprocess.run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(quelle), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "44100",
            "-af", "loudnorm=I=-19:TP=-2:LRA=11",
            "-c:a", "pcm_s16le", str(ziel),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if ergebnis.returncode != 0 or not ziel.is_file():
        raise RuntimeError("Die Sprachspur konnte nicht normalisiert werden: "
                           + ergebnis.stderr[-1000:])
    return ziel


def trenne(quelle: Path, ausgabe: Path) -> tuple[Path, Path]:
    melde("separation", "Stimme und Originalrest werden mit Demucs getrennt.")
    demucs_ziel = ausgabe / "demucs"
    demucs_ziel.mkdir(parents=True, exist_ok=True)
    try:
        from demucs.separate import main as demucs_main

        demucs_main([
            "--two-stems", "vocals",
            "--name", "htdemucs",
            "--out", str(demucs_ziel),
            str(quelle),
        ])
    except SystemExit as fehler:
        if int(fehler.code or 0) != 0:
            raise RuntimeError(f"Demucs wurde mit Fehlercode {fehler.code} beendet.") from fehler

    vocals_roh = finde_stem(demucs_ziel, "vocals.wav")
    rest_roh = finde_stem(demucs_ziel, "no_vocals.wav")
    vocals = ausgabe / "stimme.wav"
    rest = ausgabe / "originalrest.wav"
    melde("separation", "Sprachspur wird für Pyannote und Whisper normalisiert.")
    normalisiere_stimme(vocals_roh, vocals)
    shutil.copy2(rest_roh, rest)
    melde("separation", "Audiotrennung abgeschlossen.", vocals=str(vocals), rest=str(rest))
    return vocals, rest


def lade_pipeline(modell: str, token: str):
    from pyannote.audio import Pipeline

    argumente = {}
    if token:
        argumente["token"] = token
    try:
        return Pipeline.from_pretrained(modell, **argumente)
    except TypeError:
        if token:
            argumente = {"use_auth_token": token}
        return Pipeline.from_pretrained(modell, **argumente)


def diarisiere(vocals: Path, modell: str, geraet: str, token: str) -> tuple[list[dict], str]:
    melde("diarization", "Pyannote erkennt Sprecher und Zeitbereiche.")
    import torch

    wunsch = str(geraet or "auto").lower()
    if wunsch not in {"auto", "cpu", "cuda"}:
        wunsch = "auto"
    aktiv = "cuda" if wunsch == "cuda" or (wunsch == "auto" and torch.cuda.is_available()) else "cpu"
    try:
        pipeline = lade_pipeline(modell, token)
    except Exception as fehler:
        zusatz = (
            " Es wurde kein Token übergeben."
            if not token else
            " Prüfe, ob der Token gültig ist und die Modellbedingungen bestätigt wurden."
        )
        raise RuntimeError(
            f"Pyannote-Modell »{modell}« konnte nicht geladen werden: "
            f"{type(fehler).__name__}: {fehler}.{zusatz}"
        ) from fehler
    if pipeline is None:
        raise RuntimeError(
            "Das Pyannote-Modell konnte nicht geladen werden. Bitte auf Hugging Face "
            "die Modellbedingungen akzeptieren und einen gültigen Token eintragen."
        )
    try:
        pipeline.to(torch.device(aktiv))
    except Exception:
        if wunsch != "auto" or aktiv == "cpu":
            raise
        aktiv = "cpu"
        pipeline.to(torch.device("cpu"))

    ergebnis = pipeline(str(vocals))
    if isinstance(ergebnis, dict):
        annotation = (
            ergebnis.get("speaker_diarization")
            or ergebnis.get("diarization")
            or ergebnis
        )
    else:
        annotation = getattr(ergebnis, "speaker_diarization", ergebnis)
    if not hasattr(annotation, "itertracks"):
        raise RuntimeError("Pyannote hat keine verwertbare Sprecher-Timeline geliefert.")
    segmente = []
    for bereich, _spur, sprecher in annotation.itertracks(yield_label=True):
        start, ende = float(bereich.start), float(bereich.end)
        if ende - start >= 0.08:
            segmente.append({
                "start": round(start, 3),
                "end": round(ende, 3),
                "speaker": str(sprecher),
            })
    segmente.sort(key=lambda wert: (wert["start"], wert["end"]))
    melde(
        "diarization",
        f"{len({s['speaker'] for s in segmente})} Sprecher und "
        f"{len(segmente)} Sprachbereiche erkannt.",
        geraet=aktiv,
    )
    return segmente, aktiv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quelle", required=True)
    parser.add_argument("--ausgabe", required=True)
    parser.add_argument("--modell", default="pyannote/speaker-diarization-3.1")
    parser.add_argument("--geraet", default="auto")
    parser.add_argument("--ohne-separation", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")
    # Pyannote 3.x lädt seine offiziellen Lightning-Checkpoints über torch.load.
    # Seit PyTorch 2.6 ist dort weights_only=True der Standard, womit diese
    # älteren Checkpoints trotz vertrauenswürdiger Quelle abgewiesen werden.
    # Der von PyTorch vorgesehene Kompatibilitätsschalter gilt nur in diesem
    # isolierten Worker-Prozess und nicht für OmniVoice oder Whisper.
    os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
    quelle = Path(args.quelle).resolve()
    ausgabe = Path(args.ausgabe).resolve()
    token = os.environ.get("HF_TOKEN", "").strip()
    try:
        if not quelle.is_file():
            raise FileNotFoundError(f"Audiodatei fehlt: {quelle}")
        ausgabe.mkdir(parents=True, exist_ok=True)
        arbeitsquelle = bereite_audio_vor(quelle, ausgabe)
        if args.ohne_separation:
            melde(
                "separation",
                "Separation ist deaktiviert: Originalmix wird direkt analysiert.",
            )
            vocals = normalisiere_stimme(arbeitsquelle, ausgabe / "stimme.wav")
            rest = ausgabe / "originalrest.wav"
            shutil.copy2(arbeitsquelle, rest)
        else:
            vocals, rest = trenne(arbeitsquelle, ausgabe)
        diar, aktiv = diarisiere(vocals, args.modell, args.geraet, token)
        resultat = {
            "ok": True,
            "quelle": str(quelle),
            "vocals": str(vocals),
            "rest": str(rest),
            "diarisierung": diar,
            "pyannote_modell": args.modell,
            "geraet": aktiv,
            "separation": not args.ohne_separation,
        }
        ziel = ausgabe / "analyse.json"
        ziel.write_text(json.dumps(resultat, indent=2, ensure_ascii=False), encoding="utf-8")
        melde("fertig", "Stem-Trennung und Sprechererkennung abgeschlossen.",
              ergebnis=str(ziel), **resultat)
        return 0
    except Exception as fehler:
        traceback.print_exc(file=sys.stderr)
        melde("fehler", f"{type(fehler).__name__}: {fehler}", ok=False)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
