# Guscio, ricerca e filtri

## Decisioni

### Sidebar a sinistra, pannello filtri a destra

La **sidebar** (232px) è navigazione e stato, sempre presente: marchio con il totale dei
titoli, le destinazioni principali, un gruppo «Manutenzione» con i contatori, e in fondo
lo stato del sistema (sessione, ultimo import, Plex, avanzamento dei voti).

I **filtri** stanno in un pannello dedicato a destra (248px), **richiudibile**. Oggi sono
sei controlli, con Plex diventano almeno otto e la lista non è finita: una riga sotto la
barra di ricerca non regge quella crescita. Il prezzo è la colonna dei risultati più
stretta — circa 760px su uno schermo da 1280 — e la scheda ci sta, ma le pastiglie delle
release vanno a capo prima.

I **filtri attivi risalgono** come pastiglie rimovibili accanto al conteggio dei
risultati: nel pannello c'è tutto, sopra i risultati solo ciò che sta davvero agendo.

### La pagina Logs sparisce

I log vanno su Grafana con Alloy/Loki, che gira già su xhub. In sidebar resta una voce
con la freccia, marcata «esterno».

### La ricerca resta due campi

Titolo e regista affiancati nella stessa barra, separati da un filetto. Le quattro
modalità (contiene / inizia con / finisce con / tutte le parole) sono un controllo nel
pannello, non quattro bottoni a vista.

### Scartata: i token nella barra

La variante `voto:≥7 libreria:no avengers` in un campo solo è imbattibile da tastiera e
opaca per chiunque non conosca le chiavi. Soprattutto, i filtri attivi si leggono solo
rileggendo la barra. Tenuta da parte: potrebbe tornare come scorciatoia avanzata sopra il
pannello, non al posto suo.

## Pattern CSS

```css
.shell { display: flex; min-height: 100vh; }

.sidebar {
  width: 232px; flex-shrink: 0; display: flex; flex-direction: column;
  padding: var(--space-5) var(--space-3);
  background: var(--glass-1); backdrop-filter: blur(var(--glass-blur));
  border-right: 1px solid var(--edge);
}
.nav-item {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-2) var(--space-3); border-radius: var(--radius-md);
  font-size: var(--text-sm); color: var(--color-text-dim);
  border: 1px solid transparent; transition: all var(--dur-fast) var(--ease);
}
.nav-item:hover { background: var(--glass-2); color: var(--color-text); }
.nav-item.active { background: var(--glass-3); color: var(--color-text); border-color: var(--edge-strong); }
.nav-item .count { margin-left: auto; font-family: var(--font-mono); font-size: var(--text-2xs); }

/* la barra di ricerca si illumina sul fuoco: è il gesto principale */
.searchbar {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--glass-2); backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--edge); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md); transition: all var(--dur) var(--ease);
}
.searchbar:focus-within { border-color: var(--color-primary); box-shadow: var(--shadow-glow); }
.searchbar input {
  flex: 1; background: none; border: none; outline: none;
  color: var(--color-text); font-family: inherit; font-size: var(--text-lg);
}

.panel {
  width: 248px; flex-shrink: 0; position: sticky; top: var(--space-5);
  padding: var(--space-4);
  background: var(--glass-1); backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--edge); border-radius: var(--radius-lg);
}
.panel h3 {
  font-size: var(--text-2xs); text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--color-text-muted); font-weight: 600;
}

.active-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--text-2xs); padding: 4px 6px 4px 9px; border-radius: var(--radius-full);
  background: var(--color-primary-dim); border: 1px solid var(--color-primary);
}

@media (max-width: 860px) { .sidebar, .panel { display: none; } }
```

## Struttura HTML

```html
<div class="shell">
  <aside class="sidebar">
    <div class="brand">…</div>
    <div class="nav-group">
      <div class="nav-item active"><span class="ico">⌕</span> Ricerca</div>
      <div class="nav-item"><span class="ico">▦</span> Sezioni <span class="count">10</span></div>
      <div class="nav-item"><span class="ico">✦</span> Libreria Plex</div>
    </div>
    <div class="nav-group">
      <div class="nav-label">Manutenzione</div>
      <div class="nav-item">◎ Abbinamenti <span class="count warn">234</span></div>
      <div class="nav-item">⚠ Dati mancanti <span class="count">16.862</span></div>
      <div class="nav-item">⚙ Amministrazione</div>
      <div class="nav-item">↗ Log su Grafana <span class="ext">esterno</span></div>
    </div>
    <div class="sidebar-foot">… stato sistema …</div>
  </aside>

  <main class="work">
    <div class="with-panel">
      <div><!-- barra di ricerca, conteggio + pastiglie attive, risultati --></div>
      <aside class="panel"><!-- libreria, voto minimo, sezione, qualità --></aside>
    </div>
  </main>
</div>
```

I filtri restano una **form GET**: il pannello è la form, le pastiglie attive sono link
che tolgono un parametro. Nessun JavaScript necessario per il funzionamento di base.

## Faccette reali

Sezioni: Movie 45.567 · Series 15.008 · Documentari 1.689 · AnimeSD 1.539 ·
AnimazioneSD 1.427 · AnimazioneHD 1.419 · AnimazioneDVD 524 · AnimazioneINT 439 ·
Animazione4K 100 · AnimeHD 2. Nel pannello vanno accorpate: Animazione (3.909) e
Anime (1.541).

Eliminati 404: 62. Senza regista o anno: 16.862. Abbinamenti da rivedere: 234.

## Origine

Sketch 002 (guscio e ricerca). Sorgente in `sources/002-shell-and-search/`.
