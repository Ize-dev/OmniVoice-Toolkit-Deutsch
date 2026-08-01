#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aussehen und Bedienung des Szenen-Editors.

Der Editor liegt als Überlagerung auf der Stapel-Seite und nimmt fast den
ganzen Bildschirm ein; der Hintergrund ist währenddessen gesperrt.

Gezeichnet wird auf einer Leinwand (canvas): zwei Spuren mit gemeinsamer
Zeitachse, Zoom, Auswahl, Abspielkopf und Segmentblöcke mit Ziehgriffen.
Zoomen, Schieben, Markieren und das Kontextmenü laufen vollständig im
Browser - der Server liefert nur Hüllkurven, Segmente und Tonschnipsel.

Farben kommen aus den Gradio-Variablen, damit das Thema durchschlägt; jede
hat einen festen Rückfallwert, falls die Variable fehlt.
"""

KOPF_HTML = """
<div class="ize-szene-leiste">
  <button type="button" class="ize-szene-auf" data-ize-oeffnen>🎬 &nbsp;Szenen-Editor öffnen</button>
  <span class="ize-szene-hinweis">Lange Aufnahme laden, Bereiche markieren, deutsche Spur
    aufbauen und zurück in den Stapel geben.</span>
</div>

<div class="ize-modal" data-ize-modal style="display:none">
  <div class="ize-fenster">

    <header class="ize-kopf">
      <span class="ize-titel">SZENEN&#8209;EDITOR</span>
      <input class="ize-feld" data-ize-pfad style="flex:1"
             placeholder="Pfad zur langen englischen Aufnahme (z. B. C:\\Projekte\\szene.wav)">
      <button type="button" class="ize-knopf" data-ize-laden>Öffnen</button>
      <button type="button" class="ize-knopf" data-ize-auto title="Whisper legt Segmente an">
        ✨ Automatisch vorbefüllen</button>
      <button type="button" class="ize-knopf ize-haupt" data-ize-speichern
              title="Deutsche Spur mischen und dorthin schreiben, wo der Stapel sie erwartet">
        💾 In den Stapel übernehmen</button>
      <span class="ize-sicher" data-ize-sicher></span>
      <button type="button" class="ize-knopf ize-zu" data-ize-schliessen title="Schließen (Esc)">✕</button>
    </header>

    <div class="ize-meldung" data-ize-meldung>Noch keine Aufnahme geladen.</div>

    <div class="ize-buehne">
      <div class="ize-spurnamen">
        <div class="ize-spurname">
          <span>ENGLISCH</span>
          <button type="button" class="ize-mini" data-ize-stumm-en title="Spur stumm schalten">🔊</button>
        </div>
        <div class="ize-spurname de">
          <span>DEUTSCH</span>
          <button type="button" class="ize-mini" data-ize-stumm-de title="Spur stumm schalten">🔊</button>
        </div>
      </div>
      <canvas class="ize-leinwand" data-ize-leinwand height="300"></canvas>
    </div>

    <div class="ize-leiste">
      <button type="button" class="ize-knopf" data-ize-play="en">▶ Englisch</button>
      <button type="button" class="ize-knopf" data-ize-play="de">▶ Deutsch</button>
      <button type="button" class="ize-knopf" data-ize-play="beides">▶ Beides</button>
      <button type="button" class="ize-knopf" data-ize-stopp>■ Stopp</button>
      <span class="ize-marke" data-ize-position>0:00,00</span>
      <span class="ize-marke ize-auswahl" data-ize-auswahl>keine Auswahl</span>
      <button type="button" class="ize-knopf" data-ize-alles title="Ganze Aufnahme zeigen">⤢ Alles</button>
      <span class="ize-tipp">Ziehen = markieren · Rechtsklick = Menü · Rad = Zoom ·
        Umschalt+Rad = schieben · Leertaste = zuletzt gewählte Spur ·
        Zeitachse ziehen oder ← → = Marke setzen (Strg fein, Umschalt grob)</span>
    </div>

    <div class="ize-segmente" data-ize-segmente></div>

    <footer class="ize-fuss">
      <input class="ize-feld" data-ize-ziel style="flex:1"
             placeholder="Zieldatei der deutschen Spur (.wav) – leer = dorthin, wo der Stapel sie erwartet">
      <button type="button" class="ize-knopf ize-haupt" data-ize-speichern>
        💾 Deutsche Spur speichern</button>
      <button type="button" class="ize-knopf" data-ize-projekt-sichern>Projekt sichern</button>
      <button type="button" class="ize-knopf" data-ize-projekt-laden>Projekt laden</button>
    </footer>

  </div>

  <div class="ize-menue" data-ize-menue style="display:none"></div>

  <div class="ize-eingabe-blase" data-ize-blase style="display:none">
    <div class="ize-blase-kopf" data-ize-blase-kopf>Text für den Bereich</div>
    <div class="ize-blase-original" data-ize-blase-original style="display:none"></div>
    <textarea class="ize-feld" data-ize-blase-text rows="3"
              placeholder="Deutscher Text …"></textarea>
    <div class="ize-blase-fuss">
      <button type="button" class="ize-knopf" data-ize-blase-ab>Abbrechen</button>
      <button type="button" class="ize-knopf ize-haupt" data-ize-blase-ok>Übernehmen</button>
    </div>
  </div>
</div>
"""


CSS = """
.ize-szene-leiste { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
                    padding: 4px 0 2px 0; }
.ize-szene-auf {
    padding: 10px 18px; border-radius: 10px; cursor: pointer; font-size: 14px;
    font-weight: 800; letter-spacing: .04em;
    color: var(--body-text-color, #eaf2ff);
    border: 1px solid var(--color-accent, rgba(255,79,216,.45));
    background: var(--button-primary-background-fill,
                linear-gradient(135deg, rgba(255,79,216,.22), rgba(34,224,255,.14)));
    transition: transform .08s ease, box-shadow .13s ease;
}
.ize-szene-auf:hover { box-shadow: 0 0 22px rgba(255,79,216,.35); }
.ize-szene-auf:active { transform: scale(.98); }
.ize-szene-hinweis { font-size: 12px; opacity: .6; color: var(--body-text-color, #dbe3f4); }

.ize-modal {
    position: fixed; inset: 0; z-index: 9000; display: flex;
    align-items: center; justify-content: center;
    background: rgba(4,6,12,.82); backdrop-filter: blur(5px);
}
.ize-fenster {
    display: flex; flex-direction: column; gap: 9px;
    /* overflow-y statt hidden: Passt bei sehr kleinen Fenstern trotz allem
       nicht alles hinein, wird das Fenster scrollbar, statt den Fuß samt
       Speichern-Knopf einfach abzuschneiden. */
    width: 94vw; height: 92vh; padding: 14px 16px;
    overflow-x: hidden; overflow-y: auto;
    border-radius: 16px;
    border: 1px solid var(--border-color-accent, rgba(34,224,255,.32));
    background: var(--background-fill-primary, #0d1018);
    color: var(--body-text-color, #dbe3f4);
    box-shadow: 0 24px 80px rgba(0,0,0,.75);
    font-family: var(--font, system-ui, -apple-system, "Segoe UI", sans-serif);
}
/* Kopf, Werkzeugleiste und Fuß dürfen nie schrumpfen oder aus dem Fenster
   fallen - sonst verschwindet als Erstes der Speichern-Knopf, sobald etwas
   umbricht. Nur Bühne und Segmentliste geben nach. */
.ize-kopf, .ize-leiste, .ize-fuss, .ize-meldung { flex: 0 0 auto; }
.ize-kopf { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.ize-titel { font-size: 13px; font-weight: 800; letter-spacing: .24em;
             background: linear-gradient(90deg,#ff4fd8,#22e0ff);
             -webkit-background-clip: text; background-clip: text; color: transparent; }
.ize-sicher { font-size: 11px; opacity: .5; min-width: 96px; }
.ize-feld {
    padding: 8px 11px; border-radius: 9px; font-size: 12.5px;
    color: var(--body-text-color, #eaf2ff);
    border: 1px solid var(--border-color-primary, rgba(255,255,255,.14));
    background: var(--input-background-fill, rgba(0,0,0,.35));
    font-family: inherit;
}
/* Ohne min-width behalten Eingabefelder ihre Standardbreite von rund 20
   Zeichen und zwingen Kopf- und Fußzeile in einen Umbruch. */
.ize-feld { min-width: 0; }
.ize-feld:focus { outline: none; border-color: var(--color-accent, rgba(77,155,255,.7)); }
.ize-knopf {
    padding: 8px 13px; border-radius: 9px; cursor: pointer; white-space: nowrap;
    font-size: 12.5px; font-weight: 700; color: var(--body-text-color, #dbe6ff);
    border: 1px solid var(--border-color-primary, rgba(77,155,255,.42));
    background: var(--button-secondary-background-fill, rgba(77,155,255,.14));
    transition: background .12s ease, transform .08s ease;
}
.ize-knopf:hover { background: var(--button-secondary-background-fill-hover, rgba(77,155,255,.30)); }
.ize-knopf:active { transform: scale(.97); }
.ize-knopf[disabled] { opacity: .35; cursor: not-allowed; }
.ize-knopf.ize-haupt {
    border-color: rgba(255,79,216,.5);
    background: var(--button-primary-background-fill, rgba(255,79,216,.20));
}
.ize-knopf.ize-haupt:hover { background: rgba(255,79,216,.34); }
.ize-knopf.ize-zu { margin-left: auto; }
.ize-knopf.laeuft { background: rgba(255,79,216,.3); }
.ize-knopf.aktiv { border-color: #46e08a; color: #7ff0b0; }

.ize-meldung { font-size: 12px; opacity: .8; min-height: 16px; }
.ize-buehne { display: flex; gap: 8px; align-items: stretch; flex: 3 1 0; min-height: 130px; }
.ize-spurnamen { display: flex; flex-direction: column; width: 88px; flex: 0 0 88px; gap: 4px; }
.ize-spurname {
    flex: 1; display: flex; flex-direction: column; align-items: flex-end;
    justify-content: center; gap: 6px; padding-right: 8px; text-align: right;
    font-size: 10px; font-weight: 800; letter-spacing: .14em; color: #8aa4c8;
    border-right: 2px solid rgba(138,164,200,.35);
}
.ize-spurname.de { color: #4d9bff; border-right-color: rgba(77,155,255,.45); }
.ize-spurname.stumm { opacity: .4; }
.ize-leinwand {
    flex: 1; width: 100%; height: 100%; border-radius: 10px; cursor: crosshair;
    background: var(--background-fill-secondary, rgba(0,0,0,.35));
    border: 1px solid var(--border-color-primary, rgba(255,255,255,.08)); display: block;
}
.ize-leiste, .ize-fuss { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ize-marke {
    padding: 5px 10px; border-radius: 8px; font-size: 12px; font-weight: 700;
    font-family: ui-monospace, Consolas, monospace; white-space: nowrap;
    color: #9fb0cc; background: rgba(255,255,255,.06);
}
.ize-marke.ize-auswahl { color: #ffd27d; background: rgba(255,200,87,.14); }
.ize-tipp { font-size: 11px; opacity: .42; }
.ize-segmente {
    overflow-y: auto; flex: 1 1 26vh; min-height: 74px; border-radius: 10px;
    border: 1px solid var(--border-color-primary, rgba(255,255,255,.08));
    background: var(--background-fill-secondary, rgba(0,0,0,.22));
}
.ize-seg {
    display: flex; align-items: center; gap: 9px; padding: 7px 11px;
    border-top: 1px solid rgba(255,255,255,.055); font-size: 12px; cursor: pointer;
    transition: background .12s ease;
}
.ize-seg:first-child { border-top: 0; }
.ize-seg:hover { background: rgba(77,155,255,.10); }
.ize-seg.gewaehlt {
    background: rgba(255,79,216,.16); box-shadow: inset 3px 0 0 #ff4fd8;
}
.ize-seg.stumm { opacity: .45; }
.ize-seg-zeit { font-family: ui-monospace, Consolas, monospace; color: #8aa4c8;
                white-space: nowrap; }
.ize-seg-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ize-seg-text i { opacity: .55; }
.ize-seg-art { font-size: 10px; font-weight: 800; letter-spacing: .1em; padding: 2px 7px;
               border-radius: 8px; }
.ize-seg-art.tts { color: #ff9be9; background: rgba(255,79,216,.16); }
.ize-seg-art.kopie { color: #8aa4c8; background: rgba(138,164,200,.16); }
.ize-warn { color: #ffd27d; font-size: 11px; white-space: nowrap; }
.ize-fehlt { color: #ff9b9b; font-size: 11px; white-space: nowrap; }
.ize-mini { padding: 4px 8px; font-size: 11px; border-radius: 7px; cursor: pointer;
            color: var(--body-text-color, #dbe6ff);
            border: 1px solid var(--border-color-primary, rgba(255,255,255,.14));
            background: rgba(255,255,255,.05); }
.ize-mini:hover { background: rgba(77,155,255,.25); }
.ize-leer { padding: 18px; text-align: center; font-size: 12px; opacity: .5; }

.ize-menue {
    position: fixed; z-index: 9500; min-width: 210px; padding: 5px;
    border-radius: 10px; border: 1px solid rgba(255,255,255,.14);
    background: var(--background-fill-primary, #121524);
    box-shadow: 0 14px 40px rgba(0,0,0,.6);
}
.ize-menue button {
    display: block; width: 100%; text-align: left; padding: 8px 11px; cursor: pointer;
    border: 0; border-radius: 7px; font-size: 12.5px; background: transparent;
    color: var(--body-text-color, #dbe3f4); font-family: inherit;
}
.ize-menue button:hover { background: rgba(77,155,255,.22); }
.ize-menue hr { border: 0; border-top: 1px solid rgba(255,255,255,.09); margin: 4px 2px; }
.ize-menue .weg:hover { background: rgba(255,107,107,.25); }

.ize-eingabe-blase {
    position: fixed; z-index: 9600; width: 420px; padding: 11px;
    display: flex; flex-direction: column; gap: 8px;
    border-radius: 12px; border: 1px solid rgba(255,79,216,.45);
    background: var(--background-fill-primary, #121524);
    box-shadow: 0 16px 50px rgba(0,0,0,.65);
}
.ize-blase-kopf { font-size: 11px; font-weight: 800; letter-spacing: .16em; color: #ff9be9; }
.ize-blase-original { font-size: 11.5px; opacity: .6; font-style: italic; }
.ize-blase-fuss { display: flex; gap: 8px; justify-content: flex-end; }

/* Auf kleinen Fenstern fliegen zuerst die Erklärtexte raus - sie sind der
   größte Grund für Umbrüche, und ohne sie bleibt alles bedienbar. */
@media (max-height: 640px), (max-width: 900px) {
    .ize-tipp, .ize-szene-hinweis { display: none; }
}
"""


JS = r"""
const Z = {
  dauer: 0, welleEN: [], welleDE: [], segmente: [], quelle: "",
  von: 0, bis: 0, auswahl: null, gewaehlt: null, cursor: 0,
  ziehen: null, stummEN: false, stummDE: false,
  spielt: null,          // {spur, von, bis, beginn}
  letzteSpur: "en",      // Leertaste nimmt genau die wieder
};
const ton = new Audio();
const modal = element.querySelector("[data-ize-modal]");
const leinwand = element.querySelector("[data-ize-leinwand]");
const stift = leinwand.getContext("2d");
const menue = element.querySelector("[data-ize-menue]");
const blase = element.querySelector("[data-ize-blase]");
let blaseAktion = null;

const q = (n) => element.querySelector("[data-ize-" + n + "]");
const melde = (t) => { const f = q("meldung"); if (f) f.textContent = t || ""; };
const zeit = (s) => {
  s = Math.max(0, s || 0);
  const m = Math.floor(s / 60), r = s - m * 60;
  return m + ":" + (r < 10 ? "0" : "") + r.toFixed(2).replace(".", ",");
};
const LINEAL = 22, LUECKE = 6;

// ---------------------------------------------------------------- Zeichnen
function masse() {
  const breite = Math.max(320, leinwand.clientWidth || 900);
  const hoehe = Math.max(160, leinwand.clientHeight || 300);
  const d = window.devicePixelRatio || 1;
  if (leinwand.width !== Math.round(breite * d) || leinwand.height !== Math.round(hoehe * d)) {
    leinwand.width = Math.round(breite * d);
    leinwand.height = Math.round(hoehe * d);
  }
  stift.setTransform(d, 0, 0, d, 0, 0);
  const spur = (hoehe - LINEAL - LUECKE) / 2;
  return { breite, hoehe, spur, obenEN: LINEAL, obenDE: LINEAL + spur + LUECKE };
}
const zuX = (t, b) => (t - Z.von) / Math.max(1e-6, Z.bis - Z.von) * b;
const zuZeit = (x, b) => Z.von + (x / b) * (Z.bis - Z.von);

function welleMalen(welle, oben, hoehe, breite, farbe, blass) {
  stift.fillStyle = "rgba(255,255,255,.025)";
  stift.fillRect(0, oben, breite, hoehe);
  if (!welle || !welle.length || !Z.dauer) return;
  const mitte = oben + hoehe / 2, proPunkt = Z.dauer / welle.length;
  stift.beginPath();
  for (let x = 0; x <= breite; x++) {
    const i = Math.max(0, Math.min(welle.length - 1, Math.floor(zuZeit(x, breite) / proPunkt)));
    const a = (welle[i] || 0) * (hoehe / 2 - 3);
    if (x === 0) stift.moveTo(x, mitte - a); else stift.lineTo(x, mitte - a);
  }
  for (let x = breite; x >= 0; x--) {
    const i = Math.max(0, Math.min(welle.length - 1, Math.floor(zuZeit(x, breite) / proPunkt)));
    const a = (welle[i] || 0) * (hoehe / 2 - 3);
    stift.lineTo(x, mitte + a);
  }
  stift.closePath();
  stift.globalAlpha = blass ? 0.35 : 1;
  stift.fillStyle = farbe;
  stift.fill();
  stift.globalAlpha = 1;
}

function zeichnen() {
  const { breite, hoehe, spur, obenEN, obenDE } = masse();
  stift.clearRect(0, 0, breite, hoehe);

  stift.fillStyle = "rgba(255,255,255,.05)";
  stift.fillRect(0, 0, breite, LINEAL);
  const spanne = Z.bis - Z.von;
  const stufen = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  const schritt = stufen.find((s) => spanne / s < 14) || 900;
  stift.strokeStyle = "rgba(255,255,255,.09)";
  stift.fillStyle = "rgba(219,227,244,.5)";
  stift.font = "10px system-ui, sans-serif";
  stift.lineWidth = 1;
  for (let t = Math.ceil(Z.von / schritt) * schritt; t <= Z.bis; t += schritt) {
    const x = Math.round(zuX(t, breite)) + 0.5;
    stift.beginPath(); stift.moveTo(x, 0); stift.lineTo(x, hoehe); stift.stroke();
    stift.fillText(zeit(t), x + 4, 14);
  }

  welleMalen(Z.welleEN, obenEN, spur, breite, "rgba(138,164,200,.8)", Z.stummEN);
  welleMalen(Z.welleDE, obenDE, spur, breite, "rgba(77,155,255,.85)", Z.stummDE);

  for (const s of Z.segmente) {
    const x1 = zuX(s.start, breite), x2 = zuX(s.ende, breite);
    if (x2 < -30 || x1 > breite + 30) continue;
    const w = Math.max(3, x2 - x1);
    const gewaehlt = Z.gewaehlt === s.nummer;
    stift.fillStyle = s.stumm ? "rgba(120,130,150,.16)"
      : (s.art === "kopie" ? "rgba(138,164,200,.20)" : "rgba(255,79,216,.18)");
    stift.fillRect(x1, obenDE, w, spur);
    stift.strokeStyle = !s.fertig ? "rgba(255,155,155,.8)"
      : (s.veraltet ? "rgba(255,210,125,.9)"
      : (gewaehlt ? "#ff4fd8" : (s.art === "kopie" ? "rgba(138,164,200,.6)" : "rgba(255,79,216,.5)")));
    stift.lineWidth = gewaehlt ? 2 : 1;
    stift.strokeRect(x1 + .5, obenDE + .5, w - 1, spur - 1);
    if (gewaehlt) {                               // Ziehgriffe
      stift.fillStyle = "#ff4fd8";
      stift.fillRect(x1 - 2, obenDE, 4, spur);
      stift.fillRect(x2 - 2, obenDE, 4, spur);
    }
    if (w > 40) {
      stift.fillStyle = "rgba(255,255,255,.8)";
      stift.font = "10px system-ui, sans-serif";
      const marke = "#" + s.nummer + (s.veraltet ? " ⟳" : "") + (s.fertig ? "" : " ⚠");
      stift.fillText(marke, x1 + 6, obenDE + 13);
    }
  }

  if (Z.auswahl) {
    const x1 = zuX(Z.auswahl.von, breite), x2 = zuX(Z.auswahl.bis, breite);
    stift.fillStyle = "rgba(255,200,87,.13)";
    stift.fillRect(x1, LINEAL, x2 - x1, hoehe - LINEAL);
    stift.strokeStyle = "rgba(255,200,87,.9)"; stift.lineWidth = 1;
    stift.beginPath();
    stift.moveTo(x1 + .5, LINEAL); stift.lineTo(x1 + .5, hoehe);
    stift.moveTo(x2 - .5, LINEAL); stift.lineTo(x2 - .5, hoehe);
    stift.stroke();
  }

  const cx = zuX(Z.cursor, breite);
  if (cx >= -1 && cx <= breite + 1) {
    stift.strokeStyle = "#7ff0b0"; stift.lineWidth = 1.5;
    stift.beginPath(); stift.moveTo(cx, 0); stift.lineTo(cx, hoehe); stift.stroke();
    stift.fillStyle = "#7ff0b0";
    stift.beginPath();
    stift.moveTo(cx - 5, 0); stift.lineTo(cx + 5, 0); stift.lineTo(cx, 7); stift.fill();
  }
}

// ---------------------------------------------------------------- Zustand
function uebernehmen(a) {
  try {
    if (!a || typeof a !== "object") return;
    if (typeof a.dauer === "number" && a.pfad !== undefined) {
      const neu = a.pfad !== Z.quelle || !Z.dauer;
      Z.dauer = a.dauer; Z.quelle = a.pfad;
      if (neu) { Z.von = 0; Z.bis = a.dauer; Z.auswahl = null; Z.cursor = 0; Z.gewaehlt = null; }
      if (Z.bis > Z.dauer || Z.bis <= Z.von) { Z.von = 0; Z.bis = Z.dauer; }
    }
    if (Array.isArray(a.welle_en)) Z.welleEN = a.welle_en;
    if (Array.isArray(a.welle_de)) Z.welleDE = a.welle_de;
    if (Array.isArray(a.segmente)) Z.segmente = a.segmente;
    if (a.meldung) melde(a.meldung);
    if (a.projekt) {
      const f = q("sicher");
      if (f) f.textContent = "✓ gesichert " + new Date().toLocaleTimeString();
    }
    listeMalen(); auswahlZeigen(); zeichnen();
  } catch (fehler) { melde("Anzeige-Fehler: " + fehler); }
}

function listeMalen() {
  const kasten = q("segmente");
  if (!Z.segmente.length) {
    kasten.innerHTML = "<div class='ize-leer'>Noch keine Segmente. Bereich ziehen, " +
      "dann Rechtsklick oder Leertaste – oder oben »Automatisch vorbefüllen«.</div>";
    return;
  }
  const sicher = (t) => String(t || "").replace(/[<>&]/g, (c) =>
    ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
  kasten.innerHTML = Z.segmente.map((s) => {
    const text = s.text ? sicher(s.text)
      : (s.art === "kopie" ? "<i>Original übernommen</i>"
        : (s.original ? "<i>" + sicher(s.original) + "</i>" : "<i>kein Text</i>"));
    return "<div class='ize-seg" + (s.stumm ? " stumm" : "") +
      (Z.gewaehlt === s.nummer ? " gewaehlt" : "") + "' data-ize-seg='" + s.nummer + "'>" +
      "<span class='ize-seg-art " + s.art + "'>" + (s.art === "kopie" ? "ORIG" : "TTS") + "</span>" +
      "<span class='ize-seg-zeit'>" + zeit(s.start) + " → " + zeit(s.ende) +
      " (" + s.dauer.toFixed(2).replace(".", ",") + " s)</span>" +
      "<span class='ize-seg-text'>" + text + "</span>" +
      (s.fertig ? "" : "<span class='ize-fehlt'>keine Aufnahme</span>") +
      (s.veraltet ? "<span class='ize-warn'>Länge/Text geändert</span>" : "") +
      "<button type='button' class='ize-mini' data-ize-seg-hoeren='" + s.nummer + "'>♪</button>" +
      (s.art === "tts" ? "<button type='button' class='ize-mini' data-ize-seg-text='" +
        s.nummer + "' title='Text bearbeiten'>✎</button>" +
        "<button type='button' class='ize-mini' data-ize-seg-neu='" + s.nummer +
        "' title='neu erzeugen'>↻</button>" : "") +
      "<button type='button' class='ize-mini' data-ize-seg-teilen='" + s.nummer +
      "' title='an der Cursorstelle teilen'>✂</button>" +
      "<button type='button' class='ize-mini' data-ize-seg-stumm='" + s.nummer + "'>" +
      (s.stumm ? "🔈" : "🔇") + "</button>" +
      "<button type='button' class='ize-mini' data-ize-seg-weg='" + s.nummer + "'>✕</button></div>";
  }).join("");
}

function auswahlZeigen() {
  const f = q("auswahl");
  if (f) {
    f.textContent = Z.auswahl
      ? zeit(Z.auswahl.von) + " → " + zeit(Z.auswahl.bis) + "  (" +
        (Z.auswahl.bis - Z.auswahl.von).toFixed(2).replace(".", ",") + " s)"
      : "keine Auswahl";
  }
  const p = q("position");
  if (p) p.textContent = zeit(Z.cursor);
}

async function ruf(name, daten, knopf) {
  if (knopf) { knopf.disabled = true; knopf.classList.add("laeuft"); }
  try {
    const a = await server[name](daten);
    if (a && a.ok === false && a.meldung) melde(a.meldung);
    uebernehmen(a);
    return a;
  } catch (fehler) {
    melde("Fehler: " + fehler);
    return null;
  } finally {
    if (knopf) { knopf.disabled = false; knopf.classList.remove("laeuft"); }
  }
}

// ---------------------------------------------------------------- Wiedergabe
let abspielTakt = null;
function stoppen() {
  ton.pause(); Z.spielt = null;
  if (abspielTakt) { clearInterval(abspielTakt); abspielTakt = null; }
}

// Zeigt am Abspielknopf, welche Spur die Leertaste nehmen würde.
function spurZeigen() {
  element.querySelectorAll("[data-ize-play]").forEach((k) => {
    k.classList.toggle("aktiv", k.getAttribute("data-ize-play") === Z.letzteSpur);
  });
}

async function abspielen(spur, von) {
  if (!Z.dauer) { melde("Erst eine Aufnahme laden."); return; }
  Z.letzteSpur = spur;
  spurZeigen();
  stoppen();
  const bis = Math.min(Z.dauer, von + 60);        // in Stücken, sonst wird es zu groß
  const a = await ruf("szene_hoeren", {
    start: von, ende: bis, spur: spur,
    en_an: !Z.stummEN, de_an: !Z.stummDE,
  });
  if (!a || !a.uri) return;
  Z.spielt = { spur: spur, von: von, bis: bis };
  ton.src = a.uri;
  ton.play().catch(() => melde("Der Browser konnte den Ton nicht abspielen."));
  abspielTakt = setInterval(() => {
    if (!Z.spielt) return;
    Z.cursor = Math.min(Z.dauer, Z.spielt.von + (ton.currentTime || 0));
    auswahlZeigen(); zeichnen();
  }, 60);
  ton.onended = () => {
    const weiter = Z.spielt ? Z.spielt.bis : 0;
    if (weiter && weiter < Z.dauer - 0.05) abspielen(spur, weiter);   // nahtlos weiter
    else { stoppen(); zeichnen(); }
  };
}

// ---------------------------------------------------------------- Maus
function griffTreffer(t, breite) {
  if (Z.gewaehlt === null) return null;
  const s = Z.segmente.find((x) => x.nummer === Z.gewaehlt);
  if (!s) return null;
  const nah = (Z.bis - Z.von) / breite * 6;
  if (Math.abs(t - s.start) < nah) return { seg: s, seite: "links" };
  if (Math.abs(t - s.ende) < nah) return { seg: s, seite: "rechts" };
  return null;
}

leinwand.addEventListener("mousedown", (e) => {
  if (e.button !== 0 || !Z.dauer) return;
  menue.style.display = "none";
  const k = leinwand.getBoundingClientRect();
  const t = zuZeit(e.clientX - k.left, k.width);
  const y = e.clientY - k.top;
  const { obenDE } = masse();

  if (y < LINEAL) {
    // Auf der Zeitachse lässt sich die Abspielmarke gedrückt halten und
    // ziehen. Neu gehört wird erst beim Loslassen - sonst würde für jede
    // Mausbewegung ein Tonschnipsel geholt.
    Z.ziehen = { art: "kopf", liefLos: !!Z.spielt,
                 spur: Z.spielt ? Z.spielt.spur : Z.letzteSpur };
    if (Z.spielt) stoppen();
    Z.cursor = Math.max(0, Math.min(Z.dauer, t));
    leinwand.style.cursor = "ew-resize";
    auswahlZeigen(); zeichnen(); return;
  }

  const griff = griffTreffer(t, k.width);
  if (griff && y >= obenDE) { Z.ziehen = { art: "griff", ...griff }; return; }

  if (y >= obenDE) {
    const treffer = Z.segmente.find((s) => t >= s.start && t <= s.ende);
    if (treffer) {
      // Ein bereits gewähltes Segment lässt sich am Stück verschieben; der
      // erste Klick wählt nur aus, damit man nicht versehentlich zieht.
      if (Z.gewaehlt === treffer.nummer) {
        Z.ziehen = { art: "schieben", seg: treffer,
                     versatz: t - treffer.start, laenge: treffer.ende - treffer.start };
        leinwand.style.cursor = "grabbing";
        return;
      }
      Z.gewaehlt = treffer.nummer;
      Z.auswahl = { von: treffer.start, bis: treffer.ende };
      Z.cursor = treffer.start;
      listeMalen(); auswahlZeigen(); zeichnen();
      return;
    }
  }
  Z.ziehen = { art: "auswahl", start: t };
  Z.auswahl = { von: t, bis: t };
  zeichnen();
});

window.addEventListener("mousemove", (e) => {
  if (!Z.ziehen) return;
  const k = leinwand.getBoundingClientRect();
  const t = Math.max(0, Math.min(Z.dauer, zuZeit(e.clientX - k.left, k.width)));
  if (Z.ziehen.art === "kopf") {
    Z.cursor = t;
  } else if (Z.ziehen.art === "auswahl") {
    Z.auswahl = { von: Math.min(Z.ziehen.start, t), bis: Math.max(Z.ziehen.start, t) };
  } else if (Z.ziehen.art === "schieben") {
    const s = Z.ziehen.seg;
    s.start = Math.max(0, Math.min(Z.dauer - Z.ziehen.laenge, t - Z.ziehen.versatz));
    s.ende = s.start + Z.ziehen.laenge;
    Z.auswahl = { von: s.start, bis: s.ende };
  } else {
    const s = Z.ziehen.seg;
    if (Z.ziehen.seite === "links") s.start = Math.min(t, s.ende - 0.15);
    else s.ende = Math.max(t, s.start + 0.15);
    s.dauer = s.ende - s.start;
    Z.auswahl = { von: s.start, bis: s.ende };
  }
  auswahlZeigen(); zeichnen();
});

window.addEventListener("mouseup", async () => {
  const zug = Z.ziehen;
  Z.ziehen = null;
  leinwand.style.cursor = "crosshair";
  if (!zug) return;
  if (zug.art === "kopf") {
    // Lief gerade etwas, geht es an der neuen Stelle weiter.
    if (zug.liefLos) abspielen(zug.spur, Z.cursor);
    zeichnen();
  } else if (zug.art === "auswahl") {
    if (Z.auswahl && Z.auswahl.bis - Z.auswahl.von < 0.02) { Z.auswahl = null; auswahlZeigen(); }
    zeichnen();
  } else {
    await ruf("szene_verschieben", { nummer: zug.seg.nummer, start: zug.seg.start, ende: zug.seg.ende });
  }
});

leinwand.addEventListener("wheel", (e) => {
  if (!Z.dauer) return;
  e.preventDefault();
  const k = leinwand.getBoundingClientRect();
  const spanne = Z.bis - Z.von;
  if (e.shiftKey) {
    const weg = spanne * 0.18 * Math.sign(e.deltaY);
    Z.von = Math.max(0, Math.min(Z.dauer - spanne, Z.von + weg));
    Z.bis = Z.von + spanne;
  } else {
    const mitte = zuZeit(e.clientX - k.left, k.width);
    const neu = Math.max(0.3, Math.min(Z.dauer, spanne * (e.deltaY > 0 ? 1.25 : 0.8)));
    let von = mitte - (mitte - Z.von) * (neu / spanne);
    Z.von = Math.max(0, Math.min(Z.dauer - neu, von));
    Z.bis = Z.von + neu;
  }
  zeichnen();
}, { passive: false });

// ---------------------------------------------------------------- Kontextmenü
function menueZeigen(x, y, eintraege) {
  menue.innerHTML = eintraege.map((e) => e === "-" ? "<hr>"
    : "<button type='button' class='" + (e.gefahr ? "weg" : "") + "' data-tat='" + e.tat +
      "'>" + e.text + "</button>").join("");
  menue.style.display = "block";
  menue.style.left = Math.min(x, window.innerWidth - 230) + "px";
  menue.style.top = Math.min(y, window.innerHeight - menue.offsetHeight - 12) + "px";
}

leinwand.addEventListener("contextmenu", (e) => {
  e.preventDefault();
  if (!Z.dauer) return;
  const k = leinwand.getBoundingClientRect();
  const t = zuZeit(e.clientX - k.left, k.width);
  const { obenDE } = masse();
  const treffer = (e.clientY - k.top) >= obenDE
    ? Z.segmente.find((s) => t >= s.start && t <= s.ende) : null;

  if (treffer) {
    Z.gewaehlt = treffer.nummer;
    Z.auswahl = { von: treffer.start, bis: treffer.ende };
    listeMalen(); auswahlZeigen(); zeichnen();
    const eintraege = [{ tat: "seg-hoeren", text: "♪  Segment anhören" }];
    if (treffer.art === "tts") {
      eintraege.push({ tat: "seg-text", text: "✎  Text bearbeiten" },
                     { tat: "seg-neu", text: "↻  Neu erzeugen" });
    }
    // Teilen geht nur, wenn der Cursor wirklich mitten im Segment steht.
    const teilbar = Z.cursor > treffer.start + 0.15 && Z.cursor < treffer.ende - 0.15;
    eintraege.push({ tat: "seg-teilen",
                     text: teilbar ? "✂  Bei " + zeit(Z.cursor) + " teilen"
                                   : "✂  Teilen (Cursor mitten ins Segment setzen)" });
    eintraege.push({ tat: "seg-original", text: "⧉  Durch Original ersetzen" }, "-",
                   { tat: "seg-stumm", text: treffer.stumm ? "🔈  Wieder hörbar" : "🔇  Stumm schalten" },
                   { tat: "seg-weg", text: "✕  Löschen", gefahr: true });
    menueZeigen(e.clientX, e.clientY, eintraege);
    return;
  }

  if (!Z.auswahl || t < Z.auswahl.von || t > Z.auswahl.bis) {
    Z.cursor = t; auswahlZeigen(); zeichnen();
  }
  menueZeigen(e.clientX, e.clientY, [
    { tat: "sprechen", text: "🎤  Text sprechen lassen …" },
    { tat: "kopieren", text: "⧉  Original übernehmen" }, "-",
    { tat: "hoeren-en", text: "♪  Auswahl anhören (Englisch)" },
    { tat: "hoeren-de", text: "♪  Auswahl anhören (Deutsch)" },
    { tat: "ab-hier", text: "▶  Ab hier abspielen" }, "-",
    { tat: "auswahl-weg", text: "Auswahl aufheben" },
  ]);
});

// ---------------------------------------------------------------- Textblase
function blaseZeigen(titel, text, original, aktion, x, y) {
  q("blase-kopf").textContent = titel;
  q("blase-text").value = text || "";
  const orig = q("blase-original");
  if (original) { orig.textContent = "Original: " + original; orig.style.display = "block"; }
  else orig.style.display = "none";
  blaseAktion = aktion;
  blase.style.display = "flex";
  blase.style.left = Math.min(x || 200, window.innerWidth - 440) + "px";
  blase.style.top = Math.min(y || 200, window.innerHeight - 210) + "px";
  setTimeout(() => q("blase-text").focus(), 30);
}
const blaseZu = () => { blase.style.display = "none"; blaseAktion = null; };

async function blaseOk() {
  const text = q("blase-text").value.trim();
  const tat = blaseAktion;
  blaseZu();
  if (!tat) return;
  if (tat.art === "sprechen") {
    if (!text) { melde("Ohne Text kann nichts gesprochen werden."); return; }
    melde("Wird gesprochen …");
    await ruf("szene_sprechen", { start: tat.von, ende: tat.bis, text: text });
  } else if (tat.art === "text") {
    await ruf("szene_text", { nummer: tat.nummer, text: text });
  }
}

// ------------------------------------------------- Öffnen, auch von außen
function oeffnen() {
  modal.style.display = "flex";
  document.body.style.overflow = "hidden";
  setTimeout(() => { masse(); zeichnen(); }, 40);
}

// Die erweiterte Stapelliste liegt in einem eigenen Baustein und kommt nur
// über das Fenster-Objekt an den Editor heran.
window.izeSzeneOeffnen = async function (pfad, ziel) {
  oeffnen();
  if (ziel) q("ziel").value = ziel;
  if (!pfad) return;
  if (pfad === Z.quelle && Z.dauer) { melde("Szene ist bereits geladen."); return; }
  q("pfad").value = pfad;
  melde("Wird geladen …");
  await ruf("szene_laden", { pfad: pfad });
};

// ---------------------------------------------------------------- Klicks
element.addEventListener("click", async (e) => {
  const ziel = e.target;
  const knopf = ziel.closest("button");

  if (ziel.closest("[data-ize-oeffnen]")) { oeffnen(); return; }
  if (ziel.closest("[data-ize-schliessen]")) {
    modal.style.display = "none"; document.body.style.overflow = "";
    stoppen(); menue.style.display = "none"; blaseZu(); return;
  }
  if (menue.contains(ziel)) {
    const tat = ziel.getAttribute("data-tat");
    menue.style.display = "none";
    if (!tat) return;
    const seg = Z.segmente.find((s) => s.nummer === Z.gewaehlt);
    if (tat === "sprechen") {
      if (!Z.auswahl) { melde("Erst einen Bereich markieren."); return; }
      blaseZeigen("Text für " + zeit(Z.auswahl.von) + " → " + zeit(Z.auswahl.bis), "", "",
                  { art: "sprechen", von: Z.auswahl.von, bis: Z.auswahl.bis },
                  e.clientX, e.clientY);
    } else if (tat === "kopieren") {
      if (!Z.auswahl) { melde("Erst einen Bereich markieren."); return; }
      await ruf("szene_kopieren", { start: Z.auswahl.von, ende: Z.auswahl.bis });
    } else if (tat === "hoeren-en" || tat === "hoeren-de") {
      if (!Z.auswahl) { melde("Erst einen Bereich markieren."); return; }
      // Abspielmarke springt an den Anfang der Auswahl und läuft normal weiter.
      Z.cursor = Z.auswahl.von;
      abspielen(tat.endsWith("de") ? "de" : "en", Z.cursor);
    } else if (tat === "ab-hier") {
      abspielen("beides", Z.cursor);
    } else if (tat === "auswahl-weg") {
      Z.auswahl = null; Z.gewaehlt = null; listeMalen(); auswahlZeigen(); zeichnen();
    } else if (tat === "seg-hoeren" && seg) {
      Z.cursor = seg.start;
      abspielen("de", Z.cursor);
    } else if (tat === "seg-teilen" && seg) {
      if (!(Z.cursor > seg.start + 0.15 && Z.cursor < seg.ende - 0.15)) {
        melde("Zum Teilen zuerst oben auf die Zeitachse klicken – der Cursor muss "
              + "mitten im Segment stehen.");
        return;
      }
      await ruf("szene_teilen", { nummer: seg.nummer, zeitpunkt: Z.cursor });
    } else if (tat === "seg-text" && seg) {
      blaseZeigen("Text von Segment " + seg.nummer, seg.text, seg.original,
                  { art: "text", nummer: seg.nummer }, e.clientX, e.clientY);
    } else if (tat === "seg-neu" && seg) {
      melde("Segment " + seg.nummer + " wird neu erzeugt …");
      await ruf("szene_neu", { nummer: seg.nummer, text: seg.text || "" });
    } else if (tat === "seg-original" && seg) {
      await ruf("szene_kopieren", { start: seg.start, ende: seg.ende, ersetzt: seg.nummer });
    } else if (tat === "seg-stumm" && seg) {
      await ruf("szene_stumm", { nummer: seg.nummer });
    } else if (tat === "seg-weg" && seg) {
      await ruf("szene_weg", { nummer: seg.nummer });
      Z.gewaehlt = null;
    }
    return;
  }
  if (blase.contains(ziel)) {
    if (ziel.closest("[data-ize-blase-ab]")) blaseZu();
    else if (ziel.closest("[data-ize-blase-ok]")) await blaseOk();
    return;
  }

  if (ziel.closest("[data-ize-laden]")) {
    const p = q("pfad").value.trim();
    if (!p) { melde("Bitte einen Pfad angeben."); return; }
    melde("Wird geladen …");
    await ruf("szene_laden", { pfad: p }, knopf);
    return;
  }
  if (ziel.closest("[data-ize-auto]")) {
    melde("Whisper hört sich die Szene an – das kann ein paar Minuten dauern …");
    await ruf("szene_auto", {}, knopf);
    return;
  }
  if (ziel.closest("[data-ize-alles]")) { Z.von = 0; Z.bis = Z.dauer; zeichnen(); return; }
  if (ziel.closest("[data-ize-stopp]")) { stoppen(); zeichnen(); return; }
  const play = ziel.closest("[data-ize-play]");
  if (play) { abspielen(play.getAttribute("data-ize-play"), Z.cursor); return; }
  if (ziel.closest("[data-ize-stumm-en]")) {
    Z.stummEN = !Z.stummEN;
    knopf.textContent = Z.stummEN ? "🔇" : "🔊";
    knopf.closest(".ize-spurname").classList.toggle("stumm", Z.stummEN);
    zeichnen(); return;
  }
  if (ziel.closest("[data-ize-stumm-de]")) {
    Z.stummDE = !Z.stummDE;
    knopf.textContent = Z.stummDE ? "🔇" : "🔊";
    knopf.closest(".ize-spurname").classList.toggle("stumm", Z.stummDE);
    zeichnen(); return;
  }
  if (ziel.closest("[data-ize-speichern]")) {
    const a = await ruf("szene_speichern", { ziel: q("ziel").value.trim() }, knopf);
    // Damit die Zeile im Stapel sofort als erzeugt dasteht.
    if (a && a.ok !== false && typeof window.izeListeAuffrischen === "function") {
      try { window.izeListeAuffrischen(); } catch (fehler) {}
    }
    return;
  }
  if (ziel.closest("[data-ize-projekt-sichern]")) {
    await ruf("szene_projekt", { art: "sichern", pfad: q("ziel").value.trim() }, knopf); return;
  }
  if (ziel.closest("[data-ize-projekt-laden]")) {
    await ruf("szene_projekt", { art: "laden", pfad: q("pfad").value.trim() }, knopf); return;
  }

  const hoeren = ziel.closest("[data-ize-seg-hoeren]");
  if (hoeren) {
    const s = Z.segmente.find((x) => x.nummer === Number(hoeren.getAttribute("data-ize-seg-hoeren")));
    if (!s) return;
    Z.gewaehlt = s.nummer; Z.cursor = s.start;
    listeMalen();
    abspielen("de", s.start);
    return;
  }
  const teilen = ziel.closest("[data-ize-seg-teilen]");
  if (teilen) {
    const s = Z.segmente.find((x) => x.nummer === Number(teilen.getAttribute("data-ize-seg-teilen")));
    if (!s) return;
    if (!(Z.cursor > s.start + 0.15 && Z.cursor < s.ende - 0.15)) {
      melde("Zum Teilen zuerst oben auf die Zeitachse klicken – der Cursor muss "
            + "mitten im Segment stehen.");
      return;
    }
    await ruf("szene_teilen", { nummer: s.nummer, zeitpunkt: Z.cursor }, teilen);
    return;
  }
  const bearbeiten = ziel.closest("[data-ize-seg-text]");
  if (bearbeiten) {
    const s = Z.segmente.find((x) => x.nummer === Number(bearbeiten.getAttribute("data-ize-seg-text")));
    if (s) blaseZeigen("Text von Segment " + s.nummer, s.text, s.original,
                       { art: "text", nummer: s.nummer }, e.clientX - 200, e.clientY - 120);
    return;
  }
  const neu = ziel.closest("[data-ize-seg-neu]");
  if (neu) {
    const nr = Number(neu.getAttribute("data-ize-seg-neu"));
    const s = Z.segmente.find((x) => x.nummer === nr);
    melde("Segment " + nr + " wird neu erzeugt …");
    await ruf("szene_neu", { nummer: nr, text: (s && s.text) || "" }, neu);
    return;
  }
  const stumm = ziel.closest("[data-ize-seg-stumm]");
  if (stumm) { await ruf("szene_stumm", { nummer: Number(stumm.getAttribute("data-ize-seg-stumm")) }, stumm); return; }
  const weg = ziel.closest("[data-ize-seg-weg]");
  if (weg) {
    await ruf("szene_weg", { nummer: Number(weg.getAttribute("data-ize-seg-weg")) }, weg);
    Z.gewaehlt = null; listeMalen(); return;
  }
  const zeile = ziel.closest("[data-ize-seg]");
  if (zeile) {
    const s = Z.segmente.find((x) => x.nummer === Number(zeile.getAttribute("data-ize-seg")));
    if (s) {
      Z.gewaehlt = s.nummer;
      Z.auswahl = { von: s.start, bis: s.ende };
      Z.cursor = s.start;
      if (s.ende < Z.von || s.start > Z.bis) {          // in den Blick holen
        const spanne = Z.bis - Z.von;
        Z.von = Math.max(0, s.start - spanne / 3); Z.bis = Z.von + spanne;
      }
      listeMalen(); auswahlZeigen(); zeichnen();
    }
  }
});

document.addEventListener("click", (e) => {
  if (!menue.contains(e.target)) menue.style.display = "none";
});
document.addEventListener("keydown", (e) => {
  if (modal.style.display === "none") return;
  const imFeld = ["INPUT", "TEXTAREA"].includes((e.target.tagName || "").toUpperCase());
  if (e.key === "Escape") {
    if (blase.style.display !== "none") { blaseZu(); return; }
    if (menue.style.display !== "none") { menue.style.display = "none"; return; }
    modal.style.display = "none"; document.body.style.overflow = ""; stoppen(); return;
  }
  if (imFeld) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && blase.style.display !== "none") blaseOk();
    return;
  }
  if (e.code === "Space") {
    e.preventDefault();
    if (Z.spielt) stoppen(); else abspielen(Z.letzteSpur, Z.cursor);
    return;
  }
  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    if (!Z.dauer) return;
    e.preventDefault();
    // Feinarbeit: normal 50 ms, mit Strg 10 ms, mit Umschalt eine halbe Sekunde.
    const schritt = e.ctrlKey ? 0.01 : (e.shiftKey ? 0.5 : 0.05);
    Z.cursor = Math.max(0, Math.min(Z.dauer,
      Z.cursor + (e.key === "ArrowRight" ? schritt : -schritt)));
    // Läuft die Marke aus dem Bild, wandert der Ausschnitt mit.
    const spanne = Z.bis - Z.von;
    if (Z.cursor < Z.von || Z.cursor > Z.bis) {
      Z.von = Math.max(0, Math.min(Z.dauer - spanne, Z.cursor - spanne / 2));
      Z.bis = Z.von + spanne;
    }
    auswahlZeigen(); zeichnen();
    neuHoerenSpaeter();
  }
});

// Beim Tippen mit den Pfeiltasten nicht für jeden Tastendruck einen Schnipsel
// holen - erst wenn eine Viertelsekunde Ruhe ist, geht es an der neuen Stelle
// weiter.
let hoerTakt = null, hoerSpur = "";
function neuHoerenSpaeter() {
  if (!Z.spielt && !hoerTakt) return;      // es lief nichts, also nichts zu tun
  if (Z.spielt) { hoerSpur = Z.spielt.spur; stoppen(); }
  if (hoerTakt) clearTimeout(hoerTakt);
  hoerTakt = setTimeout(() => { hoerTakt = null; abspielen(hoerSpur, Z.cursor); }, 250);
}
window.addEventListener("resize", () => { if (modal.style.display !== "none") zeichnen(); });

listeMalen(); auswahlZeigen(); spurZeigen(); zeichnen();
"""
