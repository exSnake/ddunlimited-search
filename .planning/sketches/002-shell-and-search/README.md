---
sketch: 002
name: shell-and-search
question: "Dove vivono il guscio, la ricerca e i filtri, ora che i filtri sono destinati a crescere?"
winner: "B"
tags: [layout, sidebar, ricerca, filtri]
---

# Sketch 002: Guscio, ricerca e filtri

## Design Question

La sidebar è decisa. Resta la domanda vera: **dove stanno i filtri**? Oggi sono sei
controlli, ma con Plex diventano almeno otto e la lista non è finita. Il vincolo è che
il gesto principale — scrivo un titolo, apro il post — non deve allungarsi di un click
per colpa loro.

## Cosa porta dentro dallo sketch 001

La scheda raggruppata, e con lei il problema dei **post orfani**: i titoli senza match
TMDB non hanno un `tmdb_id` su cui raggruppare. In tutte e tre le varianti stanno nella
stessa lista con il bordo tratteggiato e l'etichetta "non abbinato" — guarda in fondo
ai risultati, è `AVENGERS GRIMM`.

## How to View

```
open .planning/sketches/002-shell-and-search/index.html
```

## Variants

- **A: Filtri a vista** — una riga di controlli sotto la barra di ricerca, tutto sempre
  visibile. È il percorso di minor resistenza per Flask: sono una form GET.
- **B: Pannello laterale** ★ VINCITRICE — i filtri in un pannello dedicato a destra, i soli attivi
  risalgono come pastiglie accanto al conteggio. Spazio per crescere, colonna risultati
  più stretta.
- **C: Token nella barra** — un solo campo, i filtri diventano token digitabili
  (`voto:≥7`, `libreria:no`) con suggerimenti. Velocissimo da tastiera, opaco per chi
  non conosce le chiavi.

## What to Look For

1. **Conta i click** per "voto almeno 7, solo quello che non ho, solo 1080p" in ognuna.
2. **Immagina altri quattro filtri** (lingua, audio, anno, sottotitoli): quale variante
   regge e quale esplode?
3. **Il filtro libreria è acceso in A e C**: due film spariscono e il conteggio lo dice
   in verde. Si capisce che stai guardando una lista potata?
4. **Il post orfano in fondo**: tratteggiato e senza locandina. Convive o stona?
5. **La sidebar** ha i numeri veri: 234 abbinamenti da rivedere, 16.862 titoli senza
   regista o anno. Sono informazioni o rumore?
6. **Log su Grafana** è una voce con la freccia: esce dall'app. È il posto giusto?

## Esito

**Vince B — pannello laterale.** I filtri hanno una casa che regge la crescita, e le
pastiglie accanto al conteggio tengono visibile solo quello che è davvero acceso. Il
prezzo è la colonna dei risultati più stretta (~760px su 1280): la scheda raggruppata
ci sta, ma le pastiglie delle release andranno a capo prima.

### Conseguenze

- Il pannello va reso **richiudibile**, altrimenti su schermo stretto mangia i risultati.
- Il filtro libreria è un tre-stati nel pannello (Tutti / Non in libreria / Già in
  libreria): lo sketch 003 lo verifica insieme alla marcatura sul singolo risultato.
- Con i filtri fuori dalla barra, la form GET di Flask resta comunque la strada: il
  pannello è una form, le pastiglie sono link che tolgono un parametro.
