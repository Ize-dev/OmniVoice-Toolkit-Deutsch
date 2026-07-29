#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deutsche Bedienoberflaeche fuer OmniVoice - laeuft INNERHALB der venv.

Ersetzt die englische Standard-Oberflaeche (omnivoice-demo) durch eine
aufgeraeumte deutsche Fassung mit drei Betriebsarten:

  * Stimme klonen  - Sprachprobe hochladen oder aufnehmen, Text sprechen lassen
  * Ueberraschung  - das Modell sucht sich selbst eine Stimme aus
  * Stapel (Batch) - ganze Projekte ueber eine CSV-Liste vertonen

Aufruf:
    python oberflaeche.py --ip 127.0.0.1 --port 7860 --ausgabe <ordner>

Rueckgabecodes:
    0  normal beendet
    4  diese Oberflaeche ist nicht startbar -> das Studio faellt auf die
       mitgelieferte Standard-Oberflaeche zurueck
"""

import argparse
import csv
import html
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import messwerte  # noqa: E402
import tabelle  # noqa: E402
import listengenerator  # noqa: E402
import whisper_dienst  # noqa: E402
from motor import (ABTASTRATE, MODELL, MOTOR, als_array, audiolaenge,  # noqa: E402
                   baue_argumente, empfohlene_arbeiter, fuehre_auftrag_aus,
                   nachbearbeiten, sag, schreibe_wav)
from pool import VERWALTUNG  # noqa: E402

LAUTSTAERKE_WAHL = {
    "aus": "aus",
    "feste Verstärkung": "db",
    "an das Original angleichen": "wie_original",
}
THEMEN = [
    "Crimson", "Darkmore", "Default", "Dracula", "Fallout", "Flashbang",
    "Hyrule", "Nordic", "Pixel", "Retro", "Scene",
]
THEMEN_ALIASE = {
    "Crimson Sands": "Crimson",
    "Nordic Frost": "Nordic",
    "Pixel Console": "Pixel",
    "Retro Grid": "Retro",
    "Scene NFO": "Scene",
}


def normalisiere_theme(name) -> str:
    """Akzeptiert auch Theme-Namen aus älteren gespeicherten Einstellungen."""
    name = str(name or "Default")
    name = THEMEN_ALIASE.get(name, name)
    return name if name in THEMEN else "Default"

EXIT_NICHT_STARTBAR = 4

AUDIO_ENDUNGEN = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".wem"}

BEISPIEL_TEXT = (
    "Das hier ist meine geklonte Stimme. "
    "Sie spricht jeden Text, den ich eingebe – und das komplett auf diesem Rechner."
)

BEISPIEL_CSV = (
    "C:\\Projekte\\Habitat\\content\\audio\\wwise\\stimme.wav;"
    "This is the original English line.;Das ist die deutsche Zeile."
)

STANDARD_ERSETZUNGEN = "\\r =>\n\\n =>"

# ------------------------------------------------------------
# Aussehen
# ------------------------------------------------------------

CSS = """
:root {
    --ize-magenta: #ff4fd8;
    --ize-cyan: #22e0ff;
    --ize-blau: #4d9bff;
    --ize-tief: #0b0d15;
    --ize-seitenhintergrund: radial-gradient(1400px 700px at 12% -10%, #1d2136 0%, #0b0d15 60%);
    --ize-kopftext: #eaf2ff;
    --ize-text: #eaf2ff;
    --ize-muted: #9ba8bd;
    --ize-flaeche: rgba(20, 24, 38, .68);
    --ize-flaeche-stark: #121524;
    --ize-eingabe: rgba(7, 9, 16, .72);
    --ize-rand: rgba(255,255,255,.10);
    --ize-schatten: rgba(0,0,0,.42);
}
html, body {
    background: var(--ize-flaeche-stark) !important;
    color: var(--ize-text) !important;
    transition: background-color .36s ease, color .28s ease;
}
.gradio-container {
    background: var(--ize-seitenhintergrund) fixed !important;
    color: var(--ize-text) !important;
    max-width: 100% !important;
    width: 100% !important;
    padding-left: 20px !important;
    padding-right: 20px !important;
    transition: background .42s ease, color .28s ease;
    animation: ize-seite-rein .42s cubic-bezier(.2,.75,.25,1) both;
}
.gradio-container > .main, .gradio-container .wrap, .app { max-width: 100% !important; }
#ize-kopf {
    border: 1px solid rgba(34, 224, 255, .35);
    border-radius: 14px;
    padding: 16px 22px 12px 22px;
    margin-bottom: 6px;
    background: linear-gradient(135deg, rgba(255,79,216,.10), rgba(34,224,255,.07));
    box-shadow: 0 0 40px rgba(255, 79, 216, .10);
}
#ize-kopf h1 {
    margin: 0; font-size: 26px; letter-spacing: .34em; font-weight: 800;
    display: inline-block; color: var(--ize-kopftext, #eaf2ff) !important;
    background: none !important; -webkit-text-fill-color: currentColor !important;
    text-shadow: 0 0 18px rgba(34,224,255,.30);
}
#ize-streifen {
    height: 3px; margin-top: 12px; border-radius: 3px;
    background: linear-gradient(90deg, var(--ize-magenta), var(--ize-cyan), var(--ize-magenta));
    background-size: 200% 100%; animation: ize-fluss 6s linear infinite;
}
@keyframes ize-fluss { from { background-position: 0 0; } to { background-position: 200% 0; } }
#ize-fuss {
    text-align: center; font-size: 12px; opacity: .6; padding: 14px 0 4px 0; letter-spacing: .08em;
}
#ize-fuss b { color: var(--ize-blau); letter-spacing: .25em; font-weight: 800; }
.ize-karte {
    border: 1px solid var(--ize-rand) !important;
    border-radius: 12px !important;
    background: var(--ize-flaeche) !important;
    padding: 14px !important;
    box-shadow: 0 10px 30px -24px var(--ize-schatten);
    transition: transform .22s cubic-bezier(.2,.8,.2,1), border-color .22s ease,
                background .32s ease, box-shadow .22s ease;
}
.ize-karte:hover {
    border-color: color-mix(in srgb, var(--ize-cyan) 38%, transparent) !important;
    box-shadow: 0 18px 38px -25px var(--ize-schatten);
}
#ize-los, #ize-stapel-los { font-size: 17px !important; font-weight: 700 !important; letter-spacing: .06em; }
.ize-tipp { font-size: 12.5px; opacity: .7; line-height: 1.65; }

/* Aufklappbare Bereiche: dauerhaft als anklickbar erkennbar, beim Überfahren
   deutlich hervorgehoben. .label-wrap ist Gradios Kopfzeile eines Accordions. */
.label-wrap {
    border-radius: 9px;
    background: rgba(255,255,255,.035);
    box-shadow: inset 2px 0 0 rgba(77,155,255,.35);
    transition: background .18s ease, box-shadow .18s ease, color .18s ease,
                transform .18s ease;
}
.label-wrap:hover {
    background: linear-gradient(90deg, rgba(77,155,255,.20), rgba(255,79,216,.06));
    box-shadow: inset 3px 0 0 var(--ize-blau, #4d9bff);
    color: #eaf2ff;
    transform: translateX(2px);
}
.label-wrap:hover span, .label-wrap:hover .icon { color: #eaf2ff; opacity: 1; }
.label-wrap.open { box-shadow: inset 2px 0 0 var(--ize-cyan, #22e0ff); }

/* ---------- Stapel-Anzeige ---------- */
.ize-batch {
    border: 1px solid rgba(34,224,255,.28); border-radius: 14px; padding: 16px 18px 14px 18px;
    background: linear-gradient(160deg, rgba(34,224,255,.06), rgba(255,79,216,.05));
    transition: background .32s ease, border-color .25s ease, box-shadow .25s ease;
}
.ize-batch-kopf { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; flex-wrap: wrap; }
.ize-batch-titel { font-size: 15px; font-weight: 800; letter-spacing: .22em; color: var(--ize-cyan); }
.ize-batch-titel.fertig { color: #46e08a; }
.ize-batch-titel.fehler { color: #ff6b6b; }
.ize-batch-datei { font-size: 12.5px; opacity: .72; font-family: ui-monospace, Consolas, monospace;
                   overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 62%; }
.ize-bar { height: 16px; border-radius: 8px; margin: 12px 0 4px 0; overflow: hidden;
           background: rgba(255,255,255,.07); box-shadow: inset 0 0 8px rgba(0,0,0,.45); }
.ize-bar-fuell {
    height: 100%; border-radius: 8px; transition: width .35s ease;
    background: linear-gradient(90deg, var(--ize-magenta, #ff4fd8),
                                       var(--ize-blau, #4d9bff),
                                       var(--ize-cyan, #22e0ff));
    background-size: 250% 100%; animation: ize-fluss 3.5s linear infinite;
    box-shadow: 0 0 18px rgba(77,155,255,.55);
}
/* Fertiger Stapel: ruhiges Blau mit Glow, passend zum iZE in der Fußzeile. */
.ize-bar-fuell.fertig {
    background: linear-gradient(90deg, #2f7dff, #4d9bff, #8ecbff);
    background-size: 100% 100%;
    animation: ize-glimmen 2.6s ease-in-out infinite;
    box-shadow: 0 0 22px rgba(77,155,255,.85), 0 0 48px rgba(77,155,255,.40);
}
@keyframes ize-glimmen {
    0%, 100% { box-shadow: 0 0 18px rgba(77,155,255,.65), 0 0 36px rgba(77,155,255,.28); }
    50%      { box-shadow: 0 0 26px rgba(77,155,255,.95), 0 0 56px rgba(77,155,255,.50); }
}
.ize-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
    gap: 10px; margin-top: 14px;
}
.ize-grid > div {
    background: rgba(0,0,0,.28); border: 1px solid rgba(255,255,255,.06);
    border-radius: 10px; padding: 9px 11px;
}
.ize-grid b { display: block; font-size: 19px; font-weight: 800; color: #eaf2ff; line-height: 1.25; }
.ize-grid span { display: block; font-size: 11px; opacity: .62; letter-spacing: .06em; margin-top: 2px; }
.ize-grid .warn b { color: #ffc857; }
.ize-grid .schlecht b { color: #ff6b6b; }
footer { display: none !important; }

button, .button, .tab-nav button {
    transition: transform .16s ease, filter .18s ease, background .28s ease,
                border-color .22s ease, color .22s ease, box-shadow .22s ease !important;
}
button:hover, .button:hover { transform: translateY(-1px); filter: brightness(1.08); }
button:active, .button:active { transform: translateY(0) scale(.985); }
.tab-nav button.selected {
    box-shadow: inset 0 -2px 0 var(--ize-cyan), 0 8px 22px -18px var(--ize-cyan);
}
/* Textfelder dürfen mit background: gestaltet werden. Bei Checkboxen und
   Radios würde das Kurzformat jedoch Gradios background-image (Haken/Punkt)
   löschen. Darum werden die Auswahlfelder hier ausdrücklich ausgenommen. */
input:not([type="checkbox"]):not([type="radio"]):not([type="range"]),
textarea, select {
    transition: background-color .30s ease, color .22s ease, border-color .22s ease,
                box-shadow .22s ease !important;
}
input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):focus,
textarea:focus, select:focus {
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--ize-cyan) 28%, transparent) !important;
}
@keyframes ize-seite-rein {
    from { opacity: 0; }
    to { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: .01ms !important;
        animation-iteration-count: 1 !important;
        scroll-behavior: auto !important;
        transition-duration: .01ms !important;
    }
}
"""

KOPF_HTML = """
<div id="ize-kopf">
  <h1>OMNIVOICE STUDIO</h1>
  <div id="ize-streifen"></div>
</div>
"""

FUSS_HTML = """
<div id="ize-fuss">
  OMNIVOICE STUDIO · deutsche Fassung von <b>iZE</b> · läuft lokal auf {geraet}<br>
  Modell: k2-fsa/OmniVoice · Ausgabe: 24 kHz Mono
</div>
"""

# Laeuft im Browser, sobald ein Stapel durch ist: kurzer Dreiklang und optional
# eine Benachrichtigung des Betriebssystems. Der Ton wird per WebAudio erzeugt,
# damit keine Tondatei mitgeliefert werden muss.
MELDUNG_JS = """
(ton, hinweis, blinken, protokoll) => {
  try {
    const zeilen = String(protokoll || "").trim().split("\\n").reverse();
    const text = (zeilen.find(z => z.startsWith("FERTIG:")) || "Der Stapel ist durch.").trim();
    if (blinken && !document.hasFocus()) {
      const alt = window.__izeTitel || document.title;
      window.__izeTitel = alt;
      if (window.__izeBlinken) clearInterval(window.__izeBlinken);
      let an = false;
      window.__izeBlinken = setInterval(() => {
        an = !an;
        document.title = an ? "✅ FERTIG · OmniVoice" : alt;
      }, 900);
      const aufhoeren = () => {
        clearInterval(window.__izeBlinken);
        window.__izeBlinken = null;
        document.title = alt;
        window.removeEventListener("focus", aufhoeren);
        document.removeEventListener("visibilitychange", aufhoeren);
      };
      window.addEventListener("focus", aufhoeren);
      document.addEventListener("visibilitychange", aufhoeren);
      setTimeout(aufhoeren, 120000);
    }
    if (ton) {
      const Klang = window.AudioContext || window.webkitAudioContext;
      if (Klang) {
        const ctx = new Klang();
        [660, 880, 1320].forEach((hz, i) => {
          const t0 = ctx.currentTime + i * 0.16;
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.type = "sine"; o.frequency.value = hz;
          g.gain.setValueAtTime(0.0001, t0);
          g.gain.exponentialRampToValueAtTime(0.22, t0 + 0.03);
          g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.30);
          o.connect(g); g.connect(ctx.destination);
          o.start(t0); o.stop(t0 + 0.32);
        });
        setTimeout(() => { try { ctx.close(); } catch (e) {} }, 2500);
      }
    }
    if (hinweis && "Notification" in window) {
      const zeigen = () => new Notification("OmniVoice Studio", {
        body: text, tag: "ize-stapel", requireInteraction: false });
      if (Notification.permission === "granted") { zeigen(); }
      else if (Notification.permission !== "denied") {
        Notification.requestPermission().then(p => { if (p === "granted") zeigen(); });
      }
    }
  } catch (e) { console.warn("OmniVoice-Benachrichtigung:", e); }
}
"""

# Bedienung der Liste. Laeuft als js_on_load der HTML-Komponente; »element«
# ist deren Wurzel, ueber »server« lassen sich die Python-Funktionen aufrufen.
# Die Ereignisse haengen an der Wurzel, nicht an den Zeilen - sie ueberleben
# damit jedes Neuzeichnen der Tabelle.
LISTE_JS = """
const ton = window.__izeAutoplayTon || new Audio();
window.__izeAutoplayTon = ton;
const autoplayFreigeben = () => {
  try {
    ton.pause();
    ton.muted = true;
    ton.src = 'data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
    const versuch = ton.play();
    if (versuch && versuch.then) {
      versuch.then(() => {
        ton.pause();
        ton.currentTime = 0;
        ton.muted = false;
      }).catch(() => { ton.muted = false; });
    } else {
      ton.pause();
      ton.muted = false;
    }
  } catch (e) { ton.muted = false; }
};
const melde = (text) => {
  const feld = element.querySelector('[data-ize-meldung]');
  if (feld) feld.textContent = text || '';
};
const spiele = (uri, start, welle) => {
  try {
    ton.pause();
    element.querySelectorAll('.ize-welle.spielt').forEach(w => w.classList.remove('spielt'));
    ton.src = uri;
    ton.addEventListener('loadedmetadata', () => {
      try { if (start > 0) ton.currentTime = start; } catch (e) {}
      ton.play().catch(() => melde('Der Browser kann dieses Format nicht abspielen.'));
    }, { once: true });
    ton.load();
    if (welle) {
      welle.classList.add('spielt');
      ton.addEventListener('ended', () => welle.classList.remove('spielt'), { once: true });
    }
  } catch (e) { melde('Abspielen nicht möglich: ' + e); }
};

const textEditorOeffnen = async (nummer, tabellenzeile) => {
  melde('Texte für Zeile ' + nummer + ' werden geladen …');
  try {
    const daten = await server.zeile_editor({ nr: nummer });
    if (!daten || daten.fehler) { melde((daten && daten.fehler) || 'Editor nicht verfügbar.'); return; }
    const dialog = document.createElement('dialog');
    dialog.className = 'ize-editor';
    dialog.innerHTML = `
      <div style="font-size:16px;font-weight:850;letter-spacing:.08em">TEXT ZUORDNEN · ZEILE ${nummer}</div>
      <div style="font-size:11px;opacity:.55;margin-top:5px">
        Ein Listentreffer übernimmt automatisch Englisch und Deutsch. Beide Felder bleiben manuell änderbar.
      </div>
      <div class="ize-editor-audios">
        <section>
          <b>ENGLISCHES ORIGINAL</b>
          <audio controls preload="metadata" data-ize-editor-audio="en"></audio>
          <small data-ize-editor-audio-status="en">Audio wird geladen …</small>
        </section>
        <section>
          <b>DEUTSCHES ERGEBNIS</b>
          <audio controls preload="metadata" data-ize-editor-audio="de"></audio>
          <small data-ize-editor-audio-status="de">Audio wird geladen …</small>
        </section>
      </div>
      <label>ENGLISCHER TEXT</label>
      <textarea data-ize-editor-en></textarea>
      <div style="display:flex;gap:7px;margin-top:7px">
        <input data-ize-suche-en placeholder="Englische Liste durchsuchen">
        <button type="button" class="ize-knopf" data-ize-suchen="en" style="width:150px">EN suchen</button>
      </div>
      <div class="ize-editor-treffer" data-ize-treffer-en></div>
      <label>DEUTSCHER TEXT</label>
      <textarea data-ize-editor-de></textarea>
      <div style="display:flex;gap:7px;margin-top:7px">
        <input data-ize-suche-de placeholder="Deutsche Liste durchsuchen">
        <button type="button" class="ize-knopf" data-ize-suchen="de" style="width:150px">DE suchen</button>
      </div>
      <div class="ize-editor-treffer" data-ize-treffer-de></div>
      <div class="ize-editor-aktionen">
        <button type="button" class="ize-knopf" data-ize-editor-abbruch style="width:120px">Abbrechen</button>
        <button type="button" class="ize-knopf" data-ize-editor-speichern style="width:180px">Texte speichern</button>
      </div>`;
    element.appendChild(dialog);
    const enFeld = dialog.querySelector('[data-ize-editor-en]');
    const deFeld = dialog.querySelector('[data-ize-editor-de]');
    enFeld.value = daten.englisch || '';
    deFeld.value = daten.deutsch || '';
    dialog.querySelector('[data-ize-suche-en]').value = daten.englisch || '';
    dialog.querySelector('[data-ize-suche-de]').value = daten.deutsch || '';

    const audioLaden = async (sprache) => {
      const audio = dialog.querySelector(`[data-ize-editor-audio="${sprache}"]`);
      const status = dialog.querySelector(`[data-ize-editor-audio-status="${sprache}"]`);
      try {
        const antwort = await server.zeile_ton({
          nr: nummer, welche: sprache, anteil: 0
        });
        if (!antwort || !antwort.uri) {
          audio.hidden = true;
          status.textContent = (antwort && antwort.fehler) || 'Keine Audiodatei vorhanden.';
          return;
        }
        audio.src = antwort.uri;
        status.textContent = antwort.name || 'Audio bereit';
      } catch (fehler) {
        audio.hidden = true;
        status.textContent = 'Audio konnte nicht geladen werden: ' + fehler;
      }
    };
    Promise.all([audioLaden('en'), audioLaden('de')]);

    const suchen = async (sprache) => {
      const suchfeld = dialog.querySelector(`[data-ize-suche-${sprache}]`);
      const ziel = dialog.querySelector(`[data-ize-treffer-${sprache}]`);
      ziel.textContent = 'sucht …';
      try {
        const antwort = await server.zeile_text_suchen({
          nr: nummer, sprache: sprache, suche: suchfeld.value || ''
        });
        ziel.textContent = '';
        for (const treffer of ((antwort && antwort.treffer) || [])) {
          const knopf = document.createElement('button');
          knopf.type = 'button';
          const haupt = document.createElement('span');
          const neben = document.createElement('small');
          haupt.textContent = sprache === 'de' ? treffer.deutsch : treffer.englisch;
          neben.textContent = sprache === 'de' ? treffer.englisch : treffer.deutsch;
          knopf.append(haupt, neben);
          knopf.addEventListener('click', () => {
            enFeld.value = treffer.englisch || '';
            deFeld.value = treffer.deutsch || '';
            melde('Beide Sprachen aus Zeile ' + treffer.nummer + ' übernommen.');
          });
          ziel.appendChild(knopf);
        }
        if (!ziel.children.length) ziel.textContent = 'Kein Treffer.';
      } catch (fehler) { ziel.textContent = 'Suche fehlgeschlagen: ' + fehler; }
    };
    dialog.querySelectorAll('[data-ize-suchen]').forEach(knopf => {
      knopf.addEventListener('click', () => suchen(knopf.getAttribute('data-ize-suchen')));
    });
    dialog.querySelector('[data-ize-editor-abbruch]').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-ize-editor-speichern]').addEventListener('click', async () => {
      const speichern = dialog.querySelector('[data-ize-editor-speichern]');
      speichern.disabled = true; speichern.textContent = 'speichert …';
      try {
        const antwort = await server.zeile_text_speichern({
          nr: nummer, englisch: enFeld.value, deutsch: deFeld.value
        });
        if (!antwort || !antwort.ok) throw new Error((antwort && antwort.meldung) || 'Speichern fehlgeschlagen');
        if (antwort.zeile && tabellenzeile) tabellenzeile.outerHTML = antwort.zeile;
        melde(antwort.meldung || 'Texte gespeichert.');
        dialog.close();
      } catch (fehler) {
        speichern.disabled = false; speichern.textContent = 'Texte speichern';
        melde('Fehler: ' + fehler);
      }
    });
    dialog.addEventListener('close', () => dialog.remove(), { once: true });
    dialog.showModal();
  } catch (fehler) { melde('Editor konnte nicht geöffnet werden: ' + fehler); }
};

element.addEventListener('click', async (ereignis) => {
  const textKnopf = ereignis.target.closest('[data-ize-text]');
  if (textKnopf) {
    await textEditorOeffnen(
      textKnopf.getAttribute('data-ize-text'), textKnopf.closest('tr')
    );
    return;
  }
  const knopf = ereignis.target.closest('[data-ize-neu]');
  if (knopf) {
    if (knopf.disabled) return;
    // Direkt im echten Klick freischalten. Nach der langen Modellberechnung
    // verweigern Chromium & Co. sonst ein neues play() als Autoplay.
    autoplayFreigeben();
    const beschriftung = knopf.textContent;
    knopf.disabled = true;
    knopf.classList.add('laeuft');
    knopf.textContent = '… läuft';
    melde('Zeile ' + knopf.getAttribute('data-ize-neu') + ' wird erzeugt …');
    try {
      const antwort = await server.zeile_neu({ nr: knopf.getAttribute('data-ize-neu') });
      const zeile = knopf.closest('tr');
      if (antwort && antwort.zeile && zeile) {
        zeile.outerHTML = antwort.zeile;
      } else {
        knopf.disabled = false;
        knopf.classList.remove('laeuft');
        knopf.textContent = beschriftung;
      }
      melde((antwort && antwort.meldung) || '');
      if (antwort && antwort.ton) spiele(antwort.ton, 0, null);
    } catch (fehler) {
      knopf.disabled = false;
      knopf.classList.remove('laeuft');
      knopf.textContent = beschriftung;
      melde('Fehler: ' + fehler);
    }
    return;
  }

  const welle = ereignis.target.closest('[data-ize-welle]');
  if (welle) {
    const kasten = welle.getBoundingClientRect();
    const anteil = kasten.width ? (ereignis.clientX - kasten.left) / kasten.width : 0;
    melde('lädt …');
    try {
      const antwort = await server.zeile_ton({
        nr: welle.getAttribute('data-ize-nr'),
        welche: welle.getAttribute('data-ize-welche'),
        anteil: anteil,
      });
      if (!antwort || antwort.fehler) { melde((antwort && antwort.fehler) || 'Fehler'); return; }
      spiele(antwort.uri, antwort.start, welle);
      melde(antwort.meldung || '');
    } catch (fehler) { melde('Fehler: ' + fehler); }
  }
});

// Endlos weiterblättern: beim Scrollen im Rahmen die nächsten Zeilen anhängen.
element.addEventListener('scroll', async (ereignis) => {
  const rahmen = ereignis.target;
  if (!rahmen || !rahmen.dataset || rahmen.dataset.izeRahmen !== '1') return;
  if (rahmen.dataset.laedt === '1') return;
  if (rahmen.scrollTop + rahmen.clientHeight < rahmen.scrollHeight - 140) return;
  const fuss = rahmen.querySelector('[data-ize-mehr]');
  const koerper = rahmen.querySelector('[data-ize-koerper]');
  if (!fuss || !koerper) return;
  rahmen.dataset.laedt = '1';
  try {
    const antwort = await server.zeilen_nachladen({ ab: fuss.getAttribute('data-ize-mehr') });
    if (antwort && antwort.zeilen) koerper.insertAdjacentHTML('beforeend', antwort.zeilen);
    if (antwort && antwort.rest > 0) {
      fuss.setAttribute('data-ize-mehr', antwort.ab);
      fuss.textContent = 'noch ' + antwort.rest + ' Zeilen – einfach weiterscrollen …';
    } else if (antwort) {
      fuss.removeAttribute('data-ize-mehr');
      fuss.textContent = 'alle Zeilen angezeigt';
    }
  } catch (fehler) {
    fuss.textContent = 'Nachladen fehlgeschlagen: ' + fehler;
  }
  rahmen.dataset.laedt = '';
}, true);
"""

ERLAUBNIS_JS = """
(an) => {
  try {
    if (an && "Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  } catch (e) {}
}
"""

AUTOPLAY_VORBEREITEN_JS = """
(...werte) => {
  const autoplay = Boolean(werte[7]);
  if (autoplay) {
    try {
      const ton = window.__izeAutoplayTon || new Audio();
      window.__izeAutoplayTon = ton;
      ton.pause();
      ton.muted = true;
      ton.src = 'data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
      const versuch = ton.play();
      if (versuch && versuch.then) {
        versuch.then(() => {
          ton.pause();
          ton.currentTime = 0;
          ton.muted = false;
        }).catch(() => { ton.muted = false; });
      } else {
        ton.pause();
        ton.muted = false;
      }
    } catch (e) {}
  }
  return werte;
}
"""

AUTOPLAY_SIGNAL_JS = """
(signal) => {
  if (!signal) return [];
  try {
    let uri = String(signal);
    try {
      const daten = JSON.parse(uri);
      uri = String((daten && daten.uri) || "");
    } catch (e) {}
    if (!uri) return [];
    const ton = window.__izeAutoplayTon || new Audio();
    window.__izeAutoplayTon = ton;
    ton.pause();
    ton.muted = false;
    ton.src = String(uri);
    ton.load();
    const starten = () => {
      ton.play().catch(fehler => {
        console.warn("OmniVoice-Autoplay wurde vom Browser blockiert:", fehler);
      });
    };
    if (ton.readyState >= 1) starten();
    else ton.addEventListener("loadedmetadata", starten, { once: true });
  } catch (fehler) {
    console.warn("OmniVoice-Autoplay:", fehler);
  }
  return [];
}
"""

THEME_WECHSEL_JS = """
(name) => {
  const erlaubt = [
    "Crimson", "Darkmore", "Default", "Dracula", "Fallout", "Flashbang",
    "Hyrule", "Nordic", "Pixel", "Retro", "Scene"
  ];
  const theme = erlaubt.includes(String(name)) ? String(name) : "Default";
  const wurzel = document.documentElement;
  const marker = document.querySelector("#ize-theme-marker");
  if (marker) marker.dataset.izeTheme = theme;
  wurzel.dataset.izeTheme = theme;
  if (document.body) document.body.dataset.izeTheme = theme;
  document.querySelectorAll("gradio-app, .gradio-container").forEach(
    element => element.dataset.izeTheme = theme
  );
  wurzel.classList.remove("ize-theme-wechselt");
  void wurzel.offsetWidth;
  wurzel.classList.add("ize-theme-wechselt");
  window.setTimeout(() => wurzel.classList.remove("ize-theme-wechselt"), 450);
  return [];
}
"""

# Gradio waehlt seine Sprache allein anhand von navigator.language. Das hier
# wird in den <head> gehaengt und laeuft damit VOR dem Programmteil von Gradio -
# so ist die Oberflaeche auch dann deutsch, wenn der Browser auf Englisch steht.
SPRACHE_HEAD = """
<script>
  try {
    Object.defineProperty(navigator, "language",
      { get: () => "de-DE", configurable: true });
    Object.defineProperty(navigator, "languages",
      { get: () => ["de-DE", "de"], configurable: true });
    document.documentElement.lang = "de";
  } catch (e) {}
</script>
"""

# Ein paar Texte sind in Gradio fest eingebaut und lassen sich nicht
# uebersetzen ("processing |", "queue: 1/3 |"). Die werden hier im laufenden
# Betrieb ersetzt, sobald sie auftauchen.
UEBERSETZUNG_JS = """
() => {
  const ersetzungen = [
    [/\\bprocessing \\|/g, "wird berechnet |"],
    [/\\bqueue: /g, "Warteschlange: "],
    [/^\\s*Processing\\s*$/g, "Wird berechnet"],
    [/^\\s*Loading\\.\\.\\.\\s*$/g, "Wird geladen …"],
    [/^\\s*Waiting\\s*$/g, "Warten"],
  ];
  const behandeln = (knoten) => {
    if (!knoten) return;
    if (knoten.nodeType === 3) {
      let text = knoten.nodeValue;
      if (!text) return;
      let neu = text;
      for (const [muster, ersatz] of ersetzungen) neu = neu.replace(muster, ersatz);
      if (neu !== text) knoten.nodeValue = neu;
    } else if (knoten.nodeType === 1 && knoten.childNodes) {
      knoten.childNodes.forEach(behandeln);
    }
  };
  try {
    const beobachter = new MutationObserver((eintraege) => {
      for (const eintrag of eintraege) {
        if (eintrag.type === "characterData") behandeln(eintrag.target);
        else eintrag.addedNodes.forEach(behandeln);
      }
    });
    beobachter.observe(document.body,
      { childList: true, subtree: true, characterData: true });
    behandeln(document.body);
  } catch (e) { console.warn("OmniVoice-Übersetzung:", e); }

  // Windows und einige Browser melden OGG-Dateien als application/ogg oder
  // application/octet-stream. Gradios Audio-Upload prüft dagegen hart auf
  // audio/ogg und lehnt dieselbe Datei je nach Rechner schon vor dem Upload ab.
  // Die Endung wird deshalb im Capture-Schritt normalisiert; die Audiodaten
  // selbst werden weder konvertiert noch verändert.
  if (!window.__izeAudioMimeAktiv) {
    window.__izeAudioMimeAktiv = true;
    const audioMimeKorrigieren = (dateien) => {
      if (!dateien || !dateien.length || typeof DataTransfer === "undefined") return null;
      const transfer = new DataTransfer();
      let geaendert = false;
      for (const datei of Array.from(dateien)) {
        const name = String(datei.name || "").toLowerCase();
        const mime = (name.endsWith(".ogg") || name.endsWith(".oga"))
          ? "audio/ogg"
          : (name.endsWith(".opus") ? "audio/opus" : "");
        if (mime && datei.type !== mime) {
          transfer.items.add(new File([datei], datei.name, {
            type: mime,
            lastModified: datei.lastModified,
          }));
          geaendert = true;
        } else {
          transfer.items.add(datei);
        }
      }
      return geaendert ? transfer : null;
    };

    document.addEventListener("change", (ereignis) => {
      try {
        const eingabe = ereignis.target;
        if (!eingabe || eingabe.type !== "file") return;
        const transfer = audioMimeKorrigieren(eingabe.files);
        if (transfer) eingabe.files = transfer.files;
      } catch (fehler) {
        console.warn("OmniVoice OGG-MIME-Korrektur:", fehler);
      }
    }, true);

    document.addEventListener("drop", (ereignis) => {
      try {
        if (ereignis.__izeAudioMimeKorrigiert) return;
        const transfer = audioMimeKorrigieren(
          ereignis.dataTransfer && ereignis.dataTransfer.files
        );
        if (!transfer || !ereignis.target) return;
        ereignis.preventDefault();
        ereignis.stopImmediatePropagation();
        const neu = new DragEvent("drop", {
          bubbles: true,
          cancelable: true,
          composed: true,
          dataTransfer: transfer,
          clientX: ereignis.clientX,
          clientY: ereignis.clientY,
          screenX: ereignis.screenX,
          screenY: ereignis.screenY,
        });
        neu.__izeAudioMimeKorrigiert = true;
        ereignis.target.dispatchEvent(neu);
      } catch (fehler) {
        console.warn("OmniVoice OGG-Drop-Korrektur:", fehler);
      }
    }, true);
  }
}
"""


def start_javascript(theme: str) -> str:
    """Setzt das gespeicherte Theme, bevor Gradio sichtbar wird."""
    theme = normalisiere_theme(theme)
    anfang = (
        "() => {\n"
        f"  const startTheme = {json.dumps(theme)};\n"
        "  const startThemeSetzen = () => {\n"
        "    document.documentElement.dataset.izeTheme = startTheme;\n"
        "    if (document.body) document.body.dataset.izeTheme = startTheme;\n"
        "    const marker = document.querySelector(\"#ize-theme-marker\");\n"
        "    if (marker) marker.dataset.izeTheme = startTheme;\n"
        "    document.querySelectorAll(\"gradio-app, .gradio-container\").forEach(\n"
        "      element => element.dataset.izeTheme = startTheme\n"
        "    );\n"
        "  };\n"
        "  startThemeSetzen();\n"
    )
    return UEBERSETZUNG_JS.replace("() => {\n", anfang, 1)


# ------------------------------------------------------------
# Kleine Helfer
# ------------------------------------------------------------


def komma(wert: float, stellen: int = 1) -> str:
    return f"{wert:.{stellen}f}".replace(".", ",")


def gradio_datei(pfad) -> str | None:
    """
    Liefert eine von Gradio erlaubte Kopie aus dem System-Tempordner.

    Ein frei gewählter Stapel-Ausgabeordner kann außerhalb von allowed_paths
    liegen. Die echte Datei bleibt dort; nur die Download-Komponente bekommt
    diese kleine, temporäre Kopie.
    """
    if not pfad:
        return None
    quelle = Path(pfad)
    if not quelle.is_file():
        return None
    cache = Path(tempfile.gettempdir()) / "omnivoice-gradio"
    cache.mkdir(parents=True, exist_ok=True)
    ziel = cache / f"{quelle.stem}_{time.time_ns()}{quelle.suffix}"
    shutil.copy2(quelle, ziel)
    return str(ziel)


def _ersetzungswert(text: str) -> str:
    text = str(text or "").strip()
    if text in ('""', "''"):
        return ""
    return (text.replace(r"\r", "\r").replace(r"\n", "\n")
            .replace(r"\t", "\t").replace(r"\\", "\\"))


def parse_ersetzungen(regeltext: str) -> list[tuple[str, str]]:
    """Eine Regel je Zeile: Suchtext => Ersatz; \\r/\\n/\\t werden verstanden."""
    regeln = []
    for nummer, zeile in enumerate(str(regeltext or "").splitlines(), start=1):
        if not zeile.strip() or zeile.lstrip().startswith("#"):
            continue
        if "=>" not in zeile:
            raise ValueError(f"Ersetzungsregel {nummer} braucht »=>«.")
        suche, ersatz = zeile.split("=>", 1)
        suche, ersatz = _ersetzungswert(suche), _ersetzungswert(ersatz)
        if not suche:
            raise ValueError(f"Ersetzungsregel {nummer} hat keinen Suchtext.")
        regeln.append((suche, ersatz))
    return regeln


def ersetze_text(text: str, regeltext: str) -> str:
    ergebnis = str(text or "")
    for suche, ersatz in parse_ersetzungen(regeltext):
        ergebnis = ergebnis.replace(suche, ersatz)
    return ergebnis


# ------------------------------------------------------------
# Einstellungen (bleiben ueber Neustarts erhalten)
# ------------------------------------------------------------

STANDARD_EINSTELLUNGEN = {
    "arbeiter": 1,
    "qualitaet": 32,
    "tempo": 1.0,
    "wurzel": "",
    "ausgabe": "",
    "ueberspringen": True,
    "dauer_von_probe": False,
    "monitor": True,
    "ton": True,
    "hinweis": False,
    "blinken": True,
    "bericht": True,
    "autoplay": False,
    "dauer_offset": 0.0,
    "stille_weg": False,
    "laut_modus": "aus",
    "laut_db": 0.0,
    "tab_autoplay": True,
    "pro_seite": 25,
    "whisper_modell": "medium",
    "whisper_geraet": "Automatisch (NVIDIA, sonst CPU)",
    "whisper_rating": False,
    "whisper_minimum": 55,
    "whisper_arbeiter": 1,
    "text_ersetzungen": STANDARD_ERSETZUNGEN,
    "theme": "Default",
}


def lies_einstellungen(pfad: Path) -> dict:
    werte = dict(STANDARD_EINSTELLUNGEN)
    try:
        if pfad.exists():
            gespeichert = json.loads(pfad.read_text(encoding="utf-8"))
            if isinstance(gespeichert, dict):
                werte.update({k: v for k, v in gespeichert.items() if k in werte})
    except Exception as fehler:
        sag(f"Hinweis: Einstellungen konnten nicht gelesen werden ({fehler}).")
    werte["theme"] = normalisiere_theme(werte.get("theme", "Default"))
    return werte


def schreibe_einstellungen(pfad: Path, werte: dict) -> str:
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(werte, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"✅  Gespeichert in `{pfad}`"
    except Exception as fehler:
        return f"❌  Speichern nicht möglich: {fehler}"


def dauer_text(sekunden: float) -> str:
    sekunden = max(0.0, float(sekunden))
    if sekunden < 60:
        return f"{komma(sekunden)} s"
    minuten, rest = divmod(int(sekunden), 60)
    stunden, minuten = divmod(minuten, 60)
    if stunden:
        return f"{stunden}:{minuten:02d}:{rest:02d}"
    return f"{minuten}:{rest:02d}"


def uhrzeit_text(in_sekunden: float) -> str:
    """Voraussichtliche Fertigstellung als Uhrzeit."""
    if in_sekunden <= 0 or in_sekunden > 60 * 60 * 48:
        return "–"
    ziel = time.localtime(time.time() + in_sekunden)
    jetzt = time.localtime()
    text = time.strftime("%H:%M", ziel)
    if ziel.tm_yday != jetzt.tm_yday:
        text = "morgen " + text
    return text + " Uhr"


# ------------------------------------------------------------
# CSV-Verarbeitung fuer den Stapelbetrieb
# ------------------------------------------------------------

def lies_csv(pfad: str) -> list[list[str]]:
    """Liest die Liste ein: Trennzeichen, Kodierung und Kopfzeile werden erkannt."""
    rohtext = None
    for kodierung in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            rohtext = Path(pfad).read_text(encoding=kodierung)
            break
        except UnicodeDecodeError:
            continue
        except OSError as fehler:
            raise RuntimeError(f"Die Liste ließ sich nicht öffnen: {fehler}")
    if rohtext is None:
        raise RuntimeError("Die Textkodierung der Liste wurde nicht erkannt.")

    probe = rohtext[:8192]
    try:
        trenner = csv.Sniffer().sniff(probe, delimiters=";,\t|").delimiter
    except csv.Error:
        trenner = max(";,\t|", key=probe.count)

    zeilen = []
    for felder in csv.reader(io.StringIO(rohtext), delimiter=trenner):
        felder = [f.strip().strip('"').strip() for f in felder]
        if any(felder):
            zeilen.append(felder)

    if zeilen and not sieht_nach_datei_aus(zeilen[0][0]):
        zeilen = zeilen[1:]          # Kopfzeile überspringen
    return zeilen


def sieht_nach_datei_aus(text: str) -> bool:
    if not text:
        return False
    if Path(text).suffix.lower() in AUDIO_ENDUNGEN:
        return True
    return ("\\" in text or "/" in text) and Path(text).suffix != ""


def loese_quelle(eintrag: str, wurzel: str) -> Path:
    pfad = Path(eintrag.strip().strip('"'))
    if not pfad.is_absolute() and wurzel.strip():
        pfad = Path(wurzel.strip()) / pfad
    return pfad


def erkenne_wurzel(quellen: list[Path]) -> Path:
    """Ohne Angabe: den gemeinsamen Ordner aller Dateien als Projektstart nehmen."""
    vorhanden = [str(p.resolve()) for p in quellen if p.exists()]
    if not vorhanden:
        vorhanden = [str(p) for p in quellen]
    if not vorhanden:
        return Path.cwd()
    try:
        return Path(os.path.commonpath(vorhanden))
    except ValueError:
        return Path(vorhanden[0]).parent


def zielpfad(quelle: Path, wurzel: Path, basis: Path) -> Path:
    """Spiegelt den Pfad unterhalb der Wurzel in den Ausgabeordner."""
    try:
        rel = quelle.resolve().relative_to(wurzel.resolve())
    except (ValueError, OSError):
        rel = Path(quelle.name)
    return (basis / rel).with_suffix(".wav")


# ------------------------------------------------------------
# Fancy Stapel-Anzeige
# ------------------------------------------------------------

def batch_html(zustand: str, datei: str, erledigt: int, gesamt: int, fehler: int,
               vergangen: float, rest: float, pro_datei: float, tonlaenge: float,
               arbeiter: str = "") -> str:
    anteil = (erledigt / gesamt * 100.0) if gesamt else 0.0
    titel = {"laeuft": "STAPEL LÄUFT", "fertig": "STAPEL FERTIG", "start": "STAPEL STARTET",
             "abbruch": "STAPEL ANGEHALTEN", "fehler": "STAPEL ABGEBROCHEN"}.get(zustand, "STAPEL")
    klasse = {"fertig": " fertig", "fehler": " fehler", "abbruch": " fehler"}.get(zustand, "")
    laeuft = zustand in ("laeuft", "start")
    pro_minute = (erledigt / vergangen * 60.0) if vergangen > 0 and erledigt else 0.0
    faktor = (tonlaenge / vergangen) if vergangen > 0 and tonlaenge else 0.0

    felder = [
        (f"{erledigt} <span style='opacity:.45'>/ {gesamt}</span>", "Dateien erledigt", ""),
        (f"{komma(anteil)} %", "geschafft", ""),
        (dauer_text(vergangen), "vergangen", ""),
        (dauer_text(rest) if laeuft and rest else "–", "Restzeit", ""),
        (uhrzeit_text(rest) if laeuft else "–", "fertig gegen", ""),
        (f"{komma(pro_datei)} s", "pro Datei", ""),
        (f"{komma(pro_minute)}", "Dateien/Minute", ""),
        (f"{komma(faktor)}×", "schneller als Echtzeit", ""),
        (str(fehler), "Fehler", "schlecht" if fehler else ""),
    ]
    if arbeiter:
        felder.insert(5, (arbeiter, "Arbeiter aktiv", ""))
    kacheln = "".join(
        f"<div class='{klasse_kachel}'><b>{wert}</b><span>{beschriftung}</span></div>"
        for wert, beschriftung, klasse_kachel in felder
    )
    # Der Balken traegt sich komplett selbst: Hoehe, Rundung, Farbe und Glow
    # stehen direkt am Element. Damit haengt die Anzeige weder an den
    # CSS-Variablen noch daran, ob Gradio das eingebettete Stylesheet an
    # dieser Stelle ueberhaupt anwendet. Die Klasse steuert nur noch die
    # Animation - fehlt sie, bleibt der Balken trotzdem farbig.
    if zustand == "fertig":
        fuell_klasse = " fertig"
        farbe = "linear-gradient(90deg,#2f7dff,#4d9bff,#8ecbff)"
        glut = "0 0 22px rgba(77,155,255,.85),0 0 48px rgba(77,155,255,.40)"
    elif zustand in ("fehler", "abbruch"):
        fuell_klasse = ""
        farbe = "linear-gradient(90deg,#c2455f,#ff6b6b,#ffa07a)"
        glut = "0 0 18px rgba(255,107,107,.60)"
    else:
        fuell_klasse = ""
        farbe = "linear-gradient(90deg,#ff4fd8,#4d9bff,#22e0ff) 0 0 / 250% 100%"
        glut = "0 0 20px rgba(77,155,255,.65)"
    fuell_stil = (f"width:{max(0.8, anteil):.2f}%;height:100%;border-radius:8px;"
                  f"background:{farbe};box-shadow:{glut};")
    return f"""
<div class="ize-batch">
  <div class="ize-batch-kopf">
    <span class="ize-batch-titel{klasse}">{titel}</span>
    <span class="ize-batch-datei">{html.escape(datei or "–")}</span>
  </div>
  <div class="ize-bar" style="height:16px;border-radius:8px;overflow:hidden;
       background:rgba(255,255,255,.07);margin:12px 0 4px 0">
    <div class="ize-bar-fuell{fuell_klasse}" style="{fuell_stil}"></div>
  </div>
  <div class="ize-grid">{kacheln}</div>
</div>
"""


def listen_html(zustand: str, datei: str, erledigt: int, gesamt: int, fehler: int,
                vergangen: float, rest: float, pro_datei: float) -> str:
    """Dieselbe Fortschrittskarte, im Listengenerator aber passend beschriftet."""
    return batch_html(
        zustand, datei, erledigt, gesamt, fehler, vergangen, rest, pro_datei, 0
    ).replace("STAPEL", "LISTE", 1)


LEERE_ANZEIGE = batch_html("bereit", "noch nichts gestartet", 0, 0, 0, 0, 0, 0, 0)
LEERE_LISTEN_ANZEIGE = listen_html("bereit", "noch nichts gestartet", 0, 0, 0, 0, 0, 0)


# ------------------------------------------------------------
# Stapelbetrieb (ohne Gradio testbar)
# ------------------------------------------------------------

# Solange ein Stapel laeuft, sind Pruefung und ein zweiter Start gesperrt.
# Der Zustand haengt am Server, gilt also auch fuer weitere Browserfenster.
STAPEL_LAEUFT = threading.Event()


def pruefe_liste(csv_datei, wurzel, ziel_basis, standard_basis: Path) -> str:
    """Liest die Liste probeweise und meldet, was daraus wuerde."""
    if STAPEL_LAEUFT.is_set():
        return ("⏳  Es läuft gerade ein Stapel. Die Prüfung ist so lange gesperrt – "
                "bitte abwarten oder oben auf »Anhalten« drücken.")
    if not csv_datei:
        return "⚠️  Bitte zuerst eine CSV-Liste auswählen."
    pfad = csv_datei if isinstance(csv_datei, str) else getattr(csv_datei, "name", "")
    try:
        zeilen = lies_csv(pfad)
    except Exception as fehler:
        return f"❌  {fehler}"
    if not zeilen:
        return "⚠️  In der Liste steht keine einzige Zeile."

    quellen = [loese_quelle(z[0], wurzel) for z in zeilen if z and z[0]]
    fehlen = [p for p in quellen if not p.exists()]
    genutzte_wurzel = Path(wurzel.strip()) if wurzel.strip() else erkenne_wurzel(quellen)
    basis = Path(ziel_basis.strip()) if ziel_basis.strip() else standard_basis
    spalten = max(len(z) for z in zeilen)

    bericht = [
        f"**{len(zeilen)} Zeilen** gefunden, {spalten} Spalten erkannt.",
        f"**{len(quellen) - len(fehlen)}** Audiodateien vorhanden, **{len(fehlen)}** fehlen.",
        f"Projektstart: `{genutzte_wurzel}`"
        + ("  *(automatisch erkannt)*" if not wurzel.strip() else ""),
    ]
    if spalten < 3:
        bericht.append("ℹ️  Nur zwei Spalten – der englische Text fehlt. "
                       "OmniVoice hört die Sprachprobe dann selbst ab.")
    if quellen:
        bericht.append(f"Beispiel-Ziel: `{zielpfad(quellen[0], genutzte_wurzel, basis)}`")
    for fehlende in fehlen[:5]:
        bericht.append(f"❌ fehlt: `{fehlende}`")
    if len(fehlen) > 5:
        bericht.append(f"… und {len(fehlen) - 5} weitere.")
    if not fehlen:
        bericht.append("✅  Alles bereit – der Stapel kann losgehen.")
    return "\n\n".join(bericht)


def stapel_durchlauf(csv_datei, wurzel, ziel_basis, ueberspringen,
                     schritte, tempo, standard_basis: Path, arbeiterzahl: int = 1,
                     dauer_von_probe: bool = False, bericht_schreiben: bool = True,
                     klang: dict = None, whisper_pruefen: bool = False,
                     whisper_modell: str = "medium", whisper_geraet: str = "auto",
                     bewertungen=None):
    """
    Klammer um den eigentlichen Durchlauf: setzt die Sperre und nimmt sie am
    Ende in jedem Fall wieder weg - auch beim Anhalten mitten im Lauf.
    """
    if STAPEL_LAEUFT.is_set():
        yield (batch_html("fehler", "es läuft bereits ein Stapel", 0, 0, 0, 0, 0, 0, 0),
               "Es läuft bereits ein Stapel. Bitte diesen erst beenden.", None)
        return
    STAPEL_LAEUFT.set()
    try:
        yield from stapel_arbeiten(csv_datei, wurzel, ziel_basis, ueberspringen, schritte,
                                   tempo, standard_basis, arbeiterzahl, dauer_von_probe,
                                   bericht_schreiben, klang, whisper_pruefen,
                                   whisper_modell, whisper_geraet, bewertungen)
    finally:
        STAPEL_LAEUFT.clear()


def stapel_arbeiten(csv_datei, wurzel, ziel_basis, ueberspringen,
                    schritte, tempo, standard_basis: Path, arbeiterzahl: int = 1,
                    dauer_von_probe: bool = False, bericht_schreiben: bool = True,
                    klang: dict = None, whisper_pruefen: bool = False,
                    whisper_modell: str = "medium", whisper_geraet: str = "auto",
                    bewertungen=None):
    """
    Arbeitet die Liste ab und liefert laufend (Anzeige, Protokoll, Bericht).

    Die eigentliche Erzeugung uebernimmt ein »Betrieb«: entweder der
    Hauptprozess (1 Arbeiter) oder mehrere eigene Prozesse. Nach jeder
    fertigen Datei - und mindestens zweimal pro Sekunde - wird der Zustand
    gemeldet, damit Fortschritt und Restzeit live mitlaufen.
    """
    protokoll: list[str] = []
    beginn = time.time()
    tonlaenge = 0.0
    regeltext = str((klang or {}).get("text_ersetzungen", "") or "")

    def hole_meldungen(betrieb) -> None:
        while True:
            try:
                protokoll.append(betrieb.meldungen.get_nowait())
            except Exception:
                return

    def anzeige(zustand, datei, erledigt, gesamt, fehler, betrieb=None):
        vergangen = time.time() - beginn
        pro_datei = (vergangen / erledigt) if erledigt else 0.0
        rest = pro_datei * (gesamt - erledigt) if erledigt else 0.0
        arbeiter_text = ""
        if betrieb is not None:
            if getattr(betrieb, "art", "") == "pool":
                arbeiter_text = f"{betrieb.beschaeftigt()} <span style='opacity:.45'>/ " \
                                f"{betrieb.anzahl}</span>"
            else:
                arbeiter_text = "1 <span style='opacity:.45'>/ 1</span>"
        return (batch_html(zustand, datei, erledigt, gesamt, fehler, vergangen, rest,
                           pro_datei, tonlaenge, arbeiter_text),
                "\n".join(protokoll[-400:]))

    def abbruchanzeige(text, fehlerzahl=1):
        return batch_html("fehler", text, 0, 0, fehlerzahl, 0, 0, 0, 0), "\n".join(protokoll), None

    if not csv_datei:
        protokoll.append("Keine CSV-Liste ausgewählt.")
        yield abbruchanzeige("keine Liste")
        return
    try:
        ersetzungsregeln = parse_ersetzungen(regeltext)
    except ValueError as fehler:
        protokoll.append(f"Globale Textersetzungen sind ungültig: {fehler}")
        yield abbruchanzeige("Textersetzungen ungültig")
        return

    pfad = csv_datei if isinstance(csv_datei, str) else getattr(csv_datei, "name", "")
    try:
        zeilen = lies_csv(pfad)
    except Exception as fehler:
        protokoll.append(f"FEHLER: {fehler}")
        yield abbruchanzeige("Liste unlesbar")
        return
    if not zeilen:
        protokoll.append("In der Liste steht keine einzige Zeile.")
        yield abbruchanzeige("Liste leer")
        return

    quellen = [loese_quelle(z[0], wurzel) for z in zeilen if z and z[0]]
    genutzte_wurzel = Path(wurzel.strip()) if wurzel.strip() else erkenne_wurzel(quellen)
    basis = Path(ziel_basis.strip()) if ziel_basis.strip() else standard_basis
    gesamt = len(zeilen)
    arbeiterzahl = max(1, int(arbeiterzahl))

    protokoll.append(f"Liste       : {pfad}")
    protokoll.append(f"Zeilen      : {gesamt}")
    protokoll.append(f"Projektstart: {genutzte_wurzel}")
    protokoll.append(f"Ausgabe     : {basis}")
    protokoll.append(f"Arbeiter    : {arbeiterzahl}"
                     + ("" if arbeiterzahl > 1 else " (im Hauptprozess)"))
    if dauer_von_probe:
        versatz = float((klang or {}).get("dauer_offset", 0.0))
        protokoll.append("Länge       : je Zeile so lang wie die englische Aufnahme"
                         + (f" ({versatz:+.1f} s Versatz)".replace(".", ",") if versatz else ""))
    if (klang or {}).get("stille_weg"):
        protokoll.append("Klang       : Stille am Anfang wird entfernt")
    if (klang or {}).get("lautstaerke_modus", "aus") != "aus":
        protokoll.append(f"Lautstärke  : {(klang or {}).get('lautstaerke_modus')}")
    if ersetzungsregeln:
        protokoll.append(f"Textersetzung: {len(ersetzungsregeln)} globale Regel(n)")
    protokoll.append("")
    yield anzeige("start", "Liste wird geprüft …", 0, gesamt, 0) + (None,)

    # ---------------- Vorlauf: prüfen, was überhaupt zu tun ist
    auftraege: list[dict] = []
    eintraege: dict[int, tuple] = {}
    rating_ziele: dict[int, tuple[Path, str]] = {}
    erledigt = anzahl_fehler = rating_fehler = 0

    for nummer, felder in enumerate(zeilen, start=1):
        quelle = loese_quelle(felder[0], wurzel)
        if len(felder) == 2:
            englisch, deutsch = "", felder[1].strip()
        else:
            englisch = felder[1].strip() if len(felder) > 1 else ""
            deutsch = felder[2].strip() if len(felder) > 2 else ""
        modell_englisch = ersetze_text(englisch, regeltext)
        modell_deutsch = ersetze_text(deutsch, regeltext)
        ziel = zielpfad(quelle, genutzte_wurzel, basis)

        if not modell_deutsch:
            anzahl_fehler += 1
            erledigt += 1
            protokoll.append(f"[{nummer}/{gesamt}] übersprungen (kein deutscher Text): {quelle.name}")
            eintraege[nummer] = (
                str(quelle), str(ziel), "fehler", "kein deutscher Text", "0", "", ""
            )
        elif not quelle.exists():
            anzahl_fehler += 1
            erledigt += 1
            protokoll.append(f"[{nummer}/{gesamt}] fehlt: {quelle}")
            eintraege[nummer] = (
                str(quelle), str(ziel), "fehler", "Audiodatei fehlt", "0", "", ""
            )
        elif ueberspringen and ziel.exists():
            erledigt += 1
            protokoll.append(f"[{nummer}/{gesamt}] schon vorhanden: {ziel.name}")
            eintraege[nummer] = (
                str(quelle), str(ziel), "übersprungen", "bereits vorhanden", "0", "", ""
            )
            if whisper_pruefen:
                rating_ziele[nummer] = (ziel, deutsch)
        else:
            auftrag = {"id": nummer, "text": modell_deutsch, "ref_audio": str(quelle),
                       "ref_text": modell_englisch, "num_step": int(schritte),
                       "speed": float(tempo), "ziel": str(ziel),
                       "dauer_von_probe": bool(dauer_von_probe),
                       "name": quelle.name, "rating_text": deutsch}
            auftrag.update(klang or {})
            auftraege.append(auftrag)

    protokoll.append("")
    protokoll.append(f"Zu erzeugen: {len(auftraege)} von {gesamt} Zeilen.")
    yield anzeige("start", f"{len(auftraege)} Dateien vorgemerkt", erledigt, gesamt,
                  anzahl_fehler) + (None,)

    offen: dict[int, dict] = {}
    betrieb = None
    try:
        if auftraege:
            # ---------------- Arbeiter bereitstellen
            betrieb = VERWALTUNG.betrieb(arbeiterzahl)
            hole_meldungen(betrieb)
            wartete = time.time()
            while betrieb.bereit_anzahl() == 0 and betrieb.lebende() > 0:
                hole_meldungen(betrieb)
                yield anzeige("start",
                              f"Arbeiter werden vorbereitet – {betrieb.bereit_anzahl()} von "
                              f"{betrieb.anzahl} bereit ({dauer_text(time.time() - wartete)})",
                              erledigt, gesamt, anzahl_fehler, betrieb) + (None,)
                time.sleep(0.5)
            if betrieb.lebende() == 0:
                protokoll.append("FEHLER: Es konnte kein Arbeiter gestartet werden.")
                yield abbruchanzeige("kein Arbeiter verfügbar")
                return
            hole_meldungen(betrieb)

            # ---------------- Verteilen und einsammeln
            naechster = 0
            while naechster < len(auftraege) or offen:
                while naechster < len(auftraege):
                    platz = betrieb.freier()
                    if platz is None:
                        break
                    auftrag = auftraege[naechster]
                    betrieb.sende(platz, auftrag)
                    offen[auftrag["id"]] = auftrag
                    naechster += 1

                if not offen and betrieb.lebende() == 0:
                    protokoll.append("FEHLER: Alle Arbeiter sind ausgefallen.")
                    break

                ergebnis = betrieb.antwort(timeout=0.4)
                hole_meldungen(betrieb)
                if ergebnis is None:
                    yield anzeige("laeuft", f"{len(offen)} Datei(en) in Arbeit",
                                  erledigt, gesamt, anzahl_fehler, betrieb) + (None,)
                    continue

                auftrag = offen.pop(ergebnis.get("id"), None)
                if auftrag is None:
                    continue
                nummer = auftrag["id"]
                erledigt += 1
                if ergebnis.get("ok"):
                    tonlaenge += float(ergebnis.get("ton", 0.0))
                    korrektur = float(ergebnis.get("korrektur", 0.0))
                    hinweis = ""
                    if abs(korrektur) > 0.02:
                        hinweis = (f", um {dauer_text(abs(korrektur))} "
                                   + ("gekürzt" if korrektur > 0 else "verlängert"))
                    protokoll.append(
                        f"[{nummer}/{gesamt}] ✔ {Path(auftrag['ziel']).name}  "
                        f"({dauer_text(ergebnis.get('sekunden', 0))}, "
                        f"{dauer_text(ergebnis.get('ton', 0))} Ton{hinweis})")
                    eintraege[nummer] = (auftrag["ref_audio"], auftrag["ziel"], "ok",
                                         hinweis.strip(", "),
                                         komma(float(ergebnis.get("sekunden", 0.0))), "", "")
                    if whisper_pruefen:
                        rating_ziele[nummer] = (
                            Path(auftrag["ziel"]), auftrag.get("rating_text", auftrag["text"])
                        )
                else:
                    anzahl_fehler += 1
                    protokoll.append(f"[{nummer}/{gesamt}] ✖ {auftrag['name']}: "
                                     f"{ergebnis.get('fehler', 'unbekannter Fehler')}")
                    eintraege[nummer] = (auftrag["ref_audio"], auftrag["ziel"], "fehler",
                                         str(ergebnis.get("fehler", "")), "0", "", "")
                yield anzeige("laeuft", auftrag["name"], erledigt, gesamt,
                              anzahl_fehler, betrieb) + (None,)
    finally:
        # Beim Anhalten laufende Auftraege noch einsammeln, damit die Arbeiter
        # danach wieder frei sind und nicht in der Luft haengen.
        if betrieb is not None and offen:
            def nachlesen(rest_offen):
                ende = time.time() + 300
                while rest_offen and time.time() < ende:
                    antwort = betrieb.antwort(timeout=1.0)
                    if antwort is not None:
                        rest_offen.pop(antwort.get("id"), None)

            threading.Thread(target=nachlesen, args=(dict(offen),), daemon=True).start()

    # ---------------- Optionaler Qualitätscheck mit Faster-Whisper
    if whisper_pruefen and rating_ziele:
        whisper_dienst.POOL.reduzieren()
        protokoll.append("")
        protokoll.append(
            f"Whisper-Prüfung: {len(rating_ziele)} Datei(en), Modell {whisper_modell}."
        )
        rating_beginn = time.time()
        for index, nummer in enumerate(sorted(rating_ziele), start=1):
            ziel, erwartet = rating_ziele[nummer]
            try:
                gespeichert = bewertungen.hole(ziel, erwartet) if bewertungen is not None else {}
                if gespeichert:
                    transkript = str(gespeichert.get("transkript", "") or "").strip()
                    rating = float(gespeichert.get("rating", 0.0))
                    quelle_rating = " · gespeichert"
                else:
                    with ThreadPoolExecutor(max_workers=1) as rating_executor:
                        future = rating_executor.submit(
                            whisper_dienst.DIENST.transkribiere, ziel, "de",
                            whisper_modell, whisper_geraet
                        )
                        while not future.done():
                            vergangen_rating = time.time() - rating_beginn
                            fertig_bisher = index - 1
                            pro_rating = (
                                vergangen_rating / fertig_bisher if fertig_bisher else 0.0
                            )
                            rest_rating = (
                                pro_rating * (len(rating_ziele) - fertig_bisher)
                                if fertig_bisher else 0.0
                            )
                            yield (
                                batch_html(
                                    "laeuft", f"Whisper prüft {ziel.name}",
                                    fertig_bisher, len(rating_ziele), rating_fehler,
                                    vergangen_rating, rest_rating, pro_rating, tonlaenge
                                ),
                                "\n".join(protokoll[-400:]),
                                None,
                            )
                            time.sleep(0.5)
                        antwort = future.result()
                    transkript = str(antwort.get("text", "") or "").strip()
                    rating = whisper_dienst.aehnlichkeit(erwartet, transkript)
                    quelle_rating = ""
                if bewertungen is not None and not gespeichert:
                    bewertungen.setze(
                        ziel, erwartet, rating, transkript, whisper_modell,
                        str(antwort.get("geraet", whisper_geraet)),
                    )
                bisher = list(eintraege.get(nummer, ("", "", "", "", "0", "", "")))
                bisher[5], bisher[6] = f"{rating:.1f}", transkript
                eintraege[nummer] = tuple(bisher)
                protokoll.append(
                    f"[Prüfung {index}/{len(rating_ziele)}] {ziel.name}: "
                    f"{rating:.1f} %{quelle_rating}"
                )
            except Exception as fehler:
                rating_fehler += 1
                protokoll.append(
                    f"[Prüfung {index}/{len(rating_ziele)}] {ziel.name}: FEHLER: {fehler}"
                )
            vergangen_rating = time.time() - rating_beginn
            pro_rating = vergangen_rating / index
            rest_rating = pro_rating * (len(rating_ziele) - index)
            yield (
                batch_html(
                    "laeuft", f"Whisper prüft {ziel.name}", index, len(rating_ziele),
                    rating_fehler, vergangen_rating, rest_rating, pro_rating, tonlaenge
                ),
                "\n".join(protokoll[-400:]),
                None,
            )

    # ---------------- Bericht schreiben
    bericht_datei = None
    if bericht_schreiben:
        try:
            basis.mkdir(parents=True, exist_ok=True)
            bericht_datei = basis / time.strftime("_bericht_%Y-%m-%d_%H-%M-%S.csv")
            with open(bericht_datei, "w", encoding="utf-8-sig", newline="") as datei:
                schreiber = csv.writer(datei, delimiter=";")
                schreiber.writerow((
                    "zeile", "quelle", "ziel", "status", "meldung", "sekunden",
                    "rating_prozent", "whisper_erkannt",
                ))
                for nummer in sorted(eintraege):
                    schreiber.writerow((nummer,) + eintraege[nummer])
            protokoll.append("")
            protokoll.append(f"Bericht geschrieben: {bericht_datei}")
        except Exception as fehler:
            bericht_datei = None
            protokoll.append(f"Bericht konnte nicht geschrieben werden: {fehler}")

    vergangen = time.time() - beginn
    gelungen = erledigt - anzahl_fehler
    protokoll.append("")
    protokoll.append(f"FERTIG: {gelungen} von {gesamt} Dateien in {dauer_text(vergangen)}, "
                     f"{anzahl_fehler} Fehler.")
    if whisper_pruefen:
        protokoll.append(
            f"Whisper-Prüfung: {len(rating_ziele) - rating_fehler} bewertet, "
            f"{rating_fehler} Prüf-Fehler."
        )
    if betrieb is not None and getattr(betrieb, "art", "") == "pool":
        protokoll.append(f"Die {betrieb.anzahl} Arbeiter bleiben für den nächsten Stapel bereit "
                         f"(Einstellungen → »Arbeiter stoppen« gibt den Grafikspeicher frei).")
    yield (batch_html("fehler" if anzahl_fehler and not gelungen else "fertig",
                      f"{gelungen} von {gesamt} Dateien erzeugt", erledigt, gesamt,
                      anzahl_fehler, vergangen, 0,
                      vergangen / erledigt if erledigt else 0.0, tonlaenge),
           "\n".join(protokoll[-400:]),
           gradio_datei(bericht_datei))


# ------------------------------------------------------------
# Oberflaeche
# ------------------------------------------------------------

def gradio_hauptversion() -> int:
    """Gradio 6 erwartet css und theme bei launch(), aeltere Fassungen bei Blocks()."""
    try:
        import gradio as gr

        return int(str(gr.__version__).split(".")[0])
    except Exception:
        return 0


def themen_css(name: str) -> str:
    # Alle Paletten werden immer ausgeliefert. Das Attribut am <html>-Element
    # entscheidet, welche davon aktiv ist; dadurch kann die Auswahl ohne
    # Serverneustart wechseln.
    _ = normalisiere_theme(name)
    return """
html:has(#ize-theme-marker[data-ize-theme="Default"]),
body:has(#ize-theme-marker[data-ize-theme="Default"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Default"]) {
    color-scheme:dark;
    --ize-magenta:#ff4fd8; --ize-cyan:#22e0ff; --ize-blau:#4d9bff;
    --ize-kopftext:#eaf2ff; --ize-text:#eaf2ff; --ize-muted:#9ba8bd;
    --ize-auf-akzent:#07101b;
    --ize-seitenhintergrund:
        linear-gradient(rgba(34,224,255,.025) 1px,transparent 1px),
        linear-gradient(90deg,rgba(255,79,216,.02) 1px,transparent 1px),
        radial-gradient(760px 480px at 88% -12%,rgba(255,79,216,.15),transparent 62%),
        radial-gradient(1400px 700px at 12% -10%,#1d2136 0%,#0b0d15 60%);
    --ize-flaeche:rgba(20,24,38,.72); --ize-flaeche-stark:#121524;
    --ize-eingabe:rgba(7,9,16,.76); --ize-rand:rgba(255,255,255,.10);
    --ize-schatten:rgba(0,0,0,.48);
}
html:has(#ize-theme-marker[data-ize-theme="Flashbang"]),
body:has(#ize-theme-marker[data-ize-theme="Flashbang"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Flashbang"]) {
    color-scheme:light;
    --ize-magenta:#c026d3; --ize-cyan:#0284c7; --ize-blau:#2563eb;
    --ize-kopftext:#172033; --ize-text:#172033; --ize-muted:#5d6b82;
    --ize-auf-akzent:#ffffff;
    --ize-seitenhintergrund:
        radial-gradient(circle at 12% 8%,rgba(37,99,235,.11) 0 2px,transparent 3px),
        radial-gradient(circle at 88% 18%,rgba(192,38,211,.08) 0 2px,transparent 3px),
        linear-gradient(145deg,#ffffff 0%,#e7edf7 58%,#dce7f5 100%);
    --ize-flaeche:rgba(255,255,255,.86); --ize-flaeche-stark:#f7faff;
    --ize-eingabe:#ffffff; --ize-rand:rgba(37,58,92,.18);
    --ize-schatten:rgba(37,55,85,.22);
}
html:has(#ize-theme-marker[data-ize-theme="Darkmore"]),
body:has(#ize-theme-marker[data-ize-theme="Darkmore"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Darkmore"]) {
    color-scheme:dark;
    --ize-magenta:#d946ef; --ize-cyan:#38bdf8; --ize-blau:#3b82f6;
    --ize-kopftext:#f8fafc; --ize-text:#edf4ff; --ize-muted:#7e8ba1;
    --ize-auf-akzent:#02050a;
    --ize-seitenhintergrund:
        linear-gradient(115deg,transparent 0 48%,rgba(56,189,248,.035) 49% 50%,transparent 51%),
        radial-gradient(800px 500px at 92% -15%,rgba(217,70,239,.11),transparent 66%),
        radial-gradient(1200px 680px at 15% -20%,#111827 0%,#020306 58%);
    --ize-flaeche:rgba(3,5,9,.90); --ize-flaeche-stark:#05070b;
    --ize-eingabe:#020407; --ize-rand:rgba(148,163,184,.14);
    --ize-schatten:rgba(0,0,0,.82);
}
html:has(#ize-theme-marker[data-ize-theme="Dracula"]),
body:has(#ize-theme-marker[data-ize-theme="Dracula"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Dracula"]) {
    color-scheme:dark;
    --ize-magenta:#ff79c6; --ize-cyan:#8be9fd; --ize-blau:#bd93f9;
    --ize-kopftext:#f8f8f2; --ize-text:#f8f8f2; --ize-muted:#bdc2d6;
    --ize-auf-akzent:#282a36;
    --ize-seitenhintergrund:
        radial-gradient(circle at 82% 12%,rgba(255,121,198,.10) 0 1px,transparent 2px),
        linear-gradient(135deg,transparent 0 47%,rgba(189,147,249,.045) 48% 49%,transparent 50%),
        radial-gradient(1200px 700px at 15% -15%,#44475a 0%,#282a36 58%);
    --ize-flaeche:rgba(68,71,90,.78); --ize-flaeche-stark:#282a36;
    --ize-eingabe:#21222c; --ize-rand:rgba(189,147,249,.28);
    --ize-schatten:rgba(18,18,24,.66);
}
html:has(#ize-theme-marker[data-ize-theme="Fallout"]),
body:has(#ize-theme-marker[data-ize-theme="Fallout"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Fallout"]) {
    color-scheme:dark;
    --ize-magenta:#d6ff3f; --ize-cyan:#79ff63; --ize-blau:#a7ff57;
    --ize-kopftext:#b7ff72; --ize-text:#d5ffb3; --ize-muted:#91b977;
    --ize-auf-akzent:#071006;
    --ize-seitenhintergrund:
        repeating-linear-gradient(0deg,rgba(121,255,99,.027) 0 1px,transparent 1px 4px),
        radial-gradient(circle at 78% 4%,rgba(214,255,63,.12) 0 2px,transparent 3px),
        radial-gradient(1200px 700px at 15% -15%,#1c2912 0%,#070b05 62%);
    --ize-flaeche:rgba(12,24,8,.86); --ize-flaeche-stark:#091006;
    --ize-eingabe:#050a03; --ize-rand:rgba(121,255,99,.26);
    --ize-schatten:rgba(0,0,0,.76);
}
html:has(#ize-theme-marker[data-ize-theme="Hyrule"]),
body:has(#ize-theme-marker[data-ize-theme="Hyrule"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Hyrule"]) {
    color-scheme:dark;
    --ize-magenta:#e4b85a; --ize-cyan:#75d9ae; --ize-blau:#2f966d;
    --ize-kopftext:#ffe9a6; --ize-text:#edf6df; --ize-muted:#a7ba9a;
    --ize-auf-akzent:#07170f;
    --ize-seitenhintergrund:
        linear-gradient(60deg,transparent 0 47%,rgba(228,184,90,.035) 48% 50%,transparent 51%),
        radial-gradient(900px 540px at 78% -15%,rgba(228,184,90,.18),transparent 62%),
        radial-gradient(1100px 720px at 8% -10%,#205a3f 0%,#07160f 64%);
    --ize-flaeche:rgba(17,52,35,.82); --ize-flaeche-stark:#0a2116;
    --ize-eingabe:#07190f; --ize-rand:rgba(228,184,90,.27);
    --ize-schatten:rgba(0,0,0,.72);
}
html:has(#ize-theme-marker[data-ize-theme="Crimson"]),
body:has(#ize-theme-marker[data-ize-theme="Crimson"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Crimson"]) {
    color-scheme:dark;
    --ize-magenta:#ff615f; --ize-cyan:#e8b86c; --ize-blau:#a82d3e;
    --ize-kopftext:#ffd5ad; --ize-text:#fae7db; --ize-muted:#c59b91;
    --ize-auf-akzent:#210b0e;
    --ize-seitenhintergrund:
        repeating-linear-gradient(115deg,rgba(232,184,108,.022) 0 1px,transparent 1px 13px),
        radial-gradient(980px 600px at 84% -18%,rgba(232,184,108,.17),transparent 58%),
        radial-gradient(1250px 760px at 12% -12%,#4a151a 0%,#120708 65%);
    --ize-flaeche:rgba(61,18,23,.80); --ize-flaeche-stark:#210b0e;
    --ize-eingabe:#160709; --ize-rand:rgba(232,184,108,.25);
    --ize-schatten:rgba(4,0,0,.78);
}
html:has(#ize-theme-marker[data-ize-theme="Nordic"]),
body:has(#ize-theme-marker[data-ize-theme="Nordic"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Nordic"]) {
    color-scheme:dark;
    --ize-magenta:#c7d5e7; --ize-cyan:#8eeaff; --ize-blau:#648fb7;
    --ize-kopftext:#f4fbff; --ize-text:#e7f1f7; --ize-muted:#9cabb8;
    --ize-auf-akzent:#08141d;
    --ize-seitenhintergrund:
        linear-gradient(128deg,transparent 0 46%,rgba(199,213,231,.045) 47% 49%,transparent 50%),
        radial-gradient(1000px 620px at 80% -18%,rgba(142,234,255,.15),transparent 60%),
        radial-gradient(1300px 760px at 10% -12%,#314454 0%,#0b1218 64%);
    --ize-flaeche:rgba(34,49,61,.80); --ize-flaeche-stark:#121c24;
    --ize-eingabe:#0c151c; --ize-rand:rgba(174,213,234,.23);
    --ize-schatten:rgba(0,4,8,.74);
}
html:has(#ize-theme-marker[data-ize-theme="Retro"]),
body:has(#ize-theme-marker[data-ize-theme="Retro"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Retro"]) {
    color-scheme:dark;
    --ize-magenta:#ff4fd8; --ize-cyan:#29f4ff; --ize-blau:#7857ff;
    --ize-kopftext:#fff2ff; --ize-text:#f4eaff; --ize-muted:#b5a0cb;
    --ize-auf-akzent:#0b0515;
    --ize-seitenhintergrund:
        linear-gradient(rgba(120,87,255,.035) 1px,transparent 1px),
        linear-gradient(90deg,rgba(41,244,255,.035) 1px,transparent 1px),
        radial-gradient(1100px 680px at 50% -18%,#451668 0%,#0b0515 63%);
    --ize-flaeche:rgba(37,13,54,.82); --ize-flaeche-stark:#150820;
    --ize-eingabe:#0d0516; --ize-rand:rgba(41,244,255,.25);
    --ize-schatten:rgba(0,0,0,.80);
}
html:has(#ize-theme-marker[data-ize-theme="Scene"]),
body:has(#ize-theme-marker[data-ize-theme="Scene"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) {
    color-scheme:dark;
    --ize-magenta:#ff3bd4; --ize-cyan:#00e5ff; --ize-blau:#f2f2f2;
    --ize-kopftext:#ffffff; --ize-text:#ededed; --ize-muted:#8a8a8a;
    --ize-auf-akzent:#050505;
    --ize-seitenhintergrund:
        repeating-linear-gradient(0deg,rgba(255,255,255,.018) 0 1px,transparent 1px 4px),
        radial-gradient(760px 420px at 8% -10%,rgba(0,229,255,.075),transparent 64%),
        radial-gradient(680px 380px at 92% 0%,rgba(255,59,212,.055),transparent 62%),
        #000000;
    --ize-flaeche:rgba(11,11,11,.96); --ize-flaeche-stark:#050505;
    --ize-eingabe:#000000; --ize-rand:rgba(255,255,255,.18);
    --ize-schatten:rgba(0,0,0,.96);
}
html:has(#ize-theme-marker[data-ize-theme="Pixel"]),
body:has(#ize-theme-marker[data-ize-theme="Pixel"]),
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) {
    color-scheme:dark;
    --ize-magenta:#7659a8; --ize-cyan:#b6acd2; --ize-blau:#e43b3f;
    --ize-kopftext:#f4f1e8; --ize-text:#ece9e1; --ize-muted:#aaa7ad;
    --ize-auf-akzent:#17171d;
    --ize-seitenhintergrund:
        linear-gradient(45deg,rgba(182,172,210,.035) 25%,transparent 25% 75%,rgba(182,172,210,.035) 75%),
        linear-gradient(45deg,rgba(228,59,63,.025) 25%,transparent 25% 75%,rgba(228,59,63,.025) 75%),
        linear-gradient(145deg,#35343c 0%,#17171d 68%);
    --ize-flaeche:rgba(57,56,64,.88); --ize-flaeche-stark:#29282f;
    --ize-eingabe:#18181d; --ize-rand:rgba(211,207,216,.24);
    --ize-schatten:rgba(0,0,0,.82);
}

body:has(#ize-theme-marker),
.gradio-container:has(#ize-theme-marker) {
    --body-background-fill:var(--ize-flaeche-stark);
    --body-background-fill-dark:var(--ize-flaeche-stark);
    --body-text-color:var(--ize-text);
    --body-text-color-dark:var(--ize-text);
    --background-fill-primary:var(--ize-flaeche-stark);
    --background-fill-primary-dark:var(--ize-flaeche-stark);
    --background-fill-secondary:var(--ize-flaeche);
    --background-fill-secondary-dark:var(--ize-flaeche);
    --block-background-fill:var(--ize-flaeche);
    --block-background-fill-dark:var(--ize-flaeche);
    --block-border-color:var(--ize-rand);
    --block-border-color-dark:var(--ize-rand);
    --input-background-fill:var(--ize-eingabe);
    --input-background-fill-dark:var(--ize-eingabe);
    --input-border-color:var(--ize-rand);
    --input-border-color-dark:var(--ize-rand);
    --color-accent:var(--ize-cyan);
    --color-accent-soft:color-mix(in srgb,var(--ize-cyan) 20%,transparent);
    --button-primary-background-fill:var(--ize-blau);
    --button-primary-background-fill-dark:var(--ize-blau);
    --button-primary-background-fill-hover:var(--ize-cyan);
    --button-primary-background-fill-hover-dark:var(--ize-cyan);
    --button-primary-border-color:var(--ize-cyan);
    --button-primary-border-color-dark:var(--ize-cyan);
    --button-primary-text-color:var(--ize-auf-akzent);
    --button-primary-text-color-dark:var(--ize-auf-akzent);
    --button-secondary-background-fill:var(--ize-flaeche-stark);
    --button-secondary-background-fill-dark:var(--ize-flaeche-stark);
    --button-secondary-background-fill-hover:color-mix(in srgb,var(--ize-blau) 20%,var(--ize-flaeche-stark));
    --button-secondary-background-fill-hover-dark:color-mix(in srgb,var(--ize-blau) 20%,var(--ize-flaeche-stark));
    --button-secondary-border-color:var(--ize-rand);
    --button-secondary-border-color-dark:var(--ize-rand);
    --button-secondary-border-color-hover:var(--ize-cyan);
    --button-secondary-border-color-hover-dark:var(--ize-cyan);
    --button-secondary-text-color:var(--ize-text);
    --button-secondary-text-color-dark:var(--ize-text);
    --button-secondary-text-color-hover:var(--ize-kopftext);
    --button-secondary-text-color-hover-dark:var(--ize-kopftext);
    --checkbox-background-color-selected:var(--ize-blau);
    --checkbox-background-color-selected-dark:var(--ize-blau);
    --checkbox-border-color-selected:var(--ize-cyan);
    --checkbox-border-color-selected-dark:var(--ize-cyan);
    --input-border-color-focus:var(--ize-cyan);
    --input-border-color-focus-dark:var(--ize-cyan);
    --input-shadow-focus:0 0 0 3px color-mix(in srgb,var(--ize-cyan) 26%,transparent);
    --input-shadow-focus-dark:0 0 0 3px color-mix(in srgb,var(--ize-cyan) 26%,transparent);
}
body:has(#ize-theme-marker),
.gradio-container:has(#ize-theme-marker) {
    color:var(--ize-text) !important;
}
.gradio-container:has(#ize-theme-marker) .block,
.gradio-container:has(#ize-theme-marker) .form,
.gradio-container:has(#ize-theme-marker) .panel,
.gradio-container:has(#ize-theme-marker) fieldset {
    color:var(--ize-text) !important;
    background:var(--ize-flaeche) !important;
    border-color:var(--ize-rand) !important;
    transition:background .34s ease,border-color .28s ease,color .24s ease;
}
/* Kein background-Kurzformat auf Checkbox/Radio: Es setzt background-image
   auf none und lässt dadurch Haken bzw. Radiopunkt verschwinden. */
.gradio-container:has(#ize-theme-marker) input:not([type="checkbox"]):not([type="radio"]):not([type="range"]),
.gradio-container:has(#ize-theme-marker) textarea,
.gradio-container:has(#ize-theme-marker) select {
    color:var(--ize-text) !important;
    background-color:var(--ize-eingabe) !important;
    border-color:var(--ize-rand) !important;
}
.gradio-container:has(#ize-theme-marker) button {
    color:var(--ize-text) !important;
    background:color-mix(in srgb,var(--ize-blau) 10%,var(--ize-flaeche-stark)) !important;
    border-color:color-mix(in srgb,var(--ize-blau) 34%,var(--ize-rand)) !important;
    box-shadow:0 8px 20px -18px var(--ize-schatten),
               inset 0 1px 0 color-mix(in srgb,var(--ize-text) 7%,transparent) !important;
    isolation:isolate;
    overflow:hidden;
    position:relative;
}
.gradio-container:has(#ize-theme-marker) button:hover {
    color:var(--ize-kopftext) !important;
    background:linear-gradient(115deg,
        color-mix(in srgb,var(--ize-blau) 28%,var(--ize-flaeche-stark)),
        color-mix(in srgb,var(--ize-cyan) 18%,var(--ize-flaeche-stark))) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 78%,var(--ize-rand)) !important;
    box-shadow:0 0 0 1px color-mix(in srgb,var(--ize-cyan) 24%,transparent),
               0 14px 30px -14px color-mix(in srgb,var(--ize-blau) 75%,var(--ize-schatten)),
               inset 0 1px 0 color-mix(in srgb,var(--ize-text) 15%,transparent) !important;
    filter:brightness(1.08) saturate(1.12);
    transform:translateY(-2px);
}
.gradio-container:has(#ize-theme-marker) button::after {
    content:"";
    position:absolute;
    z-index:0;
    inset:-2px;
    pointer-events:none;
    background:linear-gradient(105deg,transparent 20%,
        color-mix(in srgb,var(--ize-cyan) 22%,transparent) 48%,transparent 72%);
    transform:translateX(-125%);
    transition:transform .38s cubic-bezier(.2,.75,.25,1);
}
.gradio-container:has(#ize-theme-marker) button:hover::after {
    transform:translateX(125%);
}
.gradio-container:has(#ize-theme-marker) button.primary {
    color:var(--ize-auf-akzent) !important;
    background:linear-gradient(115deg,var(--ize-blau),var(--ize-cyan)) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 72%,white) !important;
    box-shadow:0 10px 26px -15px var(--ize-cyan),
               inset 0 1px 0 color-mix(in srgb,white 38%,transparent) !important;
    font-weight:800 !important;
}
.gradio-container:has(#ize-theme-marker) button.primary:hover {
    color:var(--ize-auf-akzent) !important;
    background:linear-gradient(115deg,
        color-mix(in srgb,var(--ize-blau) 82%,white),
        color-mix(in srgb,var(--ize-cyan) 76%,white)) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 62%,white) !important;
    box-shadow:0 0 0 2px color-mix(in srgb,var(--ize-cyan) 24%,transparent),
               0 16px 34px -12px var(--ize-cyan),
               inset 0 1px 0 rgba(255,255,255,.42) !important;
    filter:saturate(1.18) brightness(1.07);
    transform:translateY(-3px) scale(1.012);
}
.gradio-container:has(#ize-theme-marker) button.stop {
    color:#fff !important;
    background:linear-gradient(115deg,#b42343,#ef476f) !important;
    border-color:#ff6f8d !important;
    box-shadow:0 10px 25px -15px rgba(239,71,111,.72),
               inset 0 1px 0 rgba(255,255,255,.20) !important;
    font-weight:800 !important;
}
.gradio-container:has(#ize-theme-marker) button.stop:hover {
    color:#fff !important;
    background:linear-gradient(115deg,#d52f53,#ff6f8d) !important;
    border-color:#ffb0c1 !important;
    box-shadow:0 0 0 2px rgba(255,111,141,.22),
               0 16px 34px -12px rgba(239,71,111,.90),
               inset 0 1px 0 rgba(255,255,255,.32) !important;
    filter:saturate(1.18) brightness(1.08);
    transform:translateY(-3px) scale(1.012);
}
.gradio-container:has(#ize-theme-marker) button:active,
.gradio-container:has(#ize-theme-marker) button.primary:active,
.gradio-container:has(#ize-theme-marker) button.stop:active {
    transform:translateY(1px) scale(.985);
    filter:brightness(.98);
}
.gradio-container:has(#ize-theme-marker) button:focus,
.gradio-container:has(#ize-theme-marker) button:focus-visible {
    outline:none !important;
    border-color:var(--ize-cyan) !important;
    box-shadow:0 0 0 3px color-mix(in srgb,var(--ize-cyan) 32%,transparent),
               0 13px 30px -15px var(--ize-cyan) !important;
}
.gradio-container:has(#ize-theme-marker) button.selected,
.gradio-container:has(#ize-theme-marker) button.active,
.gradio-container:has(#ize-theme-marker) button[aria-pressed="true"],
.gradio-container:has(#ize-theme-marker) button[data-selected="true"] {
    color:var(--ize-auf-akzent) !important;
    background:linear-gradient(115deg,var(--ize-blau),var(--ize-cyan)) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 68%,white) !important;
    box-shadow:0 0 0 2px color-mix(in srgb,var(--ize-cyan) 22%,transparent),
               0 12px 28px -13px var(--ize-cyan) !important;
}
.gradio-container:has(#ize-theme-marker) .tab-nav button.selected,
.gradio-container:has(#ize-theme-marker) button[aria-selected="true"] {
    color:var(--ize-kopftext) !important;
    background:color-mix(in srgb,var(--ize-blau) 20%,var(--ize-flaeche-stark)) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 56%,var(--ize-rand)) !important;
    box-shadow:inset 0 -3px 0 var(--ize-cyan),
               0 10px 24px -18px var(--ize-cyan) !important;
}
.gradio-container:has(#ize-theme-marker) input[type="range"] {
    accent-color:var(--ize-cyan) !important;
}
/* Gradio zeichnet Checkboxen und Radios selbst. Diese Regeln setzen den
   sichtbaren Zustand absichtlich vollständig, damit alle Themes funktionieren
   und auch Browser-Unterschiede keinen Haken verschlucken. */
.gradio-container:has(#ize-theme-marker) input[type="checkbox"],
.gradio-container:has(#ize-theme-marker) input[type="radio"] {
    accent-color:var(--ize-blau) !important;
    background-color:color-mix(in srgb,var(--ize-eingabe) 88%,var(--ize-blau)) !important;
    background-image:none !important;
    border-color:color-mix(in srgb,var(--ize-blau) 52%,var(--ize-rand)) !important;
    box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--ize-text) 5%,transparent) !important;
}
.gradio-container:has(#ize-theme-marker) input[type="checkbox"]:hover,
.gradio-container:has(#ize-theme-marker) input[type="radio"]:hover {
    border-color:var(--ize-cyan) !important;
    box-shadow:0 0 0 3px color-mix(in srgb,var(--ize-cyan) 18%,transparent) !important;
}
.gradio-container:has(#ize-theme-marker) input[type="checkbox"]:focus-visible,
.gradio-container:has(#ize-theme-marker) input[type="radio"]:focus-visible {
    outline:none !important;
    border-color:var(--ize-cyan) !important;
    box-shadow:0 0 0 3px color-mix(in srgb,var(--ize-cyan) 28%,transparent) !important;
}
.gradio-container:has(#ize-theme-marker) input[type="checkbox"]:checked {
    background-color:var(--ize-blau) !important;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3 8.3 6.4 12 13.2 4.2' fill='none' stroke='%23070a10' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'/%3E%3Cpath d='M3 8.3 6.4 12 13.2 4.2' fill='none' stroke='%23fff' stroke-width='2.15' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") !important;
    background-position:center !important;
    background-repeat:no-repeat !important;
    background-size:88% 88% !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 72%,var(--ize-blau)) !important;
}
.gradio-container:has(#ize-theme-marker) input[type="radio"]:checked {
    background-color:var(--ize-blau) !important;
    background-image:radial-gradient(circle at center,#fff 0 24%,#10141c 27% 41%,transparent 44%) !important;
    background-position:center !important;
    background-repeat:no-repeat !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 72%,var(--ize-blau)) !important;
}
/* Die ganze Auswahlzeile bekommt nun einen eindeutigen Hover- und Aktivzustand.
   Das greift sowohl bei einzelnen Checkboxen als auch bei Radio-Gruppen. */
.gradio-container:has(#ize-theme-marker) label:has(input[type="checkbox"]),
.gradio-container:has(#ize-theme-marker) label:has(input[type="radio"]) {
    border-radius:8px;
    transition:background .16s ease,border-color .16s ease,color .16s ease,
               box-shadow .16s ease,transform .16s ease !important;
}
.gradio-container:has(#ize-theme-marker) label:has(input[type="checkbox"]):hover,
.gradio-container:has(#ize-theme-marker) label:has(input[type="radio"]):hover {
    color:var(--ize-kopftext) !important;
    background:color-mix(in srgb,var(--ize-blau) 17%,var(--ize-flaeche-stark)) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 54%,var(--ize-rand)) !important;
    box-shadow:0 8px 20px -17px var(--ize-schatten),
               inset 2px 0 0 var(--ize-cyan) !important;
    transform:translateX(1px);
}
.gradio-container:has(#ize-theme-marker) label.selected:has(input[type="checkbox"]),
.gradio-container:has(#ize-theme-marker) label.selected:has(input[type="radio"]),
.gradio-container:has(#ize-theme-marker) label:has(input[type="checkbox"]:checked),
.gradio-container:has(#ize-theme-marker) label:has(input[type="radio"]:checked) {
    color:var(--ize-kopftext) !important;
    background:color-mix(in srgb,var(--ize-blau) 25%,var(--ize-flaeche-stark)) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 64%,var(--ize-rand)) !important;
    box-shadow:inset 3px 0 0 var(--ize-cyan),
               0 9px 22px -18px var(--ize-schatten) !important;
}
.gradio-container:has(#ize-theme-marker) input[type="range"]::-webkit-slider-runnable-track {
    background:linear-gradient(90deg,
        color-mix(in srgb,var(--ize-blau) 52%,var(--ize-eingabe)),
        color-mix(in srgb,var(--ize-cyan) 32%,var(--ize-eingabe))) !important;
}
.gradio-container:has(#ize-theme-marker) input[type="range"]::-webkit-slider-thumb {
    background:var(--ize-cyan) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 64%,white) !important;
    box-shadow:0 0 0 3px color-mix(in srgb,var(--ize-cyan) 18%,transparent) !important;
}
/* Nur die eigentliche Optionsliste stylen. Das Eingabefeld des Dropdowns
   trägt in Gradio ebenfalls role=listbox und wurde vorher versehentlich wie
   das aufgeklappte Menü behandelt. */
body[data-ize-theme] ul[role="listbox"] {
    color:var(--ize-text) !important;
    background:var(--ize-flaeche-stark) !important;
    border:1px solid color-mix(in srgb,var(--ize-cyan) 34%,var(--ize-rand)) !important;
    border-radius:10px !important;
    box-shadow:0 22px 58px -18px var(--ize-schatten),
               0 0 0 1px color-mix(in srgb,var(--ize-blau) 12%,transparent) !important;
    scrollbar-color:color-mix(in srgb,var(--ize-blau) 70%,var(--ize-muted))
                    var(--ize-flaeche-stark);
}
body[data-ize-theme] li[role="option"] {
    color:var(--ize-text) !important;
    background:var(--ize-flaeche-stark) !important;
    border-radius:7px;
    margin:2px 4px;
    transition:background .14s ease,color .14s ease,box-shadow .14s ease !important;
}
body[data-ize-theme] li[role="option"]:hover,
body[data-ize-theme] li[role="option"].active,
body[data-ize-theme] li[role="option"][aria-selected="true"] {
    color:var(--ize-kopftext) !important;
    background:color-mix(in srgb,var(--ize-blau) 27%,var(--ize-flaeche-stark)) !important;
    box-shadow:inset 3px 0 0 var(--ize-cyan) !important;
}
body[data-ize-theme] li[role="option"][aria-selected="true"] > span:first-child {
    color:var(--ize-cyan) !important;
    visibility:visible !important;
    opacity:1 !important;
    font-weight:900 !important;
}
/* Gradio 6 berechnet top/bottom/width für das Menü anhand des Viewports und
   erwartet position:fixed. Der frühere absolute-Workaround band das Menü an
   Karten und Spalten; dadurch öffnete es versetzt und verschwand hinter DIVs. */
.gradio-container:has(#ize-theme-marker) ul[role="listbox"] {
    position:fixed !important;
    z-index:2147483000 !important;
    max-height:min(320px,50vh) !important;
    isolation:isolate;
}
/* Beim geöffneten Menü dürfen Karten/Blocks keinen eigenen niedrigen Layer
   oder Clipping-Rahmen bilden. :has() trifft nur während des Öffnens zu. */
.gradio-container:has(#ize-theme-marker) .ize-karte:has(ul[role="listbox"]),
.gradio-container:has(#ize-theme-marker) .block:has(ul[role="listbox"]),
.gradio-container:has(#ize-theme-marker) .form:has(ul[role="listbox"]),
.gradio-container:has(#ize-theme-marker) fieldset:has(ul[role="listbox"]) {
    position:relative !important;
    z-index:2147482000 !important;
    overflow:visible !important;
}
/* Auch der geschlossene Dropdown-Kopf zeigt Hover und Tastaturfokus deutlich. */
.gradio-container:has(#ize-theme-marker) .wrap:has(input[role="listbox"]) {
    overflow:visible !important;
    transition:border-color .16s ease,box-shadow .16s ease,background .16s ease !important;
}
.gradio-container:has(#ize-theme-marker) .wrap:has(input[role="listbox"]):hover {
    border-color:color-mix(in srgb,var(--ize-cyan) 55%,var(--ize-rand)) !important;
    box-shadow:0 0 0 2px color-mix(in srgb,var(--ize-cyan) 12%,transparent) !important;
}
.gradio-container:has(#ize-theme-marker) .wrap:has(input[role="listbox"]):focus-within {
    border-color:var(--ize-cyan) !important;
    box-shadow:0 0 0 3px color-mix(in srgb,var(--ize-cyan) 22%,transparent) !important;
}
.gradio-container:has(#ize-theme-marker) label,
.gradio-container:has(#ize-theme-marker) .prose,
.gradio-container:has(#ize-theme-marker) .markdown {
    color:var(--ize-text);
}
.gradio-container:has(#ize-theme-marker) #ize-kopf,
.gradio-container:has(#ize-theme-marker) .ize-karte,
.gradio-container:has(#ize-theme-marker) .ize-batch,
.gradio-container:has(#ize-theme-marker) .ize-grid > div {
    color:var(--ize-text) !important;
    background:var(--ize-flaeche) !important;
    border-color:var(--ize-rand) !important;
}
.gradio-container:has(#ize-theme-marker) #ize-kopf {
    background:
        linear-gradient(125deg,
            color-mix(in srgb,var(--ize-magenta) 13%,var(--ize-flaeche)),
            color-mix(in srgb,var(--ize-blau) 9%,var(--ize-flaeche)) 55%,
            color-mix(in srgb,var(--ize-cyan) 11%,var(--ize-flaeche))) !important;
    border-color:color-mix(in srgb,var(--ize-cyan) 42%,var(--ize-rand)) !important;
    box-shadow:0 18px 44px -30px var(--ize-schatten),
               inset 0 1px 0 color-mix(in srgb,var(--ize-text) 8%,transparent) !important;
}
.gradio-container:has(#ize-theme-marker) .ize-batch {
    background:linear-gradient(145deg,
        color-mix(in srgb,var(--ize-blau) 9%,var(--ize-flaeche)),
        color-mix(in srgb,var(--ize-magenta) 7%,var(--ize-flaeche))) !important;
}
.gradio-container:has(#ize-theme-marker) .label-wrap {
    color:var(--ize-text) !important;
    background:color-mix(in srgb,var(--ize-blau) 7%,var(--ize-flaeche-stark)) !important;
    box-shadow:inset 2px 0 0 color-mix(in srgb,var(--ize-blau) 52%,var(--ize-rand)) !important;
}
.gradio-container:has(#ize-theme-marker) .label-wrap:hover {
    color:var(--ize-kopftext) !important;
    background:linear-gradient(90deg,
        color-mix(in srgb,var(--ize-blau) 25%,var(--ize-flaeche-stark)),
        color-mix(in srgb,var(--ize-magenta) 10%,var(--ize-flaeche-stark))) !important;
    box-shadow:inset 3px 0 0 var(--ize-cyan),
               0 9px 24px -20px var(--ize-cyan) !important;
}
.gradio-container:has(#ize-theme-marker) .ize-bar-fuell.fertig {
    background:linear-gradient(90deg,var(--ize-blau),var(--ize-cyan),var(--ize-magenta));
    box-shadow:0 0 22px color-mix(in srgb,var(--ize-cyan) 72%,transparent),
               0 0 46px color-mix(in srgb,var(--ize-blau) 36%,transparent);
}
.gradio-container:has(#ize-theme-marker) .ize-rahmen,
.gradio-container:has(#ize-theme-marker) .ize-editor {
    color:var(--ize-text) !important;
    background:var(--ize-flaeche-stark) !important;
}
.gradio-container:has(#ize-theme-marker) .ize-liste thead th {
    color:var(--ize-muted) !important;
    background:var(--ize-flaeche-stark) !important;
}
.gradio-container:has(#ize-theme-marker) .ize-editor-treffer button,
.gradio-container:has(#ize-theme-marker) .ize-knopf {
    color:var(--ize-text) !important;
    background:color-mix(in srgb,var(--ize-blau) 12%,var(--ize-eingabe)) !important;
    border-color:color-mix(in srgb,var(--ize-blau) 38%,var(--ize-rand)) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Default"]) {
    background-size:42px 42px,42px 42px,auto,auto !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Default"]) #ize-kopf h1 {
    text-shadow:-2px 0 14px rgba(255,79,216,.35),
                2px 0 16px rgba(34,224,255,.42) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Flashbang"]) {
    background-size:64px 64px,80px 80px,auto !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Flashbang"]) .block,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Flashbang"]) .form,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Flashbang"]) .panel {
    box-shadow:0 14px 36px -27px rgba(37,55,85,.48);
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Flashbang"]) #ize-kopf {
    box-shadow:0 22px 48px -34px rgba(37,99,235,.52) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Flashbang"]) #ize-kopf h1 {
    text-shadow:2px 2px 0 rgba(37,99,235,.13) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Darkmore"]) {
    background-size:88px 88px,auto,auto !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Darkmore"]) .block,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Darkmore"]) .ize-karte {
    border-radius:6px !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Darkmore"]) #ize-kopf {
    border-left:3px solid #38bdf8 !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Darkmore"]) #ize-kopf h1 {
    text-shadow:0 0 18px rgba(56,189,248,.36),
                12px 0 26px rgba(217,70,239,.16) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Dracula"]) {
    background-size:54px 54px,104px 104px,auto !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Dracula"]) #ize-kopf {
    border-color:rgba(255,121,198,.42) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Dracula"]) #ize-kopf h1 {
    text-shadow:-2px 2px 0 rgba(255,121,198,.24),
                2px -2px 0 rgba(139,233,253,.16),
                0 0 20px rgba(189,147,249,.30) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Fallout"]) {
    background-size:auto,72px 72px,auto !important;
    font-family:ui-monospace,Consolas,"Cascadia Mono",monospace;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Fallout"]) #ize-kopf {
    border-radius:5px !important;
    border-color:rgba(121,255,99,.42) !important;
    box-shadow:inset 0 0 24px rgba(121,255,99,.045),
               0 0 34px -22px rgba(121,255,99,.70) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Fallout"]) #ize-kopf h1 {
    text-shadow:0 0 7px rgba(121,255,99,.90),
                0 0 18px rgba(121,255,99,.48) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Hyrule"]) {
    background-size:76px 76px,auto,auto !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Hyrule"]) #ize-kopf {
    border-color:rgba(228,184,90,.48) !important;
    box-shadow:inset 0 0 26px rgba(228,184,90,.04),
               0 18px 44px -30px rgba(228,184,90,.42) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Hyrule"]) #ize-kopf h1 {
    font-family:Georgia,"Times New Roman",serif;
    text-shadow:0 2px 0 rgba(0,0,0,.34),
                0 0 18px rgba(228,184,90,.38) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Crimson"]) #ize-kopf {
    border-color:rgba(232,184,108,.44) !important;
    box-shadow:inset 3px 0 0 rgba(255,97,95,.62),
               0 20px 46px -32px rgba(255,97,95,.52) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Crimson"]) #ize-kopf h1 {
    font-family:Georgia,"Times New Roman",serif;
    text-shadow:0 2px 0 #3a0e14,
                0 0 20px rgba(255,97,95,.42) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Nordic"]) #ize-kopf {
    border-radius:7px !important;
    border-color:rgba(142,234,255,.39) !important;
    box-shadow:inset 0 1px 0 rgba(244,251,255,.13),
               0 20px 45px -32px rgba(142,234,255,.48) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Nordic"]) #ize-kopf h1 {
    text-shadow:0 1px 0 rgba(255,255,255,.20),
                0 0 18px rgba(142,234,255,.38) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Retro"]) {
    background-size:36px 36px,36px 36px,auto !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Retro"]) #ize-kopf h1 {
    text-shadow:2px 2px 0 #7857ff,0 0 18px rgba(41,244,255,.42) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) {
    font-family:ui-monospace,Consolas,"Cascadia Mono",monospace;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) .block,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) .ize-karte,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) #ize-kopf {
    border-radius:2px !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) #ize-kopf {
    border-left:3px solid #f2f2f2 !important;
    box-shadow:inset 0 0 25px rgba(255,255,255,.025),
               0 0 32px -22px rgba(0,229,255,.58) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) #ize-kopf::before {
    content:"";
    display:block;
    margin-bottom:8px;
    color:#00e5ff;
    font-size:10px;
    font-weight:700;
    letter-spacing:.16em;
    white-space:pre;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Scene"]) #ize-kopf h1 {
    letter-spacing:.20em;
    text-shadow:2px 0 0 rgba(255,60,172,.34),
                0 0 10px rgba(255,255,255,.30) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) {
    background-size:16px 16px,16px 16px,auto !important;
    background-position:0 0,8px 8px,0 0 !important;
    font-family:ui-monospace,Consolas,"Cascadia Mono",monospace;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) #ize-kopf h1 {
    letter-spacing:.08em;
    text-shadow:3px 3px 0 #7659a8,-2px -2px 0 rgba(228,59,63,.52) !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) button,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) input,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) textarea,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) select,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) .block,
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) .ize-karte {
    border-radius:3px !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) button {
    box-shadow:3px 3px 0 #101014 !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) button:hover {
    transform:translate(-1px,-1px);
    box-shadow:4px 4px 0 #101014 !important;
}
.gradio-container:has(#ize-theme-marker[data-ize-theme="Pixel"]) button:active {
    transform:translate(2px,2px);
    box-shadow:1px 1px 0 #101014 !important;
}
html.ize-theme-wechselt .gradio-container {
    animation:ize-theme-puls .38s ease both;
}
@keyframes ize-theme-puls {
    0% { opacity:.90; }
    55% { opacity:.98; }
    100% { opacity:1; }
}
"""


def baue_thema(name: str = "Default"):
    try:
        import gradio as gr

        name = normalisiere_theme(name)
        farben = {
            "Default": ("fuchsia", "cyan", "slate"),
            "Flashbang": ("blue", "sky", "gray"),
            "Darkmore": ("blue", "cyan", "slate"),
            "Dracula": ("purple", "pink", "slate"),
            "Fallout": ("lime", "green", "slate"),
            "Hyrule": ("green", "amber", "slate"),
            "Crimson": ("red", "orange", "slate"),
            "Nordic": ("sky", "blue", "slate"),
            "Retro": ("purple", "cyan", "slate"),
            "Scene": ("gray", "cyan", "slate"),
            "Pixel": ("red", "purple", "gray"),
        }[name]
        thema = gr.themes.Base(
            primary_hue=farben[0], secondary_hue=farben[1], neutral_hue=farben[2]
        )
        if name == "Flashbang":
            thema = thema.set(
                body_background_fill="#f4f7fb", body_background_fill_dark="#f4f7fb",
                body_text_color="#172033", body_text_color_dark="#172033",
                background_fill_primary="#ffffff", background_fill_primary_dark="#ffffff",
                background_fill_secondary="#eef3fa", background_fill_secondary_dark="#eef3fa",
            )
        elif name == "Darkmore":
            thema = thema.set(
                body_background_fill="#020306", body_background_fill_dark="#020306",
                background_fill_primary="#05070b", background_fill_primary_dark="#05070b",
                background_fill_secondary="#090c12", background_fill_secondary_dark="#090c12",
            )
        elif name == "Dracula":
            thema = thema.set(
                body_background_fill="#282a36", body_background_fill_dark="#282a36",
                background_fill_primary="#343746", background_fill_primary_dark="#343746",
                background_fill_secondary="#44475a", background_fill_secondary_dark="#44475a",
            )
        elif name == "Fallout":
            thema = thema.set(
                body_background_fill="#070b05", body_background_fill_dark="#070b05",
                body_text_color="#c9ff9d", body_text_color_dark="#c9ff9d",
                background_fill_primary="#091006", background_fill_primary_dark="#091006",
                background_fill_secondary="#111d0c", background_fill_secondary_dark="#111d0c",
            )
        elif name == "Hyrule":
            thema = thema.set(
                body_background_fill="#07160f", body_background_fill_dark="#07160f",
                body_text_color="#edf6df", body_text_color_dark="#edf6df",
                background_fill_primary="#0a2116", background_fill_primary_dark="#0a2116",
                background_fill_secondary="#113423", background_fill_secondary_dark="#113423",
            )
        elif name == "Crimson":
            thema = thema.set(
                body_background_fill="#120708", body_background_fill_dark="#120708",
                body_text_color="#fae7db", body_text_color_dark="#fae7db",
                background_fill_primary="#210b0e", background_fill_primary_dark="#210b0e",
                background_fill_secondary="#3d1217", background_fill_secondary_dark="#3d1217",
            )
        elif name == "Nordic":
            thema = thema.set(
                body_background_fill="#0b1218", body_background_fill_dark="#0b1218",
                body_text_color="#e7f1f7", body_text_color_dark="#e7f1f7",
                background_fill_primary="#121c24", background_fill_primary_dark="#121c24",
                background_fill_secondary="#22313d", background_fill_secondary_dark="#22313d",
            )
        elif name == "Retro":
            thema = thema.set(
                body_background_fill="#0b0515", body_background_fill_dark="#0b0515",
                body_text_color="#f4eaff", body_text_color_dark="#f4eaff",
                background_fill_primary="#150820", background_fill_primary_dark="#150820",
                background_fill_secondary="#250d36", background_fill_secondary_dark="#250d36",
            )
        elif name == "Scene":
            thema = thema.set(
                body_background_fill="#000000", body_background_fill_dark="#000000",
                body_text_color="#ededed", body_text_color_dark="#ededed",
                background_fill_primary="#050505", background_fill_primary_dark="#050505",
                background_fill_secondary="#0b0b0b", background_fill_secondary_dark="#0b0b0b",
            )
        elif name == "Pixel":
            thema = thema.set(
                body_background_fill="#17171d", body_background_fill_dark="#17171d",
                body_text_color="#ece9e1", body_text_color_dark="#ece9e1",
                background_fill_primary="#29282f", background_fill_primary_dark="#29282f",
                background_fill_secondary="#393840", background_fill_secondary_dark="#393840",
            )
        return thema
    except Exception:
        return None


def passende_argumente(funktion, **kandidaten) -> dict:
    """Behaelt nur die Argumente, die diese Gradio-Fassung wirklich kennt."""
    import inspect

    try:
        erlaubt = set(inspect.signature(funktion).parameters)
    except (TypeError, ValueError):
        return dict(kandidaten)
    if "kwargs" in erlaubt:          # durchgereichte Signatur - nichts filtern
        return dict(kandidaten)
    return {name: wert for name, wert in kandidaten.items() if name in erlaubt}


def mach(klasse, **argumente):
    """
    Erzeugt eine Gradio-Komponente und laesst dabei Parameter weg, die die
    installierte Gradio-Fassung nicht kennt (z. B. show_copy_button ab Gradio 6).
    So bleibt die Oberflaeche ueber Versionsgrenzen hinweg lauffaehig.
    """
    rest = dict(argumente)
    for _versuch in range(len(argumente) + 1):
        try:
            return klasse(**rest)
        except TypeError as fehler:
            name = next((n for n in list(rest) if f"'{n}'" in str(fehler)), None)
            if name is None:
                raise
            rest.pop(name)
            sag(f"Hinweis: »{name}« kennt diese Gradio-Fassung nicht und wird weggelassen.")
    return klasse()


def arbeiter_zustand_html(zusatz: str = "") -> str:
    """Kleine Statuskarte fuer die Einstellungen."""
    pool = VERWALTUNG.laufend()
    if pool is None:
        farbe, titel = "#8a93a6", "KEINE ARBEITER GESTARTET"
        text = ("Der Stapel rechnet dann im Hauptprozess – ein Auftrag nach dem anderen. "
                "Kein zusätzlicher Grafikspeicher.")
    elif pool.bereit_anzahl() == pool.anzahl:
        farbe, titel = "#46e08a", f"{pool.anzahl} ARBEITER BEREIT"
        text = f"Beschäftigt: {pool.beschaeftigt()} · frei: {pool.bereit_anzahl() - pool.beschaeftigt()}"
    else:
        farbe, titel = "#ffc857", "ARBEITER WERDEN VORBEREITET"
        text = f"{pool.bereit_anzahl()} von {pool.anzahl} bereit – jeder lädt sein eigenes Modell."
    if zusatz:
        text += "<br>" + html.escape(zusatz)
    return (f"<div class='ize-batch' style='padding:12px 16px'>"
            f"<span class='ize-batch-titel' style='color:{farbe}'>{titel}</span>"
            f"<div style='font-size:12.5px;opacity:.75;margin-top:6px'>{text}</div></div>")


def baue_oberflaeche(ausgabe_ordner: Path, einstellungen_pfad: Path = None):
    import gradio as gr

    stapel_basis = ausgabe_ordner / "batch"
    einstellungen_pfad = einstellungen_pfad or (ausgabe_ordner / "einstellungen.json")
    einst = lies_einstellungen(einstellungen_pfad)
    theme_name = normalisiere_theme(einst.get("theme", "Default"))
    empfehlung = empfohlene_arbeiter(MOTOR.vram_gb)
    bewertungen = whisper_dienst.BewertungsSpeicher(
        einstellungen_pfad.parent / "whisper-bewertungen.json"
    )
    listen_basis = ausgabe_ordner / "listen"

    def audio_eingabe(**kw):
        return mach(gr.Audio, sources=["upload", "microphone"], type="filepath", **kw)

    def audio_ausgabe(beschriftung="Ergebnis"):
        return mach(gr.Audio, label=beschriftung, type="numpy",
                    autoplay=False, show_download_button=True)

    # ---------------------------------------------- Einzelstück
    def lauf(text, ref_audio, ref_text, schritte, tempo, laenge, modus,
             wie_probe=False, autoplay=False, versatz=0.0, stille=False,
             l_modus="aus", l_db=0.0, ersetzungen=""):
        beginn = time.time()
        try:
            text = ersetze_text((text or "").strip(), ersetzungen)
            ref_text = ersetze_text((ref_text or "").strip(), ersetzungen)
        except ValueError as fehler:
            return None, f"⚠️  Globale Textersetzungen sind ungültig: {fehler}", ""
        if not text:
            return None, "⚠️  Bitte zuerst einen Text eingeben, der gesprochen werden soll.", ""
        if modus == "klonen" and not ref_audio:
            return (
                None,
                "⚠️  Bitte eine Sprachprobe hochladen oder aufnehmen (5 bis 15 Sekunden).",
                "",
            )

        # Derselbe Weg wie im Stapel: Auftrag bauen, damit Länge, Stille und
        # Lautstärke hier genauso behandelt werden.
        auftrag = {"text": text, "num_step": int(schritte), "speed": float(tempo)}
        auftrag.update(klangwerte(versatz, stille, l_modus, l_db))
        vorgabe = ""
        if modus == "klonen":
            auftrag["ref_audio"] = ref_audio
            if ref_text:
                auftrag["ref_text"] = ref_text
            if wie_probe:
                probenlaenge = audiolaenge(ref_audio)
                if probenlaenge > 0.05:
                    auftrag["dauer_von_probe"] = True
                    vorgabe = (f" · Länge wie Sprachprobe "
                               f"({dauer_text(probenlaenge + float(versatz or 0.0))})")
                else:
                    vorgabe = " · Länge der Sprachprobe nicht lesbar – automatisch"
        if not auftrag.get("dauer_von_probe") and laenge and float(laenge) > 0:
            auftrag["duration"] = float(laenge)

        try:
            daten = als_array(MOTOR.erzeuge(**baue_argumente(auftrag)))
            daten, korrektur = nachbearbeiten(daten, auftrag)
            if abs(korrektur) > 0.02:
                vorgabe += (f" · um {dauer_text(abs(korrektur))} "
                            + ("gekürzt" if korrektur > 0 else "verlängert"))
        except Exception as fehler:
            traceback.print_exc()
            hinweis = f"❌  Es hat nicht geklappt: {type(fehler).__name__}: {fehler}"
            if "out of memory" in str(fehler).lower():
                hinweis += ("\n\nDer Grafikspeicher ist voll. Kürzeren Text versuchen, "
                            "andere Programme schließen oder die Qualitätsstufe senken.")
            return None, hinweis, ""

        gebraucht = time.time() - beginn
        ziel = None
        try:
            ziel = ausgabe_ordner / time.strftime("omnivoice_%Y-%m-%d_%H-%M-%S.wav")
            schreibe_wav(daten, ziel)
            gespeichert = f"\n💾  Gespeichert als **{ziel.name}** in `{ziel.parent}`"
        except Exception as fehler:
            gespeichert = f"\n(Speichern nicht möglich: {fehler})"

        # Das Gradio-autoplay-Attribut allein reicht nach einer längeren
        # Berechnung nicht: Browser betrachten play() dann nicht mehr als Teil
        # des ursprünglichen Klicks. Der dritte Rückgabewert steuert daher den
        # bereits beim Klick freigeschalteten Browser-Player.
        autoplay_uri = ""
        if autoplay and ziel is not None:
            try:
                autoplay_uri = json.dumps(
                    {"uri": tabelle.daten_uri(ziel), "id": time.time_ns()}
                )
            except Exception:
                pass
        return (ABTASTRATE, daten), (
            f"✅  Fertig in {dauer_text(gebraucht)} · Länge "
            f"{dauer_text(len(daten) / ABTASTRATE)}{vorgabe} · {MOTOR.geraetename}{gespeichert}"
        ), autoplay_uri

    # ---------------------------------------------- Stapel
    def stapel_pruefen(csv_datei, wurzel, ziel_basis):
        return pruefe_liste(csv_datei, wurzel, ziel_basis, stapel_basis)

    def klangwerte(versatz, stille, l_modus, l_db, ersetzungen="") -> dict:
        return {
            "dauer_offset": float(versatz or 0.0),
            "stille_weg": bool(stille),
            "lautstaerke_modus": LAUTSTAERKE_WAHL.get(l_modus, "aus"),
            "lautstaerke_db": float(l_db or 0.0),
            "text_ersetzungen": str(ersetzungen or ""),
        }

    def stapel_lauf(csv_datei, wurzel, ziel_basis, ueberspringen, schritte, tempo,
                    arbeiter, wie_probe, bericht, versatz, stille, l_modus, l_db,
                    pruefen, w_modell, w_geraet, ersetzungen):
        yield from stapel_durchlauf(csv_datei, wurzel, ziel_basis, ueberspringen,
                                    schritte, tempo, stapel_basis, arbeiter, wie_probe,
                                    bericht, klangwerte(
                                        versatz, stille, l_modus, l_db, ersetzungen
                                    ),
                                    pruefen, w_modell, w_geraet, bewertungen)

    # ---------------------------------------------- Listengenerator
    def parser_optionen(modus, trenner, id_spalte, text_spalte, regex):
        return listengenerator.ParserOptionen(
            modus=str(modus or "Automatisch"),
            trenner=str(trenner or "="),
            id_spalte=int(id_spalte or 1),
            text_spalte=int(text_spalte or 2),
            regex=str(regex or listengenerator.STANDARD_REGEX),
        )

    def listen_vorschau(audio_ordner, en_datei, de_datei, *parserwerte):
        if not audio_ordner or not en_datei or not de_datei:
            return "⚠️  Bitte Audioordner sowie englische und deutsche Textliste angeben."
        try:
            en_opt = parser_optionen(*parserwerte[:5])
            de_opt = parser_optionen(*parserwerte[5:])
            audios = listengenerator.audio_dateien(audio_ordner)
            en = listengenerator.parse_liste(en_datei, en_opt)
            de = listengenerator.parse_liste(de_datei, de_opt)
            _en_index, en_doppelt = listengenerator.als_index(en)
            de_index, de_doppelt = listengenerator.als_index(de)
            gemeinsam = sum(
                1 for eintrag in en
                if listengenerator.id_schluessel(eintrag.identifier) in de_index
            )
            return (
                f"✅ **{len(audios)} Audiodateien** · **{len(en)} englische** und "
                f"**{len(de)} deutsche Zeilen** erkannt · **{gemeinsam} IDs** in beiden Listen"
                + (f"\n\n⚠️ Doppelte IDs: EN {len(en_doppelt)}, DE {len(de_doppelt)}"
                   if en_doppelt or de_doppelt else "")
            )
        except Exception as fehler:
            return f"❌  Vorschau fehlgeschlagen: {fehler}"

    def liste_generieren(audio_ordner, en_datei, de_datei, minimum, unsichere,
                         w_modell, w_geraet, w_arbeiter, *parserwerte):
        beginn = time.time()
        if not audio_ordner or not en_datei or not de_datei:
            yield (
                listen_html("fehler", "Eingaben fehlen", 0, 0, 1, 0, 0, 0),
                None, None,
            )
            return
        try:
            en_opt = parser_optionen(*parserwerte[:5])
            de_opt = parser_optionen(*parserwerte[5:])
            audios = listengenerator.audio_dateien(audio_ordner)
            en = listengenerator.parse_liste(en_datei, en_opt)
            de = listengenerator.parse_liste(de_datei, de_opt)
            de_index, _doppelt = listengenerator.als_index(de)
        except Exception as fehler:
            yield (
                listen_html("fehler", str(fehler), 0, 0, 1, 0, 0, 0),
                None, None,
            )
            return
        if not audios:
            yield (
                listen_html("fehler", "keine Audiodateien gefunden", 0, 0, 1, 0, 0, 0),
                None, None,
            )
            return

        zeilen_nach_index = {}
        unsicher_anzahl, ohne_de, fehlerzahl = 0, 0, 0
        fehlertexte = []
        arbeiterzahl = max(1, min(8, int(w_arbeiter or 1)))
        minimum = max(0.0, min(100.0, float(minimum or 0)))
        yield (
            listen_html(
                "start", f"{arbeiterzahl} Whisper-Arbeiter werden vorbereitet …",
                0, len(audios), 0, 0, 0, 0
            ),
            None, None,
        )
        dienste = whisper_dienst.POOL.setze_anzahl(arbeiterzahl)
        executor = ThreadPoolExecutor(
            max_workers=arbeiterzahl, thread_name_prefix="omnivoice-whisper"
        )
        sauber_beendet = False
        try:
            futures = {
                executor.submit(
                    dienste[index % arbeiterzahl].transkribiere,
                    audio, "en", w_modell, w_geraet
                ): (index, audio)
                for index, audio in enumerate(audios)
            }
            offen = set(futures)
            erledigt = 0
            while offen:
                fertig, offen = wait(offen, timeout=0.5, return_when=FIRST_COMPLETED)
                if not fertig:
                    vergangen = time.time() - beginn
                    pro_datei = vergangen / erledigt if erledigt else 0.0
                    rest = pro_datei * (len(audios) - erledigt) if erledigt else 0.0
                    yield (
                        listen_html(
                            "laeuft", f"{arbeiterzahl} Whisper-Arbeiter transkribieren …",
                            erledigt, len(audios), fehlerzahl, vergangen, rest, pro_datei
                        ),
                        None, None,
                    )
                    continue
                for future in fertig:
                    erledigt += 1
                    index, audio = futures[future]
                    try:
                        antwort = future.result()
                        transkript = str(antwort.get("text", "") or "").strip()
                        treffer, rating = listengenerator.bester_treffer(transkript, en)
                        if treffer is None:
                            raise RuntimeError("kein englischer Texttreffer")
                        sicher = rating >= minimum
                        if not sicher:
                            unsicher_anzahl += 1
                        if sicher or bool(unsichere):
                            deutsch = de_index.get(
                                listengenerator.id_schluessel(treffer.identifier)
                            )
                            deutscher_text = deutsch.text if deutsch else ""
                            if not deutsch:
                                ohne_de += 1
                            zeilen_nach_index[index] = (
                                str(audio.resolve()), treffer.text, deutscher_text
                            )
                    except Exception as fehler:
                        fehlerzahl += 1
                        # Der Audiopfad darf bei einem Whisper-Fehler nicht aus der
                        # Projektliste verschwinden. Leere Texte machen die Zeile
                        # sichtbar, aber noch nicht versehentlich stapelfähig.
                        zeilen_nach_index[index] = (str(audio.resolve()), "", "")
                        fehlertext = f"{type(fehler).__name__}: {fehler}"
                        if fehlertext not in fehlertexte and len(fehlertexte) < 10:
                            fehlertexte.append(fehlertext)
                            sag(f"Whisper-Fehler bei {audio.name}: {fehlertext}")
                    vergangen = time.time() - beginn
                    pro_datei = vergangen / erledigt
                    rest = pro_datei * (len(audios) - erledigt)
                    yield (
                        listen_html(
                            "laeuft", audio.name, erledigt, len(audios), fehlerzahl,
                            vergangen, rest, pro_datei
                        ),
                        None, None,
                    )
            sauber_beendet = True
        finally:
            executor.shutdown(wait=sauber_beendet, cancel_futures=not sauber_beendet)
            # Listen dürfen bewusst parallel laufen. Batch-Ratings verwenden
            # danach wieder genau einen Prozess, damit RAM/VRAM frei wird.
            whisper_dienst.POOL.reduzieren()

        zeilen = [zeilen_nach_index[index] for index in sorted(zeilen_nach_index)]
        ziel = listen_basis / time.strftime("omnivoice_liste_%Y-%m-%d_%H-%M-%S.csv")
        try:
            listengenerator.schreibe_csv(zeilen, ziel)
            lookup_ziel = ziel.with_suffix(".lookup.json")
            lookup_temp = lookup_ziel.with_suffix(".lookup.json.tmp")
            lookup_daten = []
            for eintrag in en:
                deutsch = de_index.get(
                    listengenerator.id_schluessel(eintrag.identifier)
                )
                lookup_daten.append({
                    "id": eintrag.identifier,
                    "englisch": eintrag.text,
                    "deutsch": deutsch.text if deutsch else "",
                })
            lookup_temp.write_text(
                json.dumps(lookup_daten, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(lookup_temp, lookup_ziel)
        except Exception as fehler:
            yield (
                listen_html("fehler", str(fehler), len(audios), len(audios),
                            fehlerzahl + 1, time.time() - beginn, 0, 0),
                None, None,
            )
            return
        details = (
            f"{len(zeilen)} CSV-Zeilen · {unsicher_anzahl} unter {minimum:.0f} %"
            f" · {ohne_de} ohne deutschen ID-Treffer"
        )
        if fehlertexte:
            details += f" · erster Fehler: {fehlertexte[0]}"
        yield (
            listen_html("fertig", details, len(audios), len(audios), fehlerzahl,
                        time.time() - beginn, 0, 0),
            str(ziel), str(ziel),
        )

    # ---------------------------------------------- Erweiterte Ansicht
    # Die Knöpfe in der Liste rufen über gr.HTML(server_functions=…) unmittelbar
    # Python auf. Solche Aufrufe laufen am üblichen Ereignisweg vorbei und
    # bekommen deshalb keine Werte der Bedienelemente mit - Bestand und aktuelle
    # Einstellungen liegen darum hier und werden bei jeder Änderung nachgeführt.
    stand = {
        "alle": [], "gefiltert": [], "sichtbar": tabelle.NACHLADEN,
        "wurzel": "", "basis": str(stapel_basis), "csv_pfad": "", "lookup": [],
    }
    regler = {"schritte": int(einst["qualitaet"]), "tempo": float(einst["tempo"]),
              "wie_probe": bool(einst["dauer_von_probe"]),
              "versatz": float(einst["dauer_offset"]), "stille": bool(einst["stille_weg"]),
              "l_modus": str(einst["laut_modus"]), "l_db": float(einst["laut_db"]),
              "autoplay": bool(einst["tab_autoplay"]),
              "whisper_pruefen": bool(einst["whisper_rating"]),
              "whisper_modell": str(einst["whisper_modell"]),
              "whisper_geraet": str(einst["whisper_geraet"]),
              "ersetzungen": str(einst["text_ersetzungen"])}

    def merke_regler(schritte, tempo, wie_probe, versatz, stille, l_modus, l_db, autoplay,
                     w_pruefen, w_modell, w_geraet, ersetzungen):
        regler.update({"schritte": int(schritte), "tempo": float(tempo),
                       "wie_probe": bool(wie_probe), "versatz": float(versatz or 0.0),
                       "stille": bool(stille), "l_modus": str(l_modus or "aus"),
                       "l_db": float(l_db or 0.0), "autoplay": bool(autoplay),
                       "whisper_pruefen": bool(w_pruefen),
                       "whisper_modell": str(w_modell or "medium"),
                       "whisper_geraet": str(w_geraet or "auto"),
                       "ersetzungen": str(ersetzungen or "")})

    def ratings_laden(eintraege):
        for eintrag in eintraege:
            tabelle.setze_bewertung(
                eintrag, bewertungen.hole(eintrag.ziel, eintrag.deutsch)
            )

    def zeichne_liste(meldung: str = "") -> tuple:
        return (tabelle.stati_html(stand["alle"], stand["gefiltert"]),
                tabelle.tabelle_html(stand["gefiltert"], stand["sichtbar"], meldung))

    def aktive_liste_schreiben() -> None:
        pfad_text = str(stand.get("csv_pfad", "") or "")
        if not pfad_text:
            raise RuntimeError("Kein aktiver CSV-Pfad.")
        pfad = Path(pfad_text)
        temporaer = pfad.with_suffix(pfad.suffix + ".ize.tmp")
        try:
            with open(temporaer, "w", encoding="utf-8-sig", newline="") as datei:
                schreiber = csv.writer(datei, delimiter=";")
                for eintrag in stand["alle"]:
                    schreiber.writerow(
                        [str(eintrag.quelle), eintrag.englisch, eintrag.deutsch]
                    )
            os.replace(temporaer, pfad)
        finally:
            try:
                temporaer.unlink()
            except OSError:
                pass

    def lookup_laden(csv_pfad: str) -> list[dict]:
        name = Path(csv_pfad).with_suffix(".lookup.json").name
        kandidaten = [Path(csv_pfad).with_suffix(".lookup.json"), listen_basis / name]
        for kandidat in kandidaten:
            try:
                daten = json.loads(kandidat.read_text(encoding="utf-8"))
                if isinstance(daten, list):
                    ergebnis = []
                    for wert in daten:
                        if not isinstance(wert, dict):
                            continue
                        ergebnis.append({
                            "id": str(wert.get("id", "") or ""),
                            "englisch": str(wert.get("englisch", "") or ""),
                            "deutsch": str(wert.get("deutsch", "") or ""),
                        })
                    if ergebnis:
                        return ergebnis
            except Exception:
                continue
        return [
            {"id": "", "englisch": eintrag.englisch, "deutsch": eintrag.deutsch}
            for eintrag in stand["alle"]
        ]

    def liste_filtern(suche, feld, zustand, sortierung, rating_filter):
        stand["gefiltert"] = tabelle.filtere(
            stand["alle"], suche, feld, zustand, sortierung, rating_filter
        )
        stand["sichtbar"] = tabelle.NACHLADEN
        return zeichne_liste()

    def liste_einlesen(csv_datei, wurzel_wert, ziel_wert, suche, feld, zustand, sortierung,
                       rating_filter):
        if not csv_datei:
            stand["alle"], stand["gefiltert"] = [], []
            stand["csv_pfad"], stand["lookup"] = "", []
            return zeichne_liste("Bitte oben zuerst eine CSV-Liste auswählen.")
        pfad = csv_datei if isinstance(csv_datei, str) else getattr(csv_datei, "name", "")
        try:
            zeilen = lies_csv(pfad)
        except Exception as fehler:
            stand["alle"], stand["gefiltert"] = [], []
            stand["csv_pfad"], stand["lookup"] = "", []
            return zeichne_liste(f"Die Liste ließ sich nicht lesen: {fehler}")

        quellen = [loese_quelle(z[0], wurzel_wert) for z in zeilen if z and z[0]]
        genutzte_wurzel = (Path(wurzel_wert.strip()) if wurzel_wert.strip()
                           else erkenne_wurzel(quellen))
        basis = Path(ziel_wert.strip()) if ziel_wert.strip() else stapel_basis
        beginn = time.time()
        stand["alle"] = tabelle.baue_eintraege(zeilen, genutzte_wurzel, basis,
                                               loese_quelle, zielpfad)
        ratings_laden(stand["alle"])
        stand["wurzel"], stand["basis"] = str(genutzte_wurzel), str(basis)
        stand["csv_pfad"] = str(Path(pfad))
        stand["lookup"] = lookup_laden(pfad)
        stand["gefiltert"] = tabelle.filtere(
            stand["alle"], suche, feld, zustand, sortierung, rating_filter
        )
        stand["sichtbar"] = tabelle.NACHLADEN
        return zeichne_liste(f"{len(stand['alle'])} Zeilen eingelesen in "
                             f"{dauer_text(time.time() - beginn)} · "
                             f"Projektstart {genutzte_wurzel}")

    def liste_auffrischen(suche, feld, zustand, sortierung, rating_filter):
        """Dateien neu einlesen - nach einem Stapel oder auf Knopfdruck."""
        for eintrag in stand["alle"]:
            tabelle.aktualisiere(eintrag)
        ratings_laden(stand["alle"])
        stand["gefiltert"] = tabelle.filtere(
            stand["alle"], suche, feld, zustand, sortierung, rating_filter
        )
        return zeichne_liste("Stand aufgefrischt." if stand["alle"] else "")

    def stapel_gefiltert(ueberspringen, arbeiter, bericht, wurzel_wert, ziel_wert):
        """Erzeugt genau die Zeilen, die gerade im Filter stehen."""
        eintraege = list(stand["gefiltert"])
        if not eintraege:
            yield (batch_html("fehler", "kein Eintrag im Filter", 0, 0, 0, 0, 0, 0, 0),
                   "Im Filter steht keine Zeile. Bitte zuerst die Liste einlesen.", None)
            return
        # Der Stapel arbeitet mit einer Liste - also eine Zwischendatei nur mit
        # den gefilterten Zeilen. Ziele bleiben dadurch garantiert dieselben.
        zwischendatei = (Path(tempfile.gettempdir())
                         / f"ize_auswahl_{time.strftime('%H%M%S')}.csv")
        try:
            with open(zwischendatei, "w", encoding="utf-8-sig", newline="") as datei:
                schreiber = csv.writer(datei, delimiter=";")
                for eintrag in eintraege:
                    schreiber.writerow([str(eintrag.quelle), eintrag.englisch, eintrag.deutsch])
            yield from stapel_durchlauf(
                str(zwischendatei), stand["wurzel"] or wurzel_wert,
                stand["basis"] or ziel_wert, ueberspringen, regler["schritte"],
                regler["tempo"], stapel_basis, arbeiter, regler["wie_probe"], bericht,
                klangwerte(regler["versatz"], regler["stille"], regler["l_modus"],
                           regler["l_db"], regler["ersetzungen"]), regler["whisper_pruefen"],
                regler["whisper_modell"], regler["whisper_geraet"], bewertungen)
        finally:
            try:
                zwischendatei.unlink()
            except OSError:
                pass

    # -- Aufrufe aus der Liste heraus (server_functions) -----------
    def zeile_editor(daten):
        try:
            nummer = int((daten or {}).get("nr", 0))
        except (TypeError, ValueError, AttributeError):
            return {"fehler": "Ungültige Zeile."}
        eintrag = next((e for e in stand["alle"] if e.nummer == nummer), None)
        if eintrag is None:
            return {"fehler": f"Zeile {nummer} wurde nicht gefunden."}
        return {
            "nummer": nummer,
            "englisch": eintrag.englisch,
            "deutsch": eintrag.deutsch,
        }

    def zeile_text_suchen(daten):
        daten = daten or {}
        sprache = "de" if str(daten.get("sprache", "")) == "de" else "en"
        suche = str(daten.get("suche", "") or "").strip()
        klein = suche.casefold()
        kandidaten = []
        gesehen = set()
        for nummer, eintrag in enumerate(stand.get("lookup", []), start=1):
            englisch = str(eintrag.get("englisch", "") or "")
            deutsch = str(eintrag.get("deutsch", "") or "")
            schluessel = (englisch, deutsch)
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            text = deutsch if sprache == "de" else englisch
            if not text.strip():
                continue
            if not suche:
                wert = max(0.0, 100.0 - nummer / 1000.0)
            elif klein in text.casefold():
                wert = 200.0 - text.casefold().find(klein) / 1000.0
            else:
                wert = whisper_dienst.aehnlichkeit(suche, text)
            kandidaten.append((wert, nummer, englisch, deutsch))
        kandidaten.sort(key=lambda wert: (-wert[0], wert[1]))
        return {
            "treffer": [
                {"nummer": nr, "englisch": en, "deutsch": de, "rating": round(wert, 1)}
                for wert, nr, en, de in kandidaten[:40]
            ]
        }

    def zeile_text_speichern(daten):
        daten = daten or {}
        try:
            nummer = int(daten.get("nr", 0))
        except (TypeError, ValueError):
            return {"ok": False, "meldung": "Ungültige Zeile."}
        eintrag = next((e for e in stand["alle"] if e.nummer == nummer), None)
        if eintrag is None:
            return {"ok": False, "meldung": f"Zeile {nummer} wurde nicht gefunden."}
        alt = (eintrag.englisch, eintrag.deutsch, eintrag.rating, eintrag.whisper_text)
        eintrag.englisch = str(daten.get("englisch", "") or "").strip()
        eintrag.deutsch = str(daten.get("deutsch", "") or "").strip()
        tabelle.setze_bewertung(eintrag, None)
        try:
            aktive_liste_schreiben()
        except Exception as fehler:
            eintrag.englisch, eintrag.deutsch, eintrag.rating, eintrag.whisper_text = alt
            return {"ok": False, "meldung": f"CSV konnte nicht gespeichert werden: {fehler}"}
        return {
            "ok": True,
            "zeile": tabelle.zeile_html(eintrag),
            "meldung": (
                f"Zeile {nummer}: Texte gespeichert. Ein vorhandenes Rating wurde "
                "zurückgesetzt und wird bei der nächsten Erzeugung neu berechnet."
            ),
        }

    def zeile_neu(daten):
        """Eine einzelne Zeile neu erzeugen und die fertige Tabellenzeile zurückgeben."""
        try:
            nummer = int((daten or {}).get("nr", 0))
        except (TypeError, ValueError, AttributeError):
            return {"ok": False, "meldung": "Ungültige Zeile."}
        eintrag = next((e for e in stand["alle"] if e.nummer == nummer), None)
        if eintrag is None:
            return {"ok": False, "meldung": f"Zeile {nummer} nicht gefunden."}
        if STAPEL_LAEUFT.is_set():
            return {"ok": False, "zeile": tabelle.zeile_html(eintrag),
                    "meldung": "Es läuft gerade ein Stapel – einzelne Zeilen bitte danach."}
        if not eintrag.machbar:
            return {"ok": False, "zeile": tabelle.zeile_html(eintrag),
                    "meldung": "Für diese Zeile fehlt die Audiodatei oder der deutsche Text."}

        try:
            modell_deutsch = ersetze_text(eintrag.deutsch, regler["ersetzungen"])
            modell_englisch = ersetze_text(eintrag.englisch, regler["ersetzungen"])
        except ValueError as fehler:
            return {"ok": False, "zeile": tabelle.zeile_html(eintrag),
                    "meldung": f"Globale Textersetzungen sind ungültig: {fehler}"}
        auftrag = {"id": nummer, "text": modell_deutsch, "ref_audio": str(eintrag.quelle),
                   "ref_text": modell_englisch, "num_step": regler["schritte"],
                   "speed": regler["tempo"], "ziel": str(eintrag.ziel),
                   "dauer_von_probe": regler["wie_probe"]}
        auftrag.update(klangwerte(regler["versatz"], regler["stille"],
                                  regler["l_modus"], regler["l_db"],
                                  regler["ersetzungen"]))
        ergebnis = fuehre_auftrag_aus(auftrag)
        tabelle.aktualisiere(eintrag)
        if not ergebnis.get("ok"):
            return {"ok": False, "zeile": tabelle.zeile_html(eintrag),
                    "meldung": f"Zeile {nummer} ({eintrag.name}): {ergebnis.get('fehler')}"}
        rating_hinweis = ""
        # Die direkten Tabellenknöpfe »erzeugen«/»neu« bewerten immer sofort.
        # Das Batch-Häkchen steuert nur den automatischen Check eines ganzen Laufs.
        if whisper_dienst.DIENST.verfuegbar():
            try:
                antwort = whisper_dienst.DIENST.transkribiere(
                    eintrag.ziel, sprache="de", modell=regler["whisper_modell"],
                    geraet=regler["whisper_geraet"]
                )
                transkript = str(antwort.get("text", "") or "").strip()
                rating = whisper_dienst.aehnlichkeit(eintrag.deutsch, transkript)
                bewertungen.setze(
                    eintrag.ziel, eintrag.deutsch, rating, transkript,
                    regler["whisper_modell"], str(antwort.get("geraet", "")),
                )
                ratings_laden([eintrag])
                rating_hinweis = f" · Whisper-Rating {rating:.1f} %"
            except Exception as fehler:
                rating_hinweis = f" · Whisper-Prüfung fehlgeschlagen: {fehler}"
        korrektur = float(ergebnis.get("korrektur", 0.0))
        hinweis = ""
        if abs(korrektur) > 0.02:
            hinweis = (f" · um {dauer_text(abs(korrektur))} "
                       + ("gekürzt" if korrektur > 0 else "mit Stille aufgefüllt"))
        return {
            "ok": True,
            "zeile": tabelle.zeile_html(eintrag),
            "ton": tabelle.daten_uri(eintrag.ziel) if regler["autoplay"] else "",
            "meldung": (f"Zeile {nummer} · {eintrag.name} neu erzeugt in "
                        f"{dauer_text(ergebnis.get('sekunden', 0))} · "
                        f"Länge {dauer_text(eintrag.dauer_de)} "
                        f"(englisch {dauer_text(eintrag.dauer_en)}){hinweis}{rating_hinweis}"),
        }

    def zeile_ton(daten):
        """Wellenform angeklickt: Datei und Startzeit für den Browser."""
        daten = daten or {}
        try:
            nummer = int(daten.get("nr", 0))
            anteil = max(0.0, min(1.0, float(daten.get("anteil", 0.0))))
        except (TypeError, ValueError):
            return {"fehler": "Ungültige Angabe."}
        welche = "en" if str(daten.get("welche")) == "en" else "de"
        eintrag = next((e for e in stand["alle"] if e.nummer == nummer), None)
        if eintrag is None:
            return {"fehler": "Zeile nicht gefunden."}
        pfad = eintrag.quelle if welche == "en" else eintrag.ziel
        laenge = eintrag.dauer_en if welche == "en" else eintrag.dauer_de
        adresse = tabelle.daten_uri(pfad)
        if not adresse:
            return {"fehler": f"{pfad.name} lässt sich nicht abspielen (fehlt oder zu groß)."}
        return {"uri": adresse, "start": round(anteil * laenge, 3), "name": pfad.name,
                "meldung": f"{pfad.name} ab {dauer_text(anteil * laenge)}"}

    def zeilen_nachladen(daten):
        """Beim Scrollen: die nächsten Zeilen liefern."""
        try:
            ab = int((daten or {}).get("ab", 0))
        except (TypeError, ValueError):
            ab = 0
        bis = min(ab + tabelle.NACHLADEN, len(stand["gefiltert"]))
        stand["sichtbar"] = max(stand["sichtbar"], bis)
        return {"zeilen": tabelle.zeilen_html(stand["gefiltert"], ab, bis),
                "ab": bis, "rest": max(0, len(stand["gefiltert"]) - bis)}

    # ---------------------------------------------- Auslastungsanzeige
    def monitor_aktualisieren():
        return messwerte.monitor_html(MOTOR.geraetename, True)

    def monitor_umschalten(an):
        import gradio as gr

        if an:
            messwerte.starten()
        return (gr.Timer(active=bool(an)),
                messwerte.monitor_html(MOTOR.geraetename, bool(an)))

    # ---------------------------------------------- Arbeiter verwalten
    def arbeiter_starten(anzahl):
        anzahl = max(1, int(anzahl))
        if anzahl <= 1:
            VERWALTUNG.stoppen()
            yield arbeiter_zustand_html(
                "Bei einem Arbeiter wird nichts zusätzlich gestartet – das ist gewollt.")
            return
        betrieb = VERWALTUNG.betrieb(anzahl)
        wartete = time.time()
        while betrieb.bereit_anzahl() < betrieb.anzahl and betrieb.lebende() > 0:
            yield arbeiter_zustand_html(f"läuft seit {dauer_text(time.time() - wartete)}")
            time.sleep(0.5)
        yield arbeiter_zustand_html(
            f"bereit nach {dauer_text(time.time() - wartete)}" if betrieb.lebende()
            else "Es konnte kein Arbeiter gestartet werden – siehe Protokoll im Studio.")

    def arbeiter_stoppen():
        VERWALTUNG.stoppen()
        return arbeiter_zustand_html("Der Grafikspeicher der Arbeiter ist wieder frei.")

    def einstellungen_speichern(anzahl, qualitaet, sprechtempo, wurzel_wert, ausgabe_wert,
                                ueberspringen_wert, wie_probe_wert, monitor_wert,
                                ton_wert, hinweis_wert, blinken_wert, bericht_wert,
                                autoplay_wert, versatz, stille, l_modus, l_db,
                                tab_autoplay, whisper_rating, whisper_modell,
                                whisper_geraet, whisper_minimum, whisper_arbeiter,
                                ersetzungen, theme):
        try:
            parse_ersetzungen(ersetzungen)
        except ValueError as fehler:
            return f"❌  Einstellungen nicht gespeichert: {fehler}"
        return schreibe_einstellungen(einstellungen_pfad, {
            "arbeiter": int(anzahl), "qualitaet": int(qualitaet), "tempo": float(sprechtempo),
            "wurzel": wurzel_wert or "", "ausgabe": ausgabe_wert or "",
            "ueberspringen": bool(ueberspringen_wert),
            "dauer_von_probe": bool(wie_probe_wert), "monitor": bool(monitor_wert),
            "ton": bool(ton_wert), "hinweis": bool(hinweis_wert),
            "blinken": bool(blinken_wert), "bericht": bool(bericht_wert),
            "autoplay": bool(autoplay_wert),
            "dauer_offset": float(versatz or 0.0), "stille_weg": bool(stille),
            "laut_modus": str(l_modus or "aus"), "laut_db": float(l_db or 0.0),
            "tab_autoplay": bool(tab_autoplay),
            "whisper_rating": bool(whisper_rating),
            "whisper_modell": str(whisper_modell or "medium"),
            "whisper_geraet": str(whisper_geraet or "Automatisch (NVIDIA, sonst CPU)"),
            "whisper_minimum": int(whisper_minimum or 55),
            "whisper_arbeiter": max(1, min(8, int(whisper_arbeiter or 1))),
            "text_ersetzungen": str(ersetzungen or ""),
            "theme": normalisiere_theme(theme),
        })

    def theme_sofort_speichern(theme):
        theme = normalisiere_theme(theme)
        werte = lies_einstellungen(einstellungen_pfad)
        werte["theme"] = theme
        ergebnis = schreibe_einstellungen(einstellungen_pfad, werte)
        if ergebnis.startswith("✅"):
            return f"✅  Theme »{theme}« sofort angewendet und gespeichert."
        return ergebnis

    def theme_aktuell(_daten=None):
        theme = normalisiere_theme(
            lies_einstellungen(einstellungen_pfad).get("theme", "Default")
        )
        return {"theme": theme}

    def ordner_oeffnen(pfad_text=""):
        ziel = Path(pfad_text.strip()) if pfad_text.strip() else ausgabe_ordner
        try:
            ziel.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(ziel))
            return f"📂  Ordner geöffnet: {ziel}"
        except Exception as fehler:
            return f"Ordner: {ziel}  ({fehler})"

    # ---------------------------------------------- Aufbau
    blocks_args = {"title": "OmniVoice Studio · iZE", "analytics_enabled": False, "fill_width": True}
    if gradio_hauptversion() < 6:
        blocks_args["css"] = CSS + themen_css(theme_name)
        thema = baue_thema(theme_name)
        if thema is not None:
            blocks_args["theme"] = thema

    with gr.Blocks(**passende_argumente(gr.Blocks.__init__, **blocks_args)) as seite:
        theme_kopf = mach(
            gr.HTML,
            value=(
                f"<span id='ize-theme-marker' data-ize-theme='{html.escape(theme_name)}' "
                f"hidden></span>{KOPF_HTML}"
            ),
            padding=False,
            container=False,
        )

        # Gilt für alle Reiter, deshalb ganz oben statt irgendwo unten.
        with gr.Accordion("⚙️  Erzeugung und Klang – gilt überall "
                          "(Qualität, Tempo, Länge, Lautstärke)", open=False):
            with gr.Row():
                schritte = mach(gr.Slider, minimum=8, maximum=64, value=int(einst["qualitaet"]),
                                step=1, label="Qualitätsstufe",
                                info="mehr = besser und langsamer")
                tempo = mach(gr.Slider, minimum=0.5, maximum=1.5, value=float(einst["tempo"]),
                             step=0.05, label="Sprechtempo", info="1,0 = normal")
                laenge = mach(gr.Slider, minimum=0, maximum=60, value=0, step=1,
                              label="Feste Länge in Sekunden",
                              info="0 = automatisch. Nur beim Klonen; »so lang wie die "
                                   "Aufnahme« hat Vorrang.")
                dauer_offset = mach(
                    gr.Slider, minimum=-5.0, maximum=5.0,
                    value=float(einst["dauer_offset"]), step=0.1,
                    label="Versatz zur Länge in Sekunden",
                    info="Wirkt zusammen mit »so lang wie die Aufnahme«. "
                         "Minus = knapper, Plus = mehr Luft.")
            with gr.Row():
                laut_modus = mach(
                    gr.Radio, choices=list(LAUTSTAERKE_WAHL.keys()),
                    value=(str(einst["laut_modus"]) if str(einst["laut_modus"])
                           in LAUTSTAERKE_WAHL else "aus"),
                    label="Lautstärke anpassen",
                    info="»angleichen« bringt die Aufnahme auf die Lautheit der Vorlage.")
                laut_db = mach(
                    gr.Slider, minimum=-12.0, maximum=12.0, value=float(einst["laut_db"]),
                    step=0.5, label="Verstärkung in Dezibel",
                    info="nur bei »feste Verstärkung«")
                stille_weg = mach(
                    gr.Checkbox, value=bool(einst["stille_weg"]),
                    label="Stille am Anfang entfernen",
                    info="Schneidet die Ruhe vor dem ersten Wort weg.")
            text_ersetzungen = mach(
                gr.Textbox, value=str(einst["text_ersetzungen"]), lines=4,
                label="Globale Textersetzungen vor der Spracherzeugung",
                info=r"Eine Regel je Zeile: Suchen => Ersetzen. \r, \n und \t werden "
                     r"verstanden; leere rechte Seite oder \"\" löscht den Suchtext. "
                     r"Beispiel: ehrgeiz => ehrgeitz"
            )

        with gr.Tabs():
            # ------------------------------------------------ klonen
            with gr.Tab("🎤  Stimme klonen"):
                gr.Markdown(
                    "**So geht's:** eine kurze Sprachprobe hochladen oder direkt aufnehmen, "
                    "rechts den Text eintippen, auf *Sprechen lassen* klicken."
                )
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        probe = audio_eingabe(label="1 · Sprachprobe (5 bis 15 Sekunden)")
                        probe_text = gr.Textbox(
                            label="2 · Was wird in der Probe gesagt? (optional)",
                            placeholder="Leer lassen – dann hört das Modell selbst hin.",
                            lines=2,
                        )
                        gr.Markdown(
                            "<div class='ize-tipp'>"
                            "· 5 bis 15 Sekunden reichen völlig aus<br>"
                            "· sauber aufgenommen, ohne Hall, ohne Musik im Hintergrund<br>"
                            "· nur eine Person sprechend<br>"
                            "· der Text darf in einer anderen Sprache sein als die Probe"
                            "</div>"
                        )
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        text_klon = gr.Textbox(label="3 · Dieser Text wird gesprochen",
                                               value=BEISPIEL_TEXT, lines=7)
                        klon_wie_probe = mach(
                            gr.Checkbox, value=bool(einst["dauer_von_probe"]),
                            label="Ausgabe genauso lang wie die Sprachprobe",
                            info="Die Aufnahme bekommt exakt die Länge der Sprachprobe. "
                                 "Gut fürs Vertonen, wenn die Zeile ins selbe Zeitfenster passen muss.")
                        klon_autoplay = mach(
                            gr.Checkbox, value=bool(einst["autoplay"]),
                            label="Ergebnis sofort abspielen",
                            info="Spielt die fertige Aufnahme automatisch ab – praktisch "
                                 "beim schnellen Ausprobieren mehrerer Texte.")
                        los_klon = gr.Button("▶  Sprechen lassen", variant="primary", elem_id="ize-los")
                with gr.Row():
                    with gr.Column(scale=2, elem_classes="ize-karte"):
                        ergebnis_klon = audio_ausgabe()
                        autoplay_signal = gr.Textbox(
                            value="", visible=False, elem_id="ize-autoplay-signal"
                        )
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        bericht_klon = gr.Markdown("Noch nichts erzeugt.")
                        gr.Button("📂  Ergebnis-Ordner öffnen").click(
                            lambda: ordner_oeffnen(""), inputs=None, outputs=[bericht_klon])

            # ------------------------------------------------ Überraschung
            with gr.Tab("🎲  Überraschung"):
                gr.Markdown("Ohne Vorgabe: Das Modell sucht sich selbst eine Stimme aus. "
                            "Gut zum schnellen Ausprobieren.")
                with gr.Column(elem_classes="ize-karte"):
                    text_zufall = gr.Textbox(label="Dieser Text wird gesprochen",
                                             value=BEISPIEL_TEXT, lines=5)
                    los_zufall = gr.Button("▶  Sprechen lassen", variant="primary", elem_id="ize-los")
                with gr.Row():
                    with gr.Column(scale=2, elem_classes="ize-karte"):
                        ergebnis_zufall = audio_ausgabe()
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        bericht_zufall = gr.Markdown("Noch nichts erzeugt.")

            # ------------------------------------------------ Listengenerator
            with gr.Tab("🧾  Liste erzeugen"):
                gr.Markdown(
                    "**Audioordner → Whisper → englischer Fuzzy-Treffer → deutsche ID → CSV.**  "
                    "Die fertige Liste wird automatisch in den Stapel-Tab übernommen. "
                    "Der vollständige absolute Audiopfad bleibt in der ersten Spalte erhalten."
                )
                with gr.Row():
                    audio_ordner = mach(
                        gr.Textbox, label="1 · Ordner mit englischen Audiodateien",
                        lines=1, scale=2,
                        placeholder=r"z. B. C:\modding\elden ring\audios"
                    )
                    englische_liste = mach(
                        gr.File, label="2 · Englische Lookup-Liste",
                        file_types=[".txt", ".csv", ".json", ".ini"], type="filepath", scale=1
                    )
                    deutsche_liste = mach(
                        gr.File, label="3 · Deutsche Lookup-Liste",
                        file_types=[".txt", ".csv", ".json", ".ini"], type="filepath", scale=1
                    )
                with gr.Row():
                    listen_unsichere = mach(
                        gr.Checkbox, value=True,
                        label="Treffer unter dem Mindest-Rating trotzdem übernehmen",
                        info="Aus: unsichere Zeilen werden ausgelassen. Im Status steht ihre Anzahl."
                    )
                    listen_arbeiter = mach(
                        gr.Slider, minimum=1, maximum=8,
                        value=max(1, min(8, int(einst["whisper_arbeiter"]))),
                        step=1, label="Whisper-Arbeiter",
                        info="Nur für diesen Listengenerator. Jeder Arbeiter lädt ein eigenes "
                             "Modell; danach werden zusätzliche Arbeiter automatisch beendet."
                    )

                def parser_felder(titel):
                    with gr.Accordion(titel, open=False):
                        with gr.Row():
                            modus = mach(
                                gr.Dropdown, choices=listengenerator.MODI,
                                value="Automatisch", label="Aufbau"
                            )
                            trenner = mach(
                                gr.Textbox, value="=", label="Trennzeichen",
                                info=r"z. B. =, ;, | oder \t"
                            )
                            id_spalte = mach(
                                gr.Number, value=1, precision=0, label="ID-Spalte (ab 1)"
                            )
                            text_spalte = mach(
                                gr.Number, value=2, precision=0, label="Text-Spalte (ab 1)"
                            )
                        regex = mach(
                            gr.Textbox, value=listengenerator.STANDARD_REGEX,
                            label="Regulärer Ausdruck",
                            info="Benannte Gruppen (?P<id>…) und (?P<text>…) oder Gruppe 1/2.",
                            lines=2,
                        )
                    return [modus, trenner, id_spalte, text_spalte, regex]

                parser_en = parser_felder("🔧  Aufbau der englischen Lookup-Liste")
                parser_de = parser_felder("🔧  Aufbau der deutschen Lookup-Liste")
                parser_felder_alle = parser_en + parser_de
                with gr.Row():
                    listen_vorschau_knopf = gr.Button("🔍  Listen prüfen", scale=1)
                    listen_start = gr.Button(
                        "▶  CSV erzeugen", variant="primary", scale=2
                    )
                    listen_stopp = gr.Button("⏹  Anhalten", variant="stop", scale=1)
                listen_vorschau_text = gr.Markdown("")
                listen_anzeige = gr.HTML(LEERE_LISTEN_ANZEIGE)
                listen_datei = mach(
                    gr.File, label="Fertige CSV-Liste", interactive=False
                )
                with gr.Accordion("Wie die Zuordnung funktioniert", open=False):
                    gr.Markdown(
                        "Whisper transkribiert jede englische Aufnahme. Der erkannte Text wird "
                        "unscharf mit allen englischen Lookup-Texten verglichen. Die ID des besten "
                        "Treffers sucht anschließend den deutschen Text. Ausgabe ohne Kopfzeile:\n\n"
                        "`vollständiger\\pfad\\audio.wav;English lookup text;Deutscher Lookup-Text`\n\n"
                        "Bei **Automatisch** werden JSON, `ID=Text` und typische Spaltentrenner "
                        "erkannt. Für Sonderformate stehen getrennte Einstellungen und Regex für "
                        "beide Sprachlisten bereit."
                    )

            # ------------------------------------------------ Stapel
            with gr.Tab("📦  Stapel (ganzes Projekt)"):
                with gr.Row():
                    csv_datei = mach(gr.File, label="CSV-Liste", file_types=[".csv", ".txt"],
                                     type="filepath", scale=1, height=118)
                    with gr.Column(scale=3):
                        with gr.Row():
                            wurzel = mach(
                                gr.Textbox, label="Projektstart (Wurzelordner)",
                                value=einst["wurzel"], lines=1, scale=1,
                                placeholder=r"z. B. C:\Projekte  ·  leer = automatisch erkennen")
                            ziel_basis = mach(gr.Textbox, label="Ausgabeordner", lines=1, scale=1,
                                              value=einst["ausgabe"] or str(stapel_basis))
                        with gr.Row():
                            ueberspringen = mach(
                                gr.Checkbox, value=bool(einst["ueberspringen"]),
                                label="Vorhandene überspringen",
                                info="aus = überschreiben")
                            stapel_wie_probe = mach(
                                gr.Checkbox, value=bool(einst["dauer_von_probe"]),
                                label="So lang wie das Original",
                                info="passt ins selbe Zeitfenster")
                            bericht_an = mach(
                                gr.Checkbox, value=bool(einst["bericht"]),
                                label="Bericht als CSV",
                                info="Status je Zeile im Ausgabeordner")
                            whisper_rating_an = mach(
                                gr.Checkbox, value=bool(einst["whisper_rating"]),
                                label="Mit Whisper prüfen",
                                info="Aus = kein Whisper-Arbeiter. An = genau ein Arbeiter nach "
                                     "der Erzeugung; transkribiert und berechnet das Rating.")
                            stapel_arbeiter = mach(
                                gr.Slider, minimum=1, maximum=8, value=int(einst["arbeiter"]),
                                step=1, label="Arbeiter",
                                info=f"1 = Hauptprozess · empfohlen bis {empfehlung}")
                with gr.Row():
                    pruefen_knopf = gr.Button("🔍  Liste prüfen", scale=1)
                    los_stapel = gr.Button("▶  Stapel starten", variant="primary",
                                           elem_id="ize-stapel-los", scale=2)
                    stopp_stapel = gr.Button("⏹  Anhalten", variant="stop", scale=1)
                pruef_bericht = gr.Markdown("")
                stapel_anzeige = gr.HTML(LEERE_ANZEIGE)

                with gr.Accordion("📄  Format der Liste", open=False):
                    gr.Markdown(
                        "Drei Spalten, getrennt durch Semikolon oder Komma:\n\n"
                        "`englische Audiodatei ; englischer Text ; deutscher Text`\n\n"
                        f"Beispiel: `{BEISPIEL_CSV}`\n\n"
                        "Der mittlere Text ist optional – fehlt er, hört OmniVoice die Aufnahme "
                        "selbst ab. Eine Kopfzeile darf drin sein.\n\n"
                        "Der **Wurzelordner** sagt, wo das Projekt anfängt: Der Teil des Pfades "
                        "unterhalb davon wird im Ausgabeordner nachgebaut. Beispiel: Wurzel "
                        r"`C:\Projekte` und Datei `C:\Projekte\habitat\audio\stimme.wav` "
                        r"→ Ausgabe `batch\habitat\audio\stimme.wav`."
                    )

                # ------------------------------------------ Liste
                gr.HTML("<div style='margin:14px 0 2px 0;font-size:11px;font-weight:800;"
                        "letter-spacing:.22em;color:#4d9bff'>ALLE ZEILEN IM ÜBERBLICK</div>")
                with gr.Row():
                    tabelle_laden_knopf = gr.Button("📋  Liste einlesen", variant="primary",
                                                    scale=1)
                    tabelle_frisch_knopf = gr.Button("🔄  Auffrischen", scale=1)
                    los_gefiltert = gr.Button("⚡  Gefilterte erzeugen", variant="primary",
                                              scale=2)
                    tabelle_autoplay = mach(gr.Checkbox, value=bool(einst["tab_autoplay"]),
                                            label="nach dem Erzeugen abspielen", scale=1)
                with gr.Row():
                    tabelle_suche = mach(gr.Textbox, label="Suchen", lines=1, scale=3,
                                         placeholder="Text oder Muster, z. B. *falle*")
                    tabelle_feld = mach(gr.Dropdown, choices=tabelle.SUCHFELDER,
                                        value="alles", label="Suchen in", scale=1)
                    tabelle_zustand = mach(gr.Dropdown, choices=tabelle.ZUSTAENDE,
                                           value="alle", label="Zustand", scale=1)
                    tabelle_sortierung = mach(gr.Dropdown, choices=tabelle.SORTIERUNGEN,
                                              value="Zeile", label="Sortierung", scale=1)
                    tabelle_rating = mach(
                        gr.Dropdown, choices=tabelle.RATING_FILTER,
                        value="alle Ratings", label="Rating", scale=1
                    )
                tabelle_stati = gr.HTML(tabelle.stati_html([], []))
                tabelle_gitter = mach(
                    gr.HTML, value=tabelle.tabelle_html([]),
                    css_template=tabelle.CSS_LISTE, js_on_load=LISTE_JS,
                    server_functions=[
                        zeile_neu, zeile_ton, zeilen_nachladen,
                        zeile_editor, zeile_text_suchen, zeile_text_speichern,
                    ],
                    padding=False, container=False)

                with gr.Accordion("📜  Protokoll und Bericht", open=False):
                    with gr.Row():
                        with gr.Column(scale=3):
                            stapel_protokoll = mach(gr.Textbox, label="Protokoll", lines=14,
                                                    max_lines=14, autoscroll=True,
                                                    show_copy_button=True)
                        with gr.Column(scale=1, elem_classes="ize-karte"):
                            bericht_datei_aus = mach(gr.File, label="Bericht (CSV)")
                            gr.Button("📂  Ausgabeordner öffnen").click(
                                ordner_oeffnen, inputs=[ziel_basis], outputs=[pruef_bericht])

            # ------------------------------------------------ Einstellungen
            with gr.Tab("⚙️  Einstellungen"):
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        gr.Markdown(
                            "### Arbeiter\n"
                            "Jeder Arbeiter ist ein **eigener OmniVoice-Prozess** mit einem "
                            "eigenen Modell im Grafikspeicher. Der Stapelbetrieb verteilt die "
                            "Dateien darauf und rechnet dadurch wirklich parallel.\n\n"
                            f"· **1 Arbeiter** rechnet im Hauptprozess – kein zusätzlicher Speicher.\n"
                            f"· Jeder weitere Arbeiter braucht grob **3,5 GB** Grafikspeicher.\n"
                            f"· Erkannt: **{komma(MOTOR.vram_gb)} GB** auf {html.escape(MOTOR.geraetename)} "
                            f"→ empfohlen bis **{empfehlung}**.\n\n"
                            "Die Arbeiter starten automatisch beim ersten Stapel und bleiben "
                            "danach bereit. Zum Freigeben des Speichers hier stoppen."
                        )
                        arbeiter_regler = mach(
                            gr.Slider, minimum=1, maximum=8, value=int(einst["arbeiter"]), step=1,
                            label="Anzahl der Arbeiter",
                            info="Gilt für den Stapelbetrieb.")
                        with gr.Row():
                            arbeiter_start_knopf = gr.Button("⚡  Arbeiter starten", variant="primary")
                            arbeiter_stopp_knopf = gr.Button("⏹  Arbeiter stoppen", variant="stop")
                    with gr.Column(scale=1, elem_classes="ize-karte"):
                        arbeiter_anzeige = gr.HTML(arbeiter_zustand_html())
                        gr.Markdown("### Theme")
                        theme_auswahl = mach(
                            gr.Dropdown, choices=THEMEN, value=theme_name,
                            label="Oberflächen-Theme",
                            info="Wird sofort angewendet und automatisch gespeichert."
                        )
                        gr.Markdown("### Whisper und Qualitätsprüfung")
                        whisper_modell = mach(
                            gr.Dropdown, choices=whisper_dienst.MODELLE,
                            value=(str(einst["whisper_modell"])
                                   if str(einst["whisper_modell"]) in whisper_dienst.MODELLE
                                   else "medium"),
                            label="Whisper-Modell",
                            info="medium ist Standard; ein anderes Modell wird beim ersten Einsatz "
                                 "automatisch in den Modell-Cache geladen."
                        )
                        whisper_geraet = mach(
                            gr.Dropdown, choices=list(whisper_dienst.GERAETE),
                            value=(str(einst["whisper_geraet"])
                                   if str(einst["whisper_geraet"]) in whisper_dienst.GERAETE
                                   else "Automatisch (NVIDIA, sonst CPU)"),
                            label="Whisper-Gerät",
                            info="Automatisch nutzt NVIDIA, wenn verfügbar, sonst CPU/INT8."
                        )
                        whisper_minimum = mach(
                            gr.Slider, minimum=0, maximum=100,
                            value=int(einst["whisper_minimum"]), step=1,
                            label="Mindest-Rating für Listen-Treffer",
                            info="Nur relevant, wenn unsichere Treffer nicht übernommen werden."
                        )
                        whisper_stop_knopf = gr.Button("⏹  Whisper-Modell entladen")
                        gr.Markdown("### Anzeige und Benachrichtigung")
                        monitor_an = mach(
                            gr.Checkbox, value=bool(einst["monitor"]),
                            label="Auslastung einblenden",
                            info="Kleines Fenster unten rechts mit Prozessor, Arbeitsspeicher, "
                                 "Grafikkarte und Grafikspeicher – wird alle 2 Sekunden aktualisiert.")
                        ton_an = mach(
                            gr.Checkbox, value=bool(einst["ton"]),
                            label="Signalton, wenn ein Stapel fertig ist",
                            info="Nur im Stapelbetrieb.")
                        hinweis_an = mach(
                            gr.Checkbox, value=bool(einst["hinweis"]),
                            label="Browser-Benachrichtigung, wenn ein Stapel fertig ist",
                            info="Beim Einschalten fragt der Browser einmalig um Erlaubnis.")
                        blinken_an = mach(
                            gr.Checkbox, value=bool(einst["blinken"]),
                            label="Browser-Tab blinken lassen, wenn ein Stapel fertig ist",
                            info="Der Reitertitel wechselt, bis das Fenster wieder im "
                                 "Vordergrund ist. Nur wenn der Tab gerade nicht sichtbar ist.")
                        gr.Markdown(
                            "### Speichern\n"
                            "Alle Einstellungen dieser Seite werden gemerkt und beim nächsten "
                            "Start wieder eingesetzt."
                        )
                        speichern_knopf = gr.Button("💾  Einstellungen speichern")
                        speicher_bericht = gr.Markdown(f"Ablage: `{einstellungen_pfad}`")
                        gr.Markdown(
                            "<div class='ize-tipp'>"
                            f"Gerät: {html.escape(MOTOR.geraetename)} ({MOTOR.dtype_name})<br>"
                            f"Modell: {MODELL}<br>"
                            f"Ergebnisse: {html.escape(str(ausgabe_ordner))}<br>"
                            f"Stapel: {html.escape(str(stapel_basis))}"
                            "</div>"
                        )

        gr.HTML(FUSS_HTML.format(geraet=html.escape(MOTOR.geraetename)))

        # Schwebende Auslastungsanzeige - liegt außerhalb der Reiter und ist
        # damit überall sichtbar.
        if bool(einst["monitor"]):
            messwerte.starten()
        monitor_feld = gr.HTML(messwerte.monitor_html(MOTOR.geraetename, bool(einst["monitor"])))
        monitor_takt = mach(gr.Timer, value=2.0, active=bool(einst["monitor"]))

        # ---------------------------------------------- Verdrahtung
        filterfelder = [
            tabelle_suche, tabelle_feld, tabelle_zustand,
            tabelle_sortierung, tabelle_rating,
        ]

        los_klon.click(
            lambda t, a, rt, s, sp, l, w, ap, v, st, lm, ld, er: lauf(
                t, a, rt, s, sp, l, "klonen", w, ap, v, st, lm, ld, er),
            inputs=[text_klon, probe, probe_text, schritte, tempo, laenge,
                    klon_wie_probe, klon_autoplay, dauer_offset, stille_weg,
                    laut_modus, laut_db, text_ersetzungen],
            outputs=[ergebnis_klon, bericht_klon, autoplay_signal],
            js=AUTOPLAY_VORBEREITEN_JS,
        )
        los_zufall.click(
            lambda t, s, sp, l, st, lm, ld, er: lauf(
                t, None, "", s, sp, l, "zufall", False, False, 0.0, st, lm, ld, er
            ),
            inputs=[
                text_zufall, schritte, tempo, laenge, stille_weg,
                laut_modus, laut_db, text_ersetzungen,
            ],
            outputs=[ergebnis_zufall, bericht_zufall, autoplay_signal],
        )
        autoplay_signal.change(
            None, inputs=[autoplay_signal], outputs=[], js=AUTOPLAY_SIGNAL_JS
        )
        pruefen_knopf.click(stapel_pruefen, inputs=[csv_datei, wurzel, ziel_basis],
                            outputs=[pruef_bericht])
        # Während ein Stapel läuft, sind Prüfen und Starten gesperrt. Freigegeben
        # wird am Ende des Laufs - und beim Anhalten, weil die Kette dann abbricht.
        def knoepfe(aktiv):
            return gr.Button(interactive=aktiv), gr.Button(interactive=aktiv)

        sperre = los_stapel.click(lambda: knoepfe(False), inputs=None,
                                  outputs=[pruefen_knopf, los_stapel])
        stapel_ereignis = sperre.then(
            stapel_lauf,
            inputs=[csv_datei, wurzel, ziel_basis, ueberspringen, schritte, tempo,
                    stapel_arbeiter, stapel_wie_probe, bericht_an,
                    dauer_offset, stille_weg, laut_modus, laut_db,
                    whisper_rating_an, whisper_modell, whisper_geraet,
                    text_ersetzungen],
            outputs=[stapel_anzeige, stapel_protokoll, bericht_datei_aus],
        )
        freigabe = stapel_ereignis.then(lambda: knoepfe(True), inputs=None,
                                        outputs=[pruefen_knopf, los_stapel])
        # Nach dem Stapel die Liste nachziehen, falls sie eingelesen wurde.
        freigabe.then(liste_auffrischen, inputs=filterfelder,
                      outputs=[tabelle_stati, tabelle_gitter])

        # Derselbe Ablauf für »nur die gefilterten Zeilen«.
        sperre_gefiltert = los_gefiltert.click(lambda: knoepfe(False), inputs=None,
                                               outputs=[pruefen_knopf, los_stapel])
        gefiltert_ereignis = sperre_gefiltert.then(
            stapel_gefiltert,
            inputs=[ueberspringen, stapel_arbeiter, bericht_an, wurzel, ziel_basis],
            outputs=[stapel_anzeige, stapel_protokoll, bericht_datei_aus],
        )
        freigabe_gefiltert = gefiltert_ereignis.then(lambda: knoepfe(True), inputs=None,
                                                     outputs=[pruefen_knopf, los_stapel])
        freigabe_gefiltert.then(liste_auffrischen, inputs=filterfelder,
                                outputs=[tabelle_stati, tabelle_gitter])
        try:
            stopp_stapel.click(lambda: knoepfe(True), inputs=None,
                               outputs=[pruefen_knopf, los_stapel],
                               cancels=[stapel_ereignis, gefiltert_ereignis])
        except TypeError:
            stopp_stapel.click(lambda: knoepfe(True), inputs=None,
                               outputs=[pruefen_knopf, los_stapel])

        # Nach dem Stapel: Ton und Browser-Benachrichtigung. Läuft komplett im
        # Browser, deshalb als reine JavaScript-Aktion ohne Python-Funktion.
        try:
            freigabe.then(None,
                          inputs=[ton_an, hinweis_an, blinken_an, stapel_protokoll],
                          outputs=[], js=MELDUNG_JS)
        except Exception as fehler:
            sag(f"Hinweis: Benachrichtigung nicht verfügbar ({fehler}).")
        try:
            hinweis_an.change(None, inputs=[hinweis_an], outputs=[], js=ERLAUBNIS_JS)
        except Exception:
            pass

        # Auslastungsanzeige
        monitor_takt.tick(monitor_aktualisieren, inputs=None, outputs=[monitor_feld])
        monitor_an.change(monitor_umschalten, inputs=[monitor_an],
                          outputs=[monitor_takt, monitor_feld])

        # Beide Regler für die Arbeiterzahl zeigen immer denselben Wert.
        stapel_arbeiter.change(lambda wert: wert, inputs=[stapel_arbeiter],
                               outputs=[arbeiter_regler])
        arbeiter_regler.change(lambda wert: wert, inputs=[arbeiter_regler],
                               outputs=[stapel_arbeiter])
        arbeiter_start_knopf.click(arbeiter_starten, inputs=[arbeiter_regler],
                                   outputs=[arbeiter_anzeige])
        arbeiter_stopp_knopf.click(arbeiter_stoppen, inputs=None, outputs=[arbeiter_anzeige])
        whisper_stop_knopf.click(
            lambda: (whisper_dienst.POOL.stoppen()
                     or "✅  Alle Whisper-Modelle wurden aus dem Speicher entfernt."),
            inputs=None, outputs=[speicher_bericht]
        )
        speichern_knopf.click(
            einstellungen_speichern,
            inputs=[arbeiter_regler, schritte, tempo, wurzel, ziel_basis, ueberspringen,
                    stapel_wie_probe, monitor_an, ton_an, hinweis_an, blinken_an,
                    bericht_an, klon_autoplay, dauer_offset, stille_weg, laut_modus,
                    laut_db, tabelle_autoplay, whisper_rating_an, whisper_modell,
                    whisper_geraet, whisper_minimum, listen_arbeiter,
                    text_ersetzungen, theme_auswahl],
            outputs=[speicher_bericht],
        )
        try:
            theme_auswahl.change(
                None, inputs=[theme_auswahl], outputs=[], js=THEME_WECHSEL_JS
            )
            theme_auswahl.change(
                theme_sofort_speichern,
                inputs=[theme_auswahl],
                outputs=[speicher_bericht],
            )
        except Exception as fehler:
            sag(f"Hinweis: Live-Themewechsel nicht verfügbar ({fehler}).")
        try:
            theme_laden = seite.load(
                lambda: (
                    (
                        f"<span id='ize-theme-marker' "
                        f"data-ize-theme='{html.escape(theme_aktuell({})['theme'])}' "
                        f"hidden></span>{KOPF_HTML}"
                    ),
                    theme_aktuell({})["theme"],
                ),
                inputs=None,
                outputs=[theme_kopf, theme_auswahl],
                queue=False,
            )
        except Exception as fehler:
            sag(f"Hinweis: Gespeichertes Theme konnte beim Laden nicht gesetzt werden ({fehler}).")
        # Beide Häkchen für die Länge zeigen immer dasselbe.
        stapel_wie_probe.change(lambda wert: wert, inputs=[stapel_wie_probe],
                                outputs=[klon_wie_probe])
        klon_wie_probe.change(lambda wert: wert, inputs=[klon_wie_probe],
                              outputs=[stapel_wie_probe])

        # ---------------------------------------------- Listengenerator
        listen_vorschau_knopf.click(
            listen_vorschau,
            inputs=[audio_ordner, englische_liste, deutsche_liste] + parser_felder_alle,
            outputs=[listen_vorschau_text],
        )
        listen_ereignis = listen_start.click(
            liste_generieren,
            inputs=[
                audio_ordner, englische_liste, deutsche_liste, whisper_minimum,
                listen_unsichere, whisper_modell, whisper_geraet, listen_arbeiter,
            ] + parser_felder_alle,
            outputs=[listen_anzeige, listen_datei, csv_datei],
        )
        try:
            listen_stopp.click(
                lambda: (whisper_dienst.POOL.stoppen()
                         or listen_html("abbruch", "angehalten", 0, 0, 0, 0, 0, 0)),
                inputs=None, outputs=[listen_anzeige], cancels=[listen_ereignis]
            )
        except TypeError:
            listen_stopp.click(
                lambda: (whisper_dienst.POOL.stoppen()
                         or listen_html("abbruch", "angehalten", 0, 0, 0, 0, 0, 0)),
                inputs=None, outputs=[listen_anzeige]
            )

        # ---------------------------------------------- Liste
        tabelle_laden_knopf.click(
            liste_einlesen, inputs=[csv_datei, wurzel, ziel_basis] + filterfelder,
            outputs=[tabelle_stati, tabelle_gitter])
        tabelle_frisch_knopf.click(liste_auffrischen, inputs=filterfelder,
                                   outputs=[tabelle_stati, tabelle_gitter])
        for feld in filterfelder:
            feld.change(liste_filtern, inputs=filterfelder,
                        outputs=[tabelle_stati, tabelle_gitter])

        # Die Knöpfe in der Liste rufen Python unmittelbar auf und kennen die
        # Bedienelemente nicht - deshalb deren Werte hier laufend mitschreiben.
        reglerfelder = [schritte, tempo, stapel_wie_probe, dauer_offset, stille_weg,
                        laut_modus, laut_db, tabelle_autoplay, whisper_rating_an,
                        whisper_modell, whisper_geraet, text_ersetzungen]
        for feld in reglerfelder:
            feld.change(merke_regler, inputs=reglerfelder, outputs=[])

    return seite


# ------------------------------------------------------------
# Start
# ------------------------------------------------------------

def main() -> int:
    zerleger = argparse.ArgumentParser(add_help=False)
    zerleger.add_argument("--ip", default="127.0.0.1")
    zerleger.add_argument("--port", type=int, default=7860)
    zerleger.add_argument("--ausgabe", default="")
    zerleger.add_argument("--einstellungen", default="")
    argumente, _rest = zerleger.parse_known_args()

    ausgabe = Path(argumente.ausgabe) if argumente.ausgabe else Path.home() / "OmniVoice"
    einstellungen = (Path(argumente.einstellungen) if argumente.einstellungen
                     else ausgabe / "einstellungen.json")

    try:
        import gradio  # noqa: F401
    except Exception as fehler:
        sag(f"FEHLER: Gradio ist nicht verfügbar ({fehler}).")
        return EXIT_NICHT_STARTBAR

    try:
        MOTOR.laden()
    except Exception as fehler:
        sag("")
        sag(f"FEHLER: Das Sprachmodell ließ sich nicht laden: {type(fehler).__name__}: {fehler}")
        traceback.print_exc()
        return EXIT_NICHT_STARTBAR

    try:
        seite = baue_oberflaeche(ausgabe, einstellungen)
    except Exception as fehler:
        sag("")
        sag(f"FEHLER: Die deutsche Oberfläche ließ sich nicht aufbauen: "
            f"{type(fehler).__name__}: {fehler}")
        traceback.print_exc()
        return EXIT_NICHT_STARTBAR

    sag("")
    sag(f"Ergebnisse landen in: {ausgabe}")
    sag(f"Stapel-Ausgaben in  : {ausgabe / 'batch'}")
    sag(f"Einstellungen       : {einstellungen}")
    sag(f"Empfohlene Arbeiter : bis {empfohlene_arbeiter(MOTOR.vram_gb)} "
        f"({komma(MOTOR.vram_gb)} GB Grafikspeicher)")
    sag("Die Oberfläche wird gestartet …")
    try:
        seite.queue()
    except Exception:
        pass

    start_einst = lies_einstellungen(einstellungen)
    start_theme = normalisiere_theme(start_einst.get("theme", "Default"))
    start_args = {
        "server_name": argumente.ip,
        "server_port": argumente.port,
        "share": False,
        "inbrowser": False,
        "show_api": False,
        "quiet": False,
        "show_error": True,
        "allowed_paths": [str(ausgabe)],
        # Sprache: head läuft vor Gradios Programmteil und stellt die
        # Oberfläche auf Deutsch, js ersetzt danach die fest eingebauten
        # englischen Reste ("processing |").
        "head": SPRACHE_HEAD,
        "js": start_javascript(start_theme),
    }
    if gradio_hauptversion() >= 6:
        # Ab Gradio 6 werden Aussehen und Thema erst hier übergeben.
        start_args["css"] = CSS + themen_css(start_theme)
        thema = baue_thema(start_theme)
        if thema is not None:
            start_args["theme"] = thema

    try:
        seite.launch(**passende_argumente(seite.launch, **start_args))
    finally:
        # Arbeiter nie zurücklassen - sie hätten sonst weiter Grafikspeicher belegt.
        VERWALTUNG.stoppen()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        VERWALTUNG.stoppen()
        sag("Beendet.")
        sys.exit(0)
