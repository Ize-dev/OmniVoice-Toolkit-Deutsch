#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pipeline, Datenmodell und Timeline für lange Szenen/Cutscenes."""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import whisper_dienst
from motor import ABTASTRATE, MOTOR, als_array, baue_argumente, nachbearbeiten, schreibe_wav

SYSTEM_DIR = Path(__file__).resolve().parent.parent
SZENEN_PYTHON = SYSTEM_DIR / "szenen-umgebung" / (
    "Scripts/python.exe" if os.name == "nt" else "bin/python"
)
WORKER = Path(__file__).resolve().parent / "szenen_worker.py"
MARKER = "#SZENE#"
SPALTEN = ["#", "Sprecher", "Start (s)", "Ende (s)", "Originaltext", "Deutscher Text"]
PYANNOTE_MODELLE = [
    "pyannote/speaker-diarization-3.1",
]
UPLOAD_ORDNER = "_uploads"


def umgebung_bereit() -> bool:
    if not SZENEN_PYTHON.is_file() or not WORKER.is_file():
        return False
    try:
        pruefung = subprocess.run(
            [
                str(SZENEN_PYTHON), "-c",
                "from importlib.metadata import version; "
                "hub=tuple(int(x) for x in version('huggingface_hub').split('.')[:2]); "
                "sb=tuple(int(x) for x in version('speechbrain').split('.')[:2]); "
                "raise SystemExit(0 if hub < (1, 0) and sb < (1, 1) else 1)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return pruefung.returncode == 0


def _sicherer_name(text: str) -> str:
    text = re.sub(r"[^\w.-]+", "_", str(text or ""), flags=re.UNICODE).strip("._")
    return text[:70] or "cutscene"


def _melde(callback, phase: str, text: str, **daten) -> None:
    if callback:
        callback({"phase": phase, "text": text, **daten})


def _kopiere_mit_retry(quelle: Path, ziel: Path, timeout: float = 45.0) -> None:
    """Wartet die kurze exklusive Windows-Sperre nach großen Gradio-Uploads ab."""
    ende = time.monotonic() + max(1.0, timeout)
    pause = 0.15
    while True:
        try:
            shutil.copy2(quelle, ziel)
            return
        except PermissionError:
            ziel.unlink(missing_ok=True)
            if time.monotonic() >= ende:
                raise
            time.sleep(pause)
            pause = min(1.0, pause * 1.45)


def _browser_vorschau(quelle: Path, ziel: Path, normalisieren: bool = False) -> Path:
    """Erzeugt eine kleine, browserfreundliche Stereospur für Mehrkanal-Cutscenes."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return quelle
    ziel.parent.mkdir(parents=True, exist_ok=True)
    befehl = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(quelle), "-map", "0:a:0", "-vn", "-ac", "2", "-ar", "44100",
    ]
    if normalisieren:
        # Reine Restspuren können extrem leise sein. Dynamische Verstärkung
        # dient nur der Hörvorschau; die unveränderte WAV bleibt für den Mix.
        befehl += ["-af", "dynaudnorm=f=250:g=21:p=0.95:m=50:r=0.10"]
    befehl += ["-c:a", "libmp3lame", "-b:a", "192k", str(ziel)]
    ergebnis = subprocess.run(
        befehl,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=3600,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if ergebnis.returncode == 0 and ziel.is_file() and ziel.stat().st_size > 0:
        return ziel
    ziel.unlink(missing_ok=True)
    return quelle


def upload_vorbereiten(quelle, basis: Path) -> dict:
    """Entkoppelt große Uploads von Gradios temporärer, gleichzeitig ausgelieferter Datei."""
    quelle = Path(str(quelle or "")).resolve()
    if not quelle.is_file():
        raise FileNotFoundError("Die hochgeladene Audiodatei wurde nicht gefunden.")
    upload_basis = (Path(basis) / UPLOAD_ORDNER).resolve()
    upload_basis.mkdir(parents=True, exist_ok=True)

    # Eine neue Auswahl ersetzt die vorige. Alte, ausschließlich von uns
    # angelegte Uploadkopien können damit ohne wachsenden Plattenverbrauch weg.
    for alt in upload_basis.iterdir():
        if not alt.is_dir():
            continue
        for datei in alt.iterdir():
            if datei.is_file():
                datei.unlink(missing_ok=True)
        try:
            alt.rmdir()
        except OSError:
            pass

    stempel = f"{time.strftime('%Y-%m-%d_%H-%M-%S')}_{time.time_ns() % 1_000_000_000:09d}"
    zielordner = upload_basis / stempel
    zielordner.mkdir(parents=False, exist_ok=False)
    suffix = quelle.suffix.lower() if quelle.suffix else ".wav"
    ziel = zielordner / f"{_sicherer_name(quelle.stem)}{suffix}"
    _kopiere_mit_retry(quelle, ziel)
    vorschau = _browser_vorschau(ziel, zielordner / "vorschau.mp3")
    return {"quelle": str(ziel), "vorschau": str(vorschau)}


def upload_entfernen(quelle, basis: Path) -> None:
    """Entfernt nur eine zuvor von upload_vorbereiten erzeugte Arbeitskopie."""
    if not quelle:
        return
    upload_basis = (Path(basis) / UPLOAD_ORDNER).resolve()
    datei = Path(str(quelle)).resolve()
    try:
        datei.relative_to(upload_basis)
    except ValueError:
        return
    ordner = datei.parent
    for eintrag in ordner.iterdir():
        if eintrag.is_file():
            eintrag.unlink(missing_ok=True)
    try:
        ordner.rmdir()
    except OSError:
        pass


def worker_starten(quelle: Path, ziel: Path, token: str, modell: str, geraet: str,
                   callback=None, separation: bool = True) -> dict:
    if not umgebung_bereit():
        raise RuntimeError(
            "Die Szenen-Werkzeuge fehlen oder enthalten nicht kompatible Pakete. "
            "Bitte das Studio schließen, STARTEN.bat öffnen und "
            "»OmniVoice installieren / reparieren« wählen."
        )
    befehl = [
        str(SZENEN_PYTHON), "-u", str(WORKER),
        "--quelle", str(quelle), "--ausgabe", str(ziel),
        "--modell", str(modell), "--geraet", str(geraet),
    ]
    if not separation:
        befehl.append("--ohne-separation")
    env = dict(os.environ)
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYANNOTE_METRICS_ENABLED": "0",
        "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
    })
    if str(token or "").strip():
        env["HF_TOKEN"] = str(token).strip()
    ffmpeg = _ffmpeg()
    if ffmpeg:
        env["OMNIVOICE_FFMPEG"] = ffmpeg
        env["IMAGEIO_FFMPEG_EXE"] = ffmpeg
    prozess = subprocess.Popen(
        befehl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    letzte = {}
    fehlerzeilen = []
    for zeile in prozess.stdout:
        zeile = zeile.rstrip("\r\n")
        if zeile.startswith(MARKER):
            try:
                daten = json.loads(zeile[len(MARKER):])
                letzte = daten
                _melde(callback, daten.get("phase", ""), daten.get("text", ""), **{
                    k: v for k, v in daten.items() if k not in {"phase", "text"}
                })
            except ValueError:
                pass
        elif zeile.strip():
            fehlerzeilen.append(zeile.strip())
            if len(fehlerzeilen) > 80:
                fehlerzeilen = fehlerzeilen[-80:]
    code = prozess.wait()
    if code != 0 or not letzte.get("ok", letzte.get("phase") == "fertig"):
        details = str(letzte.get("text", "")).strip() or "\n".join(fehlerzeilen[-20:])
        raise RuntimeError(details or f"Szenen-Helfer endete mit Fehlercode {code}.")
    return letzte


def _ueberlappung(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _sprecher_fuer(start: float, ende: float, diar: list[dict]) -> str:
    beste, wert = "SPEAKER_00", 0.0
    mitte = (start + ende) / 2.0
    for bereich in diar:
        anteil = _ueberlappung(start, ende, float(bereich["start"]), float(bereich["end"]))
        if anteil > wert:
            beste, wert = str(bereich["speaker"]), anteil
    if wert <= 0:
        for bereich in diar:
            if float(bereich["start"]) <= mitte <= float(bereich["end"]):
                return str(bereich["speaker"])
    return beste


def _verbinde(segmente: list[dict]) -> list[dict]:
    ergebnis = []
    for segment in sorted(segmente, key=lambda s: (s["start"], s["end"])):
        if (
            ergebnis
            and ergebnis[-1]["speaker"] == segment["speaker"]
            and segment["start"] - ergebnis[-1]["end"] <= 0.35
            and segment["end"] - ergebnis[-1]["start"] <= 18.0
        ):
            ergebnis[-1]["end"] = max(ergebnis[-1]["end"], segment["end"])
            ergebnis[-1]["original"] = (
                ergebnis[-1]["original"].rstrip() + " " + segment["original"].lstrip()
            ).strip()
        else:
            ergebnis.append(dict(segment))
    return ergebnis


def _referenzen(vocals: Path, diar: list[dict], ziel: Path) -> dict[str, str]:
    import numpy as np
    import soundfile as sf

    daten, rate = sf.read(str(vocals), dtype="float32", always_2d=True)
    ziel.mkdir(parents=True, exist_ok=True)
    beste = {}
    for bereich in diar:
        sprecher = str(bereich["speaker"])
        dauer = float(bereich["end"]) - float(bereich["start"])
        if dauer > beste.get(sprecher, (0.0, None))[0]:
            beste[sprecher] = (dauer, bereich)
    ausgabe = {}
    for sprecher, (_dauer, bereich) in beste.items():
        start = max(0, int(float(bereich["start"]) * rate))
        ende = min(len(daten), int(min(float(bereich["end"]), float(bereich["start"]) + 15.0) * rate))
        ausschnitt = daten[start:ende]
        if len(ausschnitt) < int(rate * 0.2):
            continue
        if ausschnitt.shape[1] > 1:
            ausschnitt = np.mean(ausschnitt, axis=1)
        else:
            ausschnitt = ausschnitt[:, 0]
        pfad = ziel / f"{_sicherer_name(sprecher)}.wav"
        sf.write(str(pfad), ausschnitt, rate)
        ausgabe[sprecher] = str(pfad)
    return ausgabe


def _waveform(pfad: Path, punkte: int = 520) -> list[float]:
    """Liest auch große Mehrkanaldateien blockweise und liefert kompakte Spitzenwerte."""
    try:
        import numpy as np
        import soundfile as sf

        with sf.SoundFile(str(pfad)) as datei:
            block = max(1, (len(datei) + punkte - 1) // punkte)
            werte = []
            while len(werte) < punkte:
                daten = datei.read(block, dtype="float32", always_2d=True)
                if len(daten) == 0:
                    break
                werte.append(float(np.max(np.abs(daten))))
        maximum = max(werte + [0.0])
        if maximum <= 1e-8:
            return [0.0 for _ in werte]
        # Wurzel-Skalierung macht leise Sprache sichtbar, ohne Spitzen zu kappen.
        return [round((wert / maximum) ** 0.5, 4) for wert in werte]
    except Exception:
        return []


def analysieren(quelle, basis: Path, token: str, pyannote_modell: str,
                pyannote_geraet: str, whisper_modell: str, whisper_geraet: str,
                callback=None, separation: bool = True) -> dict:
    quelle = Path(str(quelle or "")).resolve()
    if not quelle.is_file():
        raise FileNotFoundError("Bitte zuerst eine gültige Audiodatei auswählen.")
    stempel = time.strftime("%Y-%m-%d_%H-%M-%S")
    grund = Path(basis) / f"{stempel}_{_sicherer_name(quelle.stem)}"
    projekt_dir = grund
    nummer = 2
    while projekt_dir.exists():
        projekt_dir = grund.with_name(f"{grund.name}_{nummer}")
        nummer += 1
    projekt_dir.mkdir(parents=True, exist_ok=False)
    _melde(callback, "start", f"Projektordner: {projekt_dir}")

    # Gradio hält seine temporäre Upload-Datei für den Browser-Player offen.
    # Demucs öffnet dieselbe Datei auf Windows teilweise exklusiv; dann kann
    # Gradio sie nicht mehr ausliefern und Uvicorn meldet PermissionError 13.
    # Eine dauerhafte Arbeitskopie trennt Browser-Streaming und KI-Verarbeitung.
    suffix = quelle.suffix.lower() if quelle.suffix else ".wav"
    arbeitsquelle = projekt_dir / f"original{suffix}"
    _melde(callback, "kopieren", "Upload wird sicher in den Szenenordner kopiert.")
    _kopiere_mit_retry(quelle, arbeitsquelle)
    _melde(callback, "vorschau", "Browserfreundliche Stereo-Vorschau wird vorbereitet.")
    upload_basis = (Path(basis) / UPLOAD_ORDNER).resolve()
    vorhandene_vorschau = quelle.parent / "vorschau.mp3"
    try:
        quelle.relative_to(upload_basis)
        ist_upload = True
    except ValueError:
        ist_upload = False
    if ist_upload and vorhandene_vorschau.is_file():
        vorschau = projekt_dir / "original-vorschau.mp3"
        shutil.copy2(vorhandene_vorschau, vorschau)
    else:
        vorschau = _browser_vorschau(
            arbeitsquelle, projekt_dir / "original-vorschau.mp3"
        )

    analyse = worker_starten(
        arbeitsquelle, projekt_dir, token, pyannote_modell, pyannote_geraet,
        callback, separation=separation,
    )
    vocals = Path(analyse["vocals"])
    diar = list(analyse.get("diarisierung") or [])
    vocals_vorschau = _browser_vorschau(
        vocals, projekt_dir / "stimme-vorschau.mp3", normalisieren=True
    )
    rest_vorschau = _browser_vorschau(
        Path(analyse["rest"]), projekt_dir / "originalrest-vorschau.mp3",
        normalisieren=True,
    )
    _melde(callback, "whisper", "Whisper transkribiert die getrennte Sprachspur.")
    whisper = whisper_dienst.DIENST.transkribiere(
        vocals, sprache="", modell=whisper_modell, geraet=whisper_geraet,
        segmente=True, szenenmodus=True, timeout=7200,
    )
    roh = []
    for nummer, segment in enumerate(whisper.get("segmente") or [], start=1):
        start = max(0.0, float(segment.get("start", 0.0)))
        ende = max(start + 0.08, float(segment.get("end", start)))
        roh.append({
            "id": nummer,
            "speaker": _sprecher_fuer(start, ende, diar),
            "start": round(start, 3),
            "end": round(ende, 3),
            "original": str(segment.get("text", "")).strip(),
            "deutsch": "",
        })
    if not roh:
        for nummer, bereich in enumerate(diar, start=1):
            roh.append({
                "id": nummer, "speaker": str(bereich["speaker"]),
                "start": float(bereich["start"]), "end": float(bereich["end"]),
                "original": "", "deutsch": "",
            })
    segmente = _verbinde(roh)
    referenzen = _referenzen(vocals, diar, projekt_dir / "sprecher")
    for nummer, segment in enumerate(segmente, start=1):
        segment["id"] = nummer
        segment["referenz"] = referenzen.get(segment["speaker"], str(vocals))

    try:
        import soundfile as sf

        ganze_dauer = float(sf.info(str(quelle)).duration)
    except Exception:
        ganze_dauer = 0.0
    projekt = {
        "version": 1,
        "quelle": str(arbeitsquelle),
        "upload_quelle": str(quelle),
        "vorschau": str(vorschau),
        "ordner": str(projekt_dir),
        "vocals": str(vocals),
        "vocals_vorschau": str(vocals_vorschau),
        "rest": str(analyse["rest"]),
        "rest_vorschau": str(rest_vorschau),
        "separation": bool(analyse.get("separation", separation)),
        "dauer": max(
            ganze_dauer,
            float(whisper.get("dauer") or 0.0),
            max([s["end"] for s in segmente] + [0.0]),
        ),
        "pyannote_modell": pyannote_modell,
        "pyannote_geraet": analyse.get("geraet", ""),
        "whisper_modell": whisper_modell,
        "whisper_geraet": whisper.get("geraet", ""),
        "waveform": _waveform(arbeitsquelle),
        "segmente": segmente,
    }
    projekt_speichern(projekt)
    _melde(callback, "fertig", f"{len(segmente)} Textsegmente sind bereit.")
    return projekt


def projekt_speichern(projekt: dict) -> Path:
    ziel = Path(projekt["ordner"]) / "cutscene.json"
    temporaer = ziel.with_suffix(".json.tmp")
    temporaer.write_text(json.dumps(projekt, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporaer, ziel)
    return ziel


def grid(projekt: dict | None) -> list[list]:
    if not projekt:
        return []
    return [
        [
            int(s["id"]), str(s["speaker"]), round(float(s["start"]), 3),
            round(float(s["end"]), 3), str(s.get("original", "")),
            str(s.get("deutsch", "")),
        ]
        for s in projekt.get("segmente", [])
    ]


def grid_anwenden(projekt: dict, daten, zeiten_bewahren: bool = False) -> dict:
    if isinstance(daten, dict) and isinstance(daten.get("data"), list):
        daten = daten["data"]
    elif hasattr(daten, "values") and not callable(daten.values):
        daten = daten.values.tolist()
    daten = list(daten or [])
    alt = {int(s["id"]): s for s in projekt.get("segmente", [])}
    neu = []
    for index, zeile in enumerate(daten, start=1):
        if isinstance(zeile, dict):
            if any(
                name in zeile
                for name in ("id", "speaker", "start", "end", "original", "deutsch")
            ):
                zeile = [
                    zeile.get("id", ""),
                    zeile.get("speaker", ""),
                    zeile.get("start", ""),
                    zeile.get("end", ""),
                    zeile.get("original", ""),
                    zeile.get("deutsch", ""),
                ]
            else:
                zeile = [zeile.get(name, "") for name in SPALTEN]
        zeile = list(zeile or [])
        while len(zeile) < len(SPALTEN):
            zeile.append("")
        try:
            ident = int(float(zeile[0]))
        except (TypeError, ValueError):
            ident = index
        vorher = alt.get(ident, {})
        if zeiten_bewahren and vorher:
            start = float(vorher.get("start", 0.0))
            ende = float(vorher.get("end", start + 0.08))
        else:
            start = max(0.0, float(zeile[2] or 0.0))
            ende = max(start + 0.08, float(zeile[3] or start + 0.08))
        neu.append({
            "id": ident,
            "speaker": str(zeile[1] or vorher.get("speaker") or "SPEAKER_00").strip(),
            "start": round(start, 3), "end": round(ende, 3),
            "original": str(zeile[4] or "").strip(),
            "deutsch": str(zeile[5] or "").strip(),
            "referenz": str(vorher.get("referenz") or projekt.get("vocals", "")),
        })
    neu.sort(key=lambda s: (s["start"], s["end"], s["id"]))
    for nummer, segment in enumerate(neu, start=1):
        segment["id"] = nummer
    projekt["segmente"] = neu
    projekt["dauer"] = max(float(projekt.get("dauer", 0.0)), max(
        [s["end"] for s in neu] + [0.0]
    ))
    projekt_speichern(projekt)
    return projekt


def timeline_aendern(projekt: dict, daten: dict) -> dict:
    ident = int(daten.get("id", 0))
    segment = next((s for s in projekt.get("segmente", []) if int(s["id"]) == ident), None)
    if segment is None:
        raise KeyError("Segment nicht gefunden.")
    if "start" in daten:
        segment["start"] = max(0.0, round(float(daten["start"]), 3))
    if "end" in daten:
        segment["end"] = max(segment["start"] + 0.08, round(float(daten["end"]), 3))
    if "deutsch" in daten:
        segment["deutsch"] = str(daten["deutsch"] or "").strip()
    if "speaker" in daten:
        segment["speaker"] = str(daten["speaker"] or segment["speaker"]).strip()
    projekt["segmente"].sort(key=lambda s: (s["start"], s["end"]))
    projekt_speichern(projekt)
    return segment


def timeline_html(projekt: dict | None) -> str:
    if not projekt or not projekt.get("segmente"):
        return (
            "<div class='ize-szene-leer'>Noch keine Szene analysiert. Audiodatei "
            "hochladen und auf »Szene analysieren« klicken.</div>"
        )
    dauer = max(0.1, float(projekt.get("dauer") or 0.0))
    farben = ["#4d9bff", "#ff4fd8", "#22e0ff", "#ffc857", "#7ff0b0", "#ad8cff"]
    sprecher = {}
    bloecke = []
    for segment in projekt["segmente"]:
        name = str(segment["speaker"])
        if name not in sprecher:
            sprecher[name] = farben[len(sprecher) % len(farben)]
        links = 100.0 * float(segment["start"]) / dauer
        breite = max(0.35, 100.0 * (float(segment["end"]) - float(segment["start"])) / dauer)
        text = str(segment.get("deutsch") or segment.get("original") or "Text eingeben")
        bloecke.append(
            f"<div class='ize-szene-block' data-id='{int(segment['id'])}' "
            f"data-start='{float(segment['start']):.3f}' data-end='{float(segment['end']):.3f}' "
            f"style='left:{links:.5f}%;width:{breite:.5f}%;--spurfarbe:{sprecher[name]}'>"
            "<i class='ize-szene-griff links' data-griff='links'></i>"
            f"<button type='button' data-spielen='{int(segment['id'])}' title='Ab hier abspielen'>▶</button>"
            f"<b>{html.escape(name)}</b>"
            f"<span contenteditable='true' data-szenentext='{int(segment['id'])}'>"
            f"{html.escape(text)}</span>"
            "<i class='ize-szene-griff rechts' data-griff='rechts'></i></div>"
        )
    legende = "".join(
        f"<span><i style='background:{farbe}'></i>{html.escape(name)}</span>"
        for name, farbe in sprecher.items()
    )
    grid_zeilen = []
    for segment in projekt["segmente"]:
        ident = int(segment["id"])
        grid_zeilen.append(
            f"<tr data-editor-zeile='{ident}'>"
            f"<td class='ize-editor-id'>{ident}</td>"
            f"<td><div contenteditable='true' data-feld='speaker'>"
            f"{html.escape(str(segment.get('speaker') or 'SPEAKER_00'))}</div></td>"
            f"<td><div contenteditable='true' data-feld='start'>"
            f"{float(segment.get('start', 0.0)):.3f}</div></td>"
            f"<td><div contenteditable='true' data-feld='end'>"
            f"{float(segment.get('end', 0.08)):.3f}</div></td>"
            f"<td><div contenteditable='true' data-feld='original'>"
            f"{html.escape(str(segment.get('original') or ''))}</div></td>"
            f"<td><div contenteditable='true' data-feld='deutsch'>"
            f"{html.escape(str(segment.get('deutsch') or ''))}</div></td>"
            "<td class='ize-editor-aktionen'>"
            "<button type='button' data-zeile-spielen title='Segment abspielen'>▶</button>"
            "<button type='button' data-zeile-teilen title='Am Textcursor teilen'>✂</button>"
            "<button type='button' data-zeile-verbinden title='Mit nächster Zeile verbinden'>⇣</button>"
            "</td></tr>"
        )
    grid_html = (
        "<div class='ize-editor-kopf'>"
        "<div><b>Szenen-Editor</b><span>Text anklicken und direkt schreiben · "
        "Strg+Enter teilt am Cursor</span></div>"
        "<button type='button' data-editor-speichern>Änderungen speichern</button>"
        "</div>"
        "<div class='ize-editor-tabelle'><table><colgroup>"
        "<col class='c-id'><col class='c-sprecher'><col class='c-zeit'><col class='c-zeit'>"
        "<col class='c-text'><col class='c-text'><col class='c-aktionen'>"
        "</colgroup><thead><tr><th>#</th><th>Sprecher</th><th>Start</th><th>Ende</th>"
        "<th>Originaltext</th><th>Deutscher Text</th><th>Aktionen</th></tr></thead>"
        f"<tbody data-editor-body>{''.join(grid_zeilen)}</tbody></table></div>"
        "<div class='ize-editor-meldung' data-editor-meldung>"
        "Änderungen werden lokal bearbeitet und im Hintergrund gespeichert.</div>"
    )
    peaks = list(projekt.get("waveform") or [])
    waveform = ""
    if peaks:
        oben = [
            f"{index},{50.0 - 44.0 * max(0.0, min(1.0, float(wert))):.2f}"
            for index, wert in enumerate(peaks)
        ]
        unten = [
            f"{index},{50.0 + 44.0 * max(0.0, min(1.0, float(wert))):.2f}"
            for index, wert in reversed(list(enumerate(peaks)))
        ]
        punkte = " ".join(oben + unten)
        waveform = (
            f"<svg class='ize-szene-waveform' viewBox='0 0 {max(1, len(peaks)-1)} 100' "
            "preserveAspectRatio='none' aria-hidden='true'>"
            f"<polygon points='{punkte}'></polygon></svg>"
        )
    return (
        f"<div class='ize-cutscene-editor' data-dauer='{dauer:.6f}'>"
        + grid_html +
        f"<div class='ize-szene' data-dauer='{dauer:.6f}'>"
        "<div class='ize-szene-steuerung'>"
        "<button type='button' data-gesamt-spielen='1'>▶ Ganze Szene</button>"
        "<button type='button' data-gesamt-pause='1'>⏸ Pause</button>"
        "<span data-szenenzeit='1'>0:00 / "
        f"{_zeit(dauer)}</span></div>"
        f"<div class='ize-szene-legende'>{legende}</div>"
        "<div class='ize-szene-bahn' data-szenenbahn='1'>"
        + waveform +
        "<div class='ize-szene-playhead' data-playhead='1'></div>"
        + "".join(bloecke) +
        "</div><div class='ize-szene-zeit'><span>0:00</span>"
        f"<span>{_zeit(dauer)}</span></div>"
        "<div class='ize-szene-hinweis' data-szenenmeldung='1'>"
        "Block ziehen = verschieben · Griffe ziehen = Anfang/Ende · Text direkt anklicken</div>"
        "</div></div>"
    )


def _zeit(sekunden: float) -> str:
    minuten, rest = divmod(max(0, int(sekunden)), 60)
    return f"{minuten}:{rest:02d}"


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        pfad = imageio_ffmpeg.get_ffmpeg_exe()
        if pfad and Path(pfad).is_file():
            return str(pfad)
    except Exception:
        pass
    return shutil.which("ffmpeg") or ""


def generieren(projekt: dict, qualitaet: int, tempo: float, ersetzungen_funktion,
               ersetzungen: str, callback=None) -> dict:
    import numpy as np

    segmente = projekt.get("segmente") or []
    if not segmente:
        raise RuntimeError("Die Szene enthält keine Segmente.")
    dauer = max(float(projekt.get("dauer") or 0.0), max(s["end"] for s in segmente))
    sprache = np.zeros(max(1, int(round(dauer * ABTASTRATE))), dtype="float32")
    zielordner = Path(projekt["ordner"]) / "deutsch"
    zielordner.mkdir(parents=True, exist_ok=True)
    erzeugt, ausgelassen = 0, 0
    for index, segment in enumerate(segmente, start=1):
        text = ersetzungen_funktion(str(segment.get("deutsch") or "").strip(), ersetzungen)
        if not text:
            ausgelassen += 1
            _melde(callback, "generation", f"Segment {index}/{len(segmente)} ohne deutschen Text übersprungen.",
                   fortschritt=index / len(segmente))
            continue
        start, ende = float(segment["start"]), float(segment["end"])
        auftrag = {
            "text": text,
            "ref_audio": str(segment.get("referenz") or projekt["vocals"]),
            "num_step": int(qualitaet),
            "speed": float(tempo),
            "duration": max(0.08, ende - start),
            "laenge_erzwingen": True,
        }
        daten = als_array(MOTOR.erzeuge(**baue_argumente(auftrag)))
        daten, _korrektur = nachbearbeiten(daten, auftrag)
        rand = min(int(0.008 * ABTASTRATE), len(daten) // 2)
        if rand > 1:
            daten[:rand] *= np.linspace(0.0, 1.0, rand, dtype="float32")
            daten[-rand:] *= np.linspace(1.0, 0.0, rand, dtype="float32")
        anfang = max(0, int(round(start * ABTASTRATE)))
        ende_index = min(len(sprache), anfang + len(daten))
        sprache[anfang:ende_index] += daten[:max(0, ende_index - anfang)]
        einzel = zielordner / f"{index:04d}_{_sicherer_name(segment['speaker'])}.wav"
        schreibe_wav(daten, einzel)
        erzeugt += 1
        _melde(callback, "generation", f"Segment {index}/{len(segmente)} erzeugt.",
               fortschritt=index / len(segmente))
    spitze = float(np.max(np.abs(sprache))) if len(sprache) else 0.0
    if spitze > 0.98:
        sprache *= 0.98 / spitze
    dub = Path(projekt["ordner"]) / "dub_sprache.wav"
    schreibe_wav(sprache, dub)

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg fehlt. Bitte die Installation über STARTEN.bat erneut ausführen."
        )
    _melde(callback, "mix", "Dub-Sprachspur wird mit dem Originalrest kombiniert.")
    final = Path(projekt["ordner"]) / "cutscene_deutsch.wav"
    befehl = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(projekt["rest"]), "-i", str(dub),
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.98[a]",
        "-map", "[a]", "-c:a", "pcm_s16le", str(final),
    ]
    ergebnis = subprocess.run(
        befehl, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if ergebnis.returncode != 0 or not final.is_file():
        raise RuntimeError("Der finale Audiomix ist fehlgeschlagen: " + ergebnis.stderr[-1200:])
    projekt["dub_sprache"] = str(dub)
    projekt["final"] = str(final)
    projekt_speichern(projekt)
    return {
        "dub": str(dub), "final": str(final), "erzeugt": erzeugt,
        "ausgelassen": ausgelassen, "ordner": str(projekt["ordner"]),
    }


TIMELINE_CSS = """
.ize-szene-leer { padding:28px;text-align:center;opacity:.58;border:1px dashed var(--ize-rand);
  border-radius:12px;background:var(--ize-eingabe); }
.ize-cutscene-editor { display:grid;gap:14px;min-width:0; }
.ize-editor-kopf { display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:11px 12px;border:1px solid var(--ize-rand);border-radius:10px 10px 0 0;
  background:var(--ize-flaeche-stark); }
.ize-editor-kopf>div { display:grid;gap:2px; }
.ize-editor-kopf b { color:var(--ize-kopftext);font-size:13px; }
.ize-editor-kopf span { opacity:.62;font-size:10px; }
.ize-editor-kopf button,.ize-editor-aktionen button { transform:none!important;filter:none!important;
  box-shadow:none!important;overflow:visible!important;isolation:auto!important; }
.ize-editor-kopf button::after,.ize-editor-aktionen button::after { content:none!important;display:none!important; }
.ize-editor-kopf button { min-height:30px!important;padding:5px 11px!important;width:auto!important; }
.ize-editor-tabelle { max-height:520px;overflow:auto;border:1px solid var(--ize-rand);
  border-top:0;border-radius:0 0 10px 10px;background:var(--ize-eingabe); }
.ize-editor-tabelle table { width:100%;min-width:980px;border-collapse:separate;border-spacing:0;
  table-layout:fixed;font-size:11px; }
.ize-editor-tabelle .c-id { width:46px }.ize-editor-tabelle .c-sprecher { width:118px }
.ize-editor-tabelle .c-zeit { width:78px }.ize-editor-tabelle .c-text { width:auto }
.ize-editor-tabelle .c-aktionen { width:112px }
.ize-editor-tabelle th { position:sticky;top:0;z-index:10;padding:8px 7px;text-align:left;
  background:var(--ize-flaeche-stark);color:var(--ize-kopftext);border-bottom:1px solid var(--ize-rand); }
.ize-editor-tabelle td { padding:0;border-right:1px solid color-mix(in srgb,var(--ize-rand) 70%,transparent);
  border-bottom:1px solid color-mix(in srgb,var(--ize-rand) 70%,transparent);vertical-align:top; }
.ize-editor-tabelle tr:hover td { background:color-mix(in srgb,var(--ize-cyan) 5%,transparent); }
.ize-editor-tabelle [contenteditable] { min-height:38px;padding:7px 8px;box-sizing:border-box;
  white-space:pre-wrap;overflow-wrap:anywhere;outline:none;color:var(--ize-text);cursor:text; }
.ize-editor-tabelle [contenteditable]:focus { background:color-mix(in srgb,var(--ize-cyan) 10%,var(--ize-eingabe));
  box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ize-cyan) 58%,transparent); }
.ize-editor-id { padding:9px 7px!important;text-align:center;font-variant-numeric:tabular-nums;opacity:.62; }
.ize-editor-aktionen { padding:5px!important;white-space:nowrap; }
.ize-editor-aktionen button { width:29px!important;min-width:29px!important;height:29px!important;
  min-height:29px!important;padding:0!important;margin:0 2px!important;border:1px solid var(--ize-rand)!important;
  background:var(--ize-flaeche-stark)!important; }
.ize-editor-aktionen button:hover { border-color:var(--ize-cyan)!important;
  background:color-mix(in srgb,var(--ize-cyan) 15%,var(--ize-flaeche-stark))!important; }
.ize-editor-meldung { min-height:18px;padding:0 4px;font-size:10px;opacity:.66; }
.ize-szene { padding:12px;border:1px solid var(--ize-rand);border-radius:12px;
  background:var(--ize-eingabe);overflow:hidden; }
.ize-szene-legende { display:flex;gap:12px;flex-wrap:wrap;margin:0 0 9px;font-size:11px;opacity:.78; }
.ize-szene-legende span { display:flex;align-items:center;gap:5px; }
.ize-szene-legende i { width:9px;height:9px;border-radius:50%;box-shadow:0 0 9px currentColor; }
.ize-szene-steuerung { display:flex;align-items:center;gap:8px;margin-bottom:10px; }
.ize-szene-steuerung button { position:relative!important;width:auto!important;min-width:0!important;
  min-height:30px!important;padding:5px 11px!important;transform:none!important;overflow:hidden!important; }
.ize-szene-steuerung span { margin-left:auto;font-variant-numeric:tabular-nums;font-size:11px;opacity:.72; }
.ize-szene-bahn { position:relative;height:180px;border-radius:9px;overflow:hidden;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.035) 0,
  rgba(255,255,255,.035) 1px,transparent 1px,transparent 5%); }
.ize-szene-waveform { position:absolute;inset:8px 0;width:100%;height:164px;opacity:.52;
  z-index:4;pointer-events:none;filter:drop-shadow(0 0 4px var(--ize-cyan));mix-blend-mode:screen; }
.ize-szene-waveform polygon { fill:color-mix(in srgb,var(--ize-cyan) 72%,transparent); }
.ize-szene-block { position:absolute;top:18px;height:136px;min-width:8px;box-sizing:border-box;
  padding:8px 7px 6px 25px;border:1px solid var(--spurfarbe);border-radius:7px;
  color:var(--ize-text);background:color-mix(in srgb,var(--spurfarbe) 13%,var(--ize-flaeche-stark));
  box-shadow:0 8px 20px -14px var(--spurfarbe);cursor:grab;overflow:hidden;user-select:none;z-index:2; }
.ize-szene-block.aktiv { box-shadow:0 0 0 2px var(--spurfarbe),0 0 25px var(--spurfarbe); }
.ize-szene-block.zieht { cursor:grabbing;opacity:.85;z-index:5; }
.ize-szene-block button { position:absolute;left:4px;top:6px;width:18px!important;min-width:18px!important;
  height:20px;padding:0!important;border:0!important;background:transparent!important;color:inherit!important; }
.ize-szene-block b { display:block;font-size:9px;letter-spacing:.08em;white-space:nowrap;overflow:hidden; }
.ize-szene-block span { display:block;margin-top:6px;font-size:11px;line-height:1.3;min-height:54px;
  overflow:hidden;user-select:text;cursor:text;outline:none; }
.ize-szene-block span:focus { background:var(--ize-eingabe);padding:3px;border-radius:4px; }
.ize-szene-griff { position:absolute;top:0;bottom:0;width:7px;background:var(--spurfarbe);
  opacity:.5;cursor:ew-resize; }
.ize-szene-griff.links { left:0 }.ize-szene-griff.rechts { right:0 }
.ize-szene-playhead { position:absolute;top:0;bottom:0;width:2px;background:#fff;z-index:8;
  pointer-events:none;box-shadow:0 0 9px #fff;left:0; }
.ize-szene-zeit { display:flex;justify-content:space-between;font-size:10px;opacity:.48;margin-top:4px; }
.ize-szene-hinweis { font-size:11px;opacity:.58;margin-top:7px;min-height:16px; }
"""


TIMELINE_JS = r"""
const wurzel = element;
const szene = () => wurzel.querySelector('.ize-szene');
const bahn = () => wurzel.querySelector('[data-szenenbahn]');
const zeilen = () => Array.from(wurzel.querySelectorAll('[data-editor-zeile]'));
const zelle = (zeile, name) => zeile?.querySelector(`[data-feld="${name}"]`);
const zahl = (wert, fallback=0) => {
  const nummer = Number(String(wert ?? '').trim().replace(',', '.'));
  return Number.isFinite(nummer) ? nummer : fallback;
};
const entkomme = (wert) => String(wert ?? '').replace(/[&<>"']/g, zeichen => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
}[zeichen]));
const tiefFinden = (start, selector) => {
  if (!start) return null;
  if (start.querySelector) {
    const direkt = start.querySelector(selector);
    if (direkt) return direkt;
  }
  const elemente = start.querySelectorAll ? start.querySelectorAll('*') : [];
  for (const eintrag of elemente) {
    if (eintrag.shadowRoot) {
      const fund = tiefFinden(eintrag.shadowRoot, selector);
      if (fund) return fund;
    }
  }
  return null;
};
const tiefAlle = (start, selector, ergebnis=[]) => {
  if (!start) return ergebnis;
  if (start.matches?.(selector)) ergebnis.push(start);
  const elemente = start.querySelectorAll ? Array.from(start.querySelectorAll('*')) : [];
  for (const eintrag of elemente) {
    if (eintrag.matches?.(selector)) ergebnis.push(eintrag);
    if (eintrag.shadowRoot) tiefAlle(eintrag.shadowRoot, selector, ergebnis);
  }
  return ergebnis;
};
const geladenerTon = (basis) => {
  const kandidaten = tiefAlle(basis, 'audio', []);
  return kandidaten.find(ton =>
    Boolean(ton.currentSrc || ton.src || ton.querySelector?.('source[src]')) ||
    Number(ton.readyState || 0) > 0
  ) || null;
};
const player = () => {
  const wurzeln = [wurzel.getRootNode(), document];
  for (const basis of wurzeln) {
    const host = tiefFinden(basis, '#ize-szenen-player');
    const ton = geladenerTon(host);
    if (ton) return ton;
  }
  for (const basis of wurzeln) {
    const ton = geladenerTon(basis);
    if (ton) return ton;
  }
  return null;
};
const meldung = (text) => {
  const timelineFeld = wurzel.querySelector('[data-szenenmeldung]');
  const editorFeld = wurzel.querySelector('[data-editor-meldung]');
  if (timelineFeld) timelineFeld.textContent = text || '';
  if (editorFeld) editorFeld.textContent = text || '';
};
const leseZeilen = () => zeilen().map((zeile, index) => ({
  id:index + 1,
  speaker:(zelle(zeile, 'speaker')?.textContent || 'SPEAKER_00').trim(),
  start:Math.max(0, zahl(zelle(zeile, 'start')?.textContent, 0)),
  end:Math.max(0.08, zahl(zelle(zeile, 'end')?.textContent, 0.08)),
  original:(zelle(zeile, 'original')?.textContent || '').trim(),
  deutsch:(zelle(zeile, 'deutsch')?.textContent || '').trim()
}));
const nummeriere = () => {
  zeilen().forEach((zeile, index) => {
    zeile.dataset.editorZeile = String(index + 1);
    const id = zeile.querySelector('.ize-editor-id');
    if (id) id.textContent = String(index + 1);
  });
};
let speicherTimer = null;
let speicherLaeuft = false;
let erneutSpeichern = false;
const speichere = async (laut=false) => {
  window.clearTimeout(speicherTimer);
  speicherTimer = null;
  if (!server?.szene_editor_speichern) return;
  if (speicherLaeuft) {
    erneutSpeichern = true;
    return;
  }
  speicherLaeuft = true;
  if (laut) meldung('Änderungen werden gespeichert …');
  try {
    const antwort = await server.szene_editor_speichern({rows:leseZeilen()});
    if (antwort?.ok === false) throw new Error(antwort.fehler || 'Unbekannter Fehler');
    if (laut) meldung(`${antwort?.anzahl ?? zeilen().length} Segmente gespeichert.`);
  } catch (fehler) {
    meldung('Speichern fehlgeschlagen: ' + fehler);
  } finally {
    speicherLaeuft = false;
    if (erneutSpeichern) {
      erneutSpeichern = false;
      speichere(false);
    }
  }
};
const speichereSpaeter = () => {
  window.clearTimeout(speicherTimer);
  speicherTimer = window.setTimeout(() => speichere(false), 650);
};
const farben = ['#4d9bff','#ff4fd8','#22e0ff','#ffc857','#7ff0b0','#ad8cff'];
const farbeFuer = (name) => {
  const namen = [];
  leseZeilen().forEach(zeile => {
    if (!namen.includes(zeile.speaker)) namen.push(zeile.speaker);
  });
  return farben[Math.max(0, namen.indexOf(name)) % farben.length];
};
const renderLegende = () => {
  const legende = wurzel.querySelector('.ize-szene-legende');
  if (!legende) return;
  const gesehen = [];
  legende.innerHTML = leseZeilen().map(zeile => {
    if (gesehen.includes(zeile.speaker)) return '';
    gesehen.push(zeile.speaker);
    const farbe = farbeFuer(zeile.speaker);
    return `<span><i style="background:${farbe}"></i>${entkomme(zeile.speaker)}</span>`;
  }).join('');
};
const renderBloecke = () => {
  const b = bahn(), s = szene();
  if (!b || !s) return;
  const dauer = Math.max(.1, zahl(s.dataset.dauer, 0.1));
  b.querySelectorAll('.ize-szene-block').forEach(block => block.remove());
  leseZeilen().forEach(zeile => {
    const start = Math.max(0, Math.min(dauer, zeile.start));
    const ende = Math.max(start + .08, Math.min(dauer, zeile.end));
    const block = document.createElement('div');
    block.className = 'ize-szene-block';
    block.dataset.id = String(zeile.id);
    block.dataset.start = start.toFixed(3);
    block.dataset.end = ende.toFixed(3);
    block.style.left = `${100 * start / dauer}%`;
    block.style.width = `${Math.max(.35, 100 * (ende-start) / dauer)}%`;
    block.style.setProperty('--spurfarbe', farbeFuer(zeile.speaker));
    block.innerHTML =
      `<i class="ize-szene-griff links" data-griff="links"></i>` +
      `<button type="button" data-spielen="${zeile.id}" title="Segment abspielen">▶</button>` +
      `<b>${entkomme(zeile.speaker)}</b>` +
      `<span contenteditable="true" data-szenentext="${zeile.id}">${entkomme(zeile.deutsch || zeile.original || 'Text eingeben')}</span>` +
      `<i class="ize-szene-griff rechts" data-griff="rechts"></i>`;
    b.appendChild(block);
  });
  renderLegende();
};
const sekunden = (event) => {
  const b = bahn(), s = szene();
  if (!b || !s) return 0;
  const r = b.getBoundingClientRect();
  return Math.max(0, Math.min(Number(s.dataset.dauer || 0),
    ((event.clientX - r.left) / Math.max(1, r.width)) * Number(s.dataset.dauer || 0)));
};
let zug = null;
let spielEnde = null;
let letzterCursor = null;
const offsetImFeld = (feld, container, offset) => {
  if (!feld || !container || !feld.contains(container)) return null;
  try {
    const bereich = feld.ownerDocument.createRange();
    bereich.selectNodeContents(feld);
    bereich.setEnd(container, offset);
    return bereich.toString().length;
  } catch (_) {
    return null;
  }
};
const cursorPosition = (feld) => {
  const auswahl =
    feld?.getRootNode?.()?.getSelection?.() ||
    feld?.ownerDocument?.defaultView?.getSelection?.() ||
    window.getSelection?.() ||
    document.getSelection?.();
  if (!feld || !auswahl || !auswahl.rangeCount) return null;
  const bereich = auswahl.getRangeAt(0);
  return offsetImFeld(feld, bereich.startContainer, bereich.startOffset);
};
const cursorAusPunkt = (feld, event) => {
  if (!feld || !event) return null;
  const dokument = feld.ownerDocument;
  const rechteck = feld.getBoundingClientRect();
  const text = feld.textContent || '';
  const anteil = rechteck.width > 0
    ? Math.max(0, Math.min(1, (event.clientX-rechteck.left) / rechteck.width))
    : 0;
  const plausibel = (wert) => (
    wert !== null &&
    !(wert === 0 && anteil > .12) &&
    !(wert === text.length && anteil < .88)
  );
  try {
    const position = dokument.caretPositionFromPoint?.(event.clientX, event.clientY);
    const wert = offsetImFeld(feld, position?.offsetNode, position?.offset);
    if (plausibel(wert)) return wert;
  } catch (_) {}
  try {
    const bereich = dokument.caretRangeFromPoint?.(event.clientX, event.clientY);
    const wert = offsetImFeld(feld, bereich?.startContainer, bereich?.startOffset);
    if (plausibel(wert)) return wert;
  } catch (_) {}
  if (!text || rechteck.width <= 0) return null;
  return Math.round(text.length * anteil);
};
const merkeCursor = (feld) => {
  if (!feld?.matches?.('[data-feld="original"],[data-feld="deutsch"]')) return;
  const position = cursorPosition(feld);
  if (position !== null) {
    feld.dataset.izeCursor = String(position);
    letzterCursor = {feld, position};
  }
};
const merkeCursorAusEreignis = (event) => {
  const feld = event.target.closest?.('[data-feld="original"],[data-feld="deutsch"]');
  if (!feld) return;
  merkeCursor(feld);
  const position = cursorAusPunkt(feld, event);
  if (position !== null) {
    feld.dataset.izeCursor = String(position);
    letzterCursor = {feld, position};
  }
};
const trenneNahe = (text, position) => {
  const wert = String(text || '');
  if (position <= 0 || position >= wert.length) return [wert.trim(), ''];
  let links = position, rechts = position;
  while (links > 0 && !/\s/.test(wert[links-1])) links--;
  while (rechts < wert.length && !/\s/.test(wert[rechts])) rechts++;
  const schnitt = position-links <= rechts-position ? links : rechts;
  return [wert.slice(0, schnitt).trim(), wert.slice(schnitt).trim()];
};
const teileZeile = (zeile, feld=null, position=null) => {
  if (!zeile) return;
  feld = feld || (
    letzterCursor?.feld?.closest('[data-editor-zeile]') === zeile
      ? letzterCursor.feld
      : zelle(zeile, 'deutsch')
  );
  const name = feld?.dataset?.feld;
  if (!['original','deutsch'].includes(name)) {
    meldung('Cursor zuerst in Original- oder deutschen Text setzen.');
    return;
  }
  const text = feld.textContent || '';
  position = position ?? (
    letzterCursor?.feld === feld
      ? letzterCursor.position
      : zahl(feld.dataset.izeCursor, cursorPosition(feld))
  );
  if (!(position > 0 && position < text.length)) {
    meldung('Cursor innerhalb des Textes platzieren und dann teilen.');
    return;
  }
  const ratio = position / Math.max(1, text.length);
  const anderes = name === 'original' ? 'deutsch' : 'original';
  const teileAktiv = [text.slice(0, position).trim(), text.slice(position).trim()];
  const andererText = zelle(zeile, anderes)?.textContent || '';
  const teileAndere = trenneNahe(andererText, Math.round(andererText.length * ratio));
  const start = zahl(zelle(zeile, 'start')?.textContent, 0);
  const ende = Math.max(start + .08, zahl(zelle(zeile, 'end')?.textContent, start + .08));
  const schnittZeit = Math.max(start + .04, Math.min(ende - .04, start + (ende-start) * ratio));
  const neu = zeile.cloneNode(true);
  zelle(zeile, name).textContent = teileAktiv[0];
  zelle(neu, name).textContent = teileAktiv[1];
  zelle(zeile, anderes).textContent = teileAndere[0];
  zelle(neu, anderes).textContent = teileAndere[1];
  zelle(zeile, 'end').textContent = schnittZeit.toFixed(3);
  zelle(neu, 'start').textContent = schnittZeit.toFixed(3);
  zeile.after(neu);
  nummeriere();
  letzterCursor = null;
  renderBloecke();
  speichere(false);
  meldung('Segment am Cursor geteilt.');
};
const verbindeNaechste = (zeile) => {
  const naechste = zeile?.nextElementSibling;
  if (!zeile || !naechste?.matches('[data-editor-zeile]')) {
    meldung('Es gibt keine nächste Zeile zum Verbinden.');
    return;
  }
  for (const name of ['original','deutsch']) {
    const links = (zelle(zeile, name)?.textContent || '').trim();
    const rechts = (zelle(naechste, name)?.textContent || '').trim();
    zelle(zeile, name).textContent = [links, rechts].filter(Boolean).join(' ');
  }
  zelle(zeile, 'end').textContent = (
    Math.max(
      zahl(zelle(zeile, 'end')?.textContent, 0),
      zahl(zelle(naechste, 'end')?.textContent, 0)
    )
  ).toFixed(3);
  naechste.remove();
  nummeriere();
  letzterCursor = null;
  renderBloecke();
  speichere(false);
  meldung('Segment mit der nächsten Zeile verbunden.');
};
const spiele = (start, ende=null) => {
  const ton = player();
  if (!ton) {
    meldung('Audioplayer nicht gefunden. Originalvorschau oben einmal laden oder abspielen.');
    return;
  }
  ton.currentTime = Math.max(0, zahl(start, 0));
  spielEnde = ende === null ? null : Math.max(ton.currentTime + .02, zahl(ende, ton.currentTime));
  const versuch = ton.play();
  if (versuch?.catch) versuch.catch(fehler => meldung('Wiedergabe nicht möglich: ' + fehler));
};
wurzel.addEventListener('pointerdown', (event) => {
  if (event.target.closest('[data-zeile-teilen]')) event.preventDefault();
}, true);
wurzel.addEventListener('selectionchange', () => {
  merkeCursor(document.activeElement);
});
wurzel.addEventListener('keyup', (event) => merkeCursor(event.target));
wurzel.addEventListener('mouseup', (event) => {
  merkeCursorAusEreignis(event);
});
wurzel.addEventListener('pointerdown', (event) => {
  const block = event.target.closest('.ize-szene-block');
  if (!block || event.target.closest('button') || event.target.closest('[contenteditable]')) return;
  const dauer = Number(szene().dataset.dauer || 0);
  const art = event.target.dataset.griff || 'move';
  zug = { block, art, x:event.clientX, start:Number(block.dataset.start), end:Number(block.dataset.end), dauer };
  block.classList.add('zieht');
  block.setPointerCapture(event.pointerId);
  event.preventDefault();
});
wurzel.addEventListener('pointermove', (event) => {
  if (!zug) return;
  const r = bahn().getBoundingClientRect();
  const delta = ((event.clientX - zug.x) / Math.max(1, r.width)) * zug.dauer;
  let start=zug.start, ende=zug.end;
  if (zug.art === 'links') start = Math.max(0, Math.min(ende-.08, zug.start+delta));
  else if (zug.art === 'rechts') ende = Math.min(zug.dauer, Math.max(start+.08, zug.end+delta));
  else {
    const laenge=ende-start;
    start=Math.max(0,Math.min(zug.dauer-laenge,zug.start+delta)); ende=start+laenge;
  }
  zug.block.dataset.start=start.toFixed(3); zug.block.dataset.end=ende.toFixed(3);
  zug.block.style.left=(100*start/zug.dauer)+'%';
  zug.block.style.width=(100*(ende-start)/zug.dauer)+'%';
});
wurzel.addEventListener('pointerup', (event) => {
  merkeCursorAusEreignis(event);
  if (!zug) return;
  const aktuell=zug; zug=null; aktuell.block.classList.remove('zieht');
  const zeile = zeilen()[Math.max(0, Number(aktuell.block.dataset.id)-1)];
  if (zeile) {
    zelle(zeile, 'start').textContent = Number(aktuell.block.dataset.start).toFixed(3);
    zelle(zeile, 'end').textContent = Number(aktuell.block.dataset.end).toFixed(3);
    speichere(false);
    meldung('Zeitposition gespeichert.');
  }
});
wurzel.addEventListener('click', (event) => {
  const speichern = event.target.closest('[data-editor-speichern]');
  if (speichern) {
    event.preventDefault(); event.stopPropagation();
    nummeriere(); renderBloecke(); speichere(true);
    return;
  }
  const zeile = event.target.closest('[data-editor-zeile]');
  if (event.target.closest('[data-zeile-spielen]')) {
    event.preventDefault(); event.stopPropagation();
    spiele(
      zahl(zelle(zeile, 'start')?.textContent, 0),
      zahl(zelle(zeile, 'end')?.textContent, 0)
    );
    return;
  }
  if (event.target.closest('[data-zeile-teilen]')) {
    event.preventDefault(); event.stopPropagation();
    teileZeile(zeile);
    return;
  }
  if (event.target.closest('[data-zeile-verbinden]')) {
    event.preventDefault(); event.stopPropagation();
    verbindeNaechste(zeile);
    return;
  }
  const ganz = event.target.closest('[data-gesamt-spielen]');
  if (ganz) {
    event.preventDefault(); event.stopPropagation();
    const ton=player();
    if (!ton) { meldung('Audiovorschau ist noch nicht geladen.'); return; }
    spielEnde=null;
    if (ton.ended || ton.currentTime >= Number(szene()?.dataset.dauer || 0)-.05) ton.currentTime=0;
    const versuch=ton.play();
    if (versuch?.catch) versuch.catch((e)=>meldung('Wiedergabe nicht möglich: '+e));
    return;
  }
  const pause = event.target.closest('[data-gesamt-pause]');
  if (pause) {
    event.preventDefault(); event.stopPropagation();
    const ton=player(); if (ton) ton.pause();
    spielEnde=null;
    return;
  }
  const knop = event.target.closest('[data-spielen]');
  if (knop) {
    event.preventDefault(); event.stopPropagation();
    const block=knop.closest('.ize-szene-block');
    if (block) spiele(block.dataset.start, block.dataset.end);
    return;
  }
  if (event.target.closest('.ize-szene-bahn') && !event.target.closest('.ize-szene-block')) {
    spiele(sekunden(event), null);
  }
});
wurzel.addEventListener('keydown', (event) => {
  const feld = event.target.closest('[data-feld="original"],[data-feld="deutsch"]');
  if (feld && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    teileZeile(feld.closest('[data-editor-zeile]'), feld);
  }
});
wurzel.addEventListener('input', (event) => {
  const feld = event.target.closest('[data-feld]');
  if (feld) {
    speichereSpaeter();
    return;
  }
  const timelineText = event.target.closest('[data-szenentext]');
  if (timelineText) {
    const zeile = zeilen()[Math.max(0, Number(timelineText.dataset.szenentext)-1)];
    if (zeile) {
      zelle(zeile, 'deutsch').textContent = timelineText.textContent || '';
      speichereSpaeter();
    }
  }
});
wurzel.addEventListener('focusout', (event) => {
  if (event.target.closest('[data-feld],[data-szenentext]')) {
    nummeriere();
    renderBloecke();
    speichere(false);
  }
});
const takt = () => {
  const ton=player(), s=szene(); if (!ton || !s) return;
  const zeit=Number(ton.currentTime||0), dauer=Number(s.dataset.dauer||1);
  if (spielEnde !== null && zeit >= spielEnde-.03) {
    ton.pause(); spielEnde=null;
  }
  const kopf=wurzel.querySelector('[data-playhead]'); if(kopf) kopf.style.left=(100*zeit/dauer)+'%';
  const zeitfeld=wurzel.querySelector('[data-szenenzeit]');
  if (zeitfeld) {
    const fmt=(wert)=>Math.floor(wert/60)+':'+String(Math.floor(wert%60)).padStart(2,'0');
    zeitfeld.textContent=fmt(zeit)+' / '+fmt(dauer);
  }
  wurzel.querySelectorAll('.ize-szene-block').forEach(block => {
    const aktiv=zeit>=Number(block.dataset.start)&&zeit<=Number(block.dataset.end)&&!ton.paused;
    block.classList.toggle('aktiv',aktiv);
  });
};
if (wurzel.__izeSzenenTimer) window.clearInterval(wurzel.__izeSzenenTimer);
wurzel.__izeSzenenTimer = window.setInterval(takt,100);
"""
