---
sketch: 001
name: result-shape
question: "Che forma ha un risultato di ricerca, ora che un film ha in media 1,79 post?"
winner: "B"
tags: [risultato, densità, locandina, raggruppamento]
---

# Sketch 001: Forma del risultato

## Design Question

Che forma ha un risultato di ricerca? L'atomo che vedi cinquanta volte per pagina deve
portare locandina, titolo, anno, regista, voto IMDb o TMDB, qualità, lingue, sezione,
stato "ce l'ho già", stato eliminato 404 e il link al post — senza rallentare il gesto
che conta, cioè trovare un titolo preciso e aprirlo in due secondi.

## Il dato che ha riscritto la domanda

Misurato sul database di produzione il 12/09/2026: **2507 film su 5462 hanno più di un
post** (46%), in media **1,79 post per film**, e i titoli popolari arrivano a undici —
`Avatar` ha 11 post che differiscono solo per qualità e release.

Quindi la domanda non è più "come impagino una riga" ma **"l'unità è il post o il film?"**.
È l'asse su cui si dividono le tre varianti.

## How to View

```
open .planning/sketches/001-result-shape/index.html
```

## Variants

- **A: Riga densa** — una riga per post, come oggi ma ridisegnato. Scansione massima,
  ogni riga è già la release che apri. Avatar occupa undici righe.
- **B: Scheda raggruppata** ★ VINCITRICE — un film una scheda, le release come pastiglie cliccabili.
  Undici post diventano una riga di pastiglie; lo stato "ce l'ho già" vive sul film.
- **C: Griglia locandine** — la copertina come oggetto, release rivelate all'hover.
  Bella per sfogliare, da verificare sulla ricerca mirata e sui film senza locandina.

## What to Look For

1. **Cerca "Avatar" mentalmente in ognuna**: in quale trovi prima il film, e in quale
   trovi prima *la release che vuoi*? Sono due domande diverse.
2. **Il voto è quasi sempre TMDB**, non IMDb: OMDb fa 900 titoli al giorno, quindi per
   settimane la maggioranza dei voti sarà azzurra e non oro. Regge la gerarchia?
3. **Spegni il vetro** dalla barra in basso a destra: con le locandine vere si sente
   la differenza di resa. Se non si sente, il vetro costa senza rendere.
4. **Scollega Plex** (stesso pannello): lo stato diventa "non lo so ancora". Il design
   regge il periodo in cui Plex non c'è ancora?
5. **`[•REC]` e i corti**: nessuna locandina, nessun voto, abbinamento incerto. Guarda
   come cadono, soprattutto nella griglia.
6. **Tastiera nella A**: `j`/`k` o frecce per muoverti, `Invio` per aprire. È il gesto
   da due secondi — provalo.

## Esito

**Vince B — scheda raggruppata.** L'unità di ricerca è il film, la release è il
dettaglio con cui scegli: gli stessi 28 post stanno in una schermata invece di tre,
e lo stato "ce l'ho già" trova il suo posto naturale sul film.

### Conseguenza da risolvere

Il raggruppamento passa da `tmdb_id`, che i titoli **senza match non hanno**. Restano
quindi due forme nella stessa lista: il film raggruppato e il post singolo orfano.
Va deciso nello sketch 002 come convivono senza sembrare due liste diverse.
