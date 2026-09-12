# Risultati e libreria

## Decisioni

### L'unità di ricerca è il film, non il post

Misurato sul database di produzione: **2507 film su 5462 hanno più di un post** (46%),
media **1,79 post per film**, e `Avatar` ne ha **undici** che differiscono solo per
qualità e release. Con una riga per post, cercare "Avatar" riempie lo schermo prima che
si arrivi al secondo film.

Quindi: **una scheda per film**, e le release diventano pastiglie cliccabili dentro la
scheda. Ogni pastiglia è un post del forum e porta al suo topic.

Conseguenza da gestire: il raggruppamento passa da `tmdb_id`, che i titoli **senza match
non hanno**. Nella stessa lista convivono due forme — il film raggruppato e il **post
orfano**, che si distingue per bordo tratteggiato, niente locandina ed etichetta «non
abbinato».

### Lo stato della libreria è un fatto, con la risoluzione dentro

Il badge dice `✓ ce l'hai in 720p`, non un generico «ce l'hai». Le release che **non**
possiedi prendono il blu dell'interazione; quella che possiedi è marcata verde con «la
tua». Vedi `tono-e-linguaggio.md` per il perché questa è la scelta giusta e l'ambra no.

«La tua» marca la release **esattamente uguale** alla copia posseduta, non l'intera
fascia di qualità: `WEB` e `720p` hanno lo stesso rango ma non sono la stessa cosa.

Il filtro libreria è a tre stati — Tutti / Non in libreria / In libreria — più un
interruttore separato e neutro: **«Solo con release che non hai»**.

### Il voto è quasi sempre TMDB

OMDb fa 900 titoli al giorno, quindi per settimane la maggioranza dei voti sarà azzurra
(TMDB) e non oro (IMDb). La gerarchia visiva deve reggere il caso frequente, non quello
bello.

### I posseduti arretrano

Opacità 62%, pieni all'hover. Serve a togliere rumore da ciò che non stai cercando, non a
svalutare la copia che hai. Da riverificare a occhio su una pagina piena.

## Pattern CSS

```css
.card {
  position: relative; display: flex; gap: var(--space-4); padding: var(--space-4);
  background: var(--glass-1); backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--edge); border-radius: var(--radius-lg);
  transition: all var(--dur) var(--ease);
}
.card:hover {
  background: var(--glass-2); border-color: var(--edge-strong);
  box-shadow: var(--shadow-md); transform: translateY(-1px);
}
.card.owned { border-left: 2px solid var(--color-owned); }
.card.dimmed { opacity: 0.62; }
.card.dimmed:hover { opacity: 1; }

/* il post senza scheda TMDB: stessa lista, forma diversa */
.card.orphan { border-style: dashed; background: transparent; }

.poster {
  display: block; object-fit: cover; flex-shrink: 0;
  width: 76px; height: 114px;
  background: linear-gradient(160deg, #1b2033, #0d1019);
  border-radius: var(--radius-sm); border: 1px solid var(--edge);
}

/* le release: monospace, perché sono sigle */
.release {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--text-2xs); font-family: var(--font-mono);
  padding: 5px 9px; border-radius: var(--radius-sm);
  background: var(--glass-2); border: 1px solid var(--edge);
  color: var(--color-text-dim); cursor: pointer;
}
.release:hover { background: var(--color-primary-dim); border-color: var(--color-primary); }
.release .q { color: var(--color-text); font-weight: 600; }

/* quella che possiedi: constatazione */
.release.mine {
  border-color: rgba(61,220,151,0.4); background: var(--color-owned-dim);
  color: var(--color-owned);
}
.release.mine::after { content: 'la tua'; font-size: 9px; opacity: 0.8; }

/* quelle che non possiedi: il blu dice "puoi cliccare", mai l'ambra */
.release.available {
  border-color: rgba(76,194,255,0.45); background: var(--color-primary-dim);
  color: var(--color-text);
}
.release.available .q { color: var(--color-primary); }

.rating { display: inline-flex; align-items: baseline; gap: 5px; font-variant-numeric: tabular-nums; }
.rating .value { font-size: var(--text-base); font-weight: 650; color: var(--color-rating); }
.rating.tmdb .value { color: var(--color-rating-tmdb); }
.rating .src { font-size: var(--text-2xs); font-weight: 600; color: var(--color-text-muted); }
```

## Struttura HTML

```html
<div class="card owned dimmed">
  <img class="poster" src="https://image.tmdb.org/t/p/w185{poster_path}" loading="lazy" alt="">
  <div class="card-main">
    <div class="card-head">
      <div>
        <div class="card-title">Avatar <span class="year">2009</span></div>
        <div class="card-dir">Cameron · Movie</div>
      </div>
      <div class="card-badges">
        <span class="badge badge-owned">✓ ce l'hai in <span class="q">720p</span></span>
        <span class="rating tmdb"><span class="value">7.6</span><span class="src">TMDB</span></span>
      </div>
    </div>
    <div class="releases">
      <span class="release available"><span class="q">2160p</span><span>ENG</span></span>
      <span class="release mine"><span class="q">720p</span><span>ITA·ENG</span></span>
      <span class="release"><span class="q">DVD</span><span>ITA</span></span>
    </div>
  </div>
</div>
```

Locandine: `https://image.tmdb.org/t/p/w185` per le schede, `w92` per le righe dense.

## Da evitare

- **Una riga per post.** Provata come variante A dello sketch 001: undici Avatar
  identici che spingono fuori pagina tutto il resto.
- **La griglia di locandine** (variante C). Bella da sfogliare, ma i titoli si troncano
  (`Agente 007 - Thunderball -…`) e i film senza locandina aprono buchi nella griglia.
  Sbagliata per «cerco un titolo preciso».
- **Il voto come stella grande sulla locandina**: compete con la copertina e non si legge
  in scansione.

## Nota tecnica

Il confronto con la libreria Plex richiede una scala di qualità
(`DVD·SD < HDTV < WEB·720p < 1080p·BluRay < 2160p·4K`) e nel database le sigle sono
**scritte in modi diversi**: `720p` e `720P`, `1080P` e `1080p`, `4K` e `2160P` come
sinonimi. Vanno normalizzate prima di poterle confrontare.

## Origine

Sketch 001 (forma del risultato) e 003 (stato libreria).
Sorgenti in `sources/001-result-shape/` e `sources/003-library-state/`.
