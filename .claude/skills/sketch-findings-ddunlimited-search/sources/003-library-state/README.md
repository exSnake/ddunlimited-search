---
sketch: 003
name: library-state
question: "Come si legge «ce l'ho già» su ogni risultato, senza dare un giudizio sulla libreria?"
winner: "D"
tags: [plex, stato, filtri, libreria, tono]
---

# Sketch 003: Ce l'ho già

## Design Question

Come si legge lo stato della libreria su ogni risultato, e che forma ha il filtro?

## Il primo giro è stato scartato, e il motivo conta

La prima versione trattava il possesso come binario e aggiungeva un terzo stato ambra,
**"c'è di meglio"**, per i film posseduti in risoluzione inferiore a quella disponibile
sul forum. Scartata dall'utente, con una ragione che riscrive il problema:

> «Il mio avere dei film in risoluzioni più basse su Plex a volte è una scelta per
> risparmiare spazio, perché sono film a cui magari non serve avere una risoluzione alta
> per essere goduti oppure sono film di seconda fascia che si vedono così ogni tanto.»

Il 720p non è un difetto da correggere: spesso è una decisione. Un'interfaccia che lo
segnala in ambra — il colore dell'allarme — **dà un giudizio sulla libreria di chi la
usa**, e per giunta sbagliato. Il verbo "aggiornare" fa lo stesso danno in parole.

La regola che ne esce, valida oltre questo sketch: **l'app espone fatti, non consigli.**
Dice cosa hai e cosa c'è; cosa farne lo decide chi guarda.

## Gli stati, riscritti

| Stato | Come si dice |
|---|---|
| non in libreria | niente badge |
| in libreria | `✓ ce l'hai in 720p` — il fatto, con la risoluzione |
| non abbinato | `? non abbinato` — nessuna scheda TMDB, Plex non sa cosa cercare |

Niente quarto stato. L'informazione "esiste anche una 2160p" resta, ma come constatazione
neutra e non come stato del film.

## How to View

```
open .planning/sketches/003-library-state/index.html
```

## Variants

Quattro volumi della stessa informazione, tutti senza giudizio:

- **A: Solo il fatto** — `✓ ce l'hai in 720p` e basta. Che esista una 2160p si legge dalle
  pastiglie come per ogni altro film.
- **B: Sussurro** — come A, più la pastiglia della tua copia marcata verde con «la tua».
- **C: Voce normale** — come B, più una riga neutra: *sul forum anche `2160p` `1080p`*.
- **D: Indicazione attiva** ★ VINCITRICE — le release che non hai prendono il blu dell'interazione
  («qui puoi cliccare»), mai l'ambra dell'allarme («qui c'è un problema»).

Il filtro è tre stati — Tutti / Non in libreria / In libreria — più un interruttore
separato e neutro: **«Solo con release che non hai»**.

## What to Look For

1. **Avatar e 007**: possedute in 720p e DVD, con release superiori sul forum. In ogni
   variante, l'interfaccia ti sta informando o ti sta dicendo cosa fare?
2. **Da A a D il volume sale**: dove smette di essere utile e comincia a essere insistente?
3. **L'interruttore «solo con release che non hai»**: neutro abbastanza, o è "da aggiornare"
   travestito?
4. **Spegni Plex** dalla barra: badge via, filtri disattivati, compare la fascia. Regge?
5. **Posseduti smorzati / pieni**: se il possesso non è un difetto, smorzare la scheda è
   ancora giusto? (smorza per togliere rumore, non per svalutare — ma il confine è sottile)

## Nota tecnica

- «La tua» marca la release **esattamente uguale** alla tua copia, non l'intera fascia:
  `WEB` e `720p` hanno lo stesso rango ma non sono la stessa cosa.
- Il confronto richiede una scala (`DVD·SD < HDTV < WEB·720p < 1080p·BluRay < 2160p·4K`)
  e nel database le qualità sono scritte in modi diversi — `720p` e `720P`, `4K` e `2160P`.
  Vanno normalizzate prima di poterle confrontare.

## Esito

**Vince D — indicazione attiva.** Le release che non hai prendono il blu
dell'interazione: si vedono subito, ma il colore dice "qui puoi cliccare" e non "qui c'è
un problema". Il badge resta il fatto completo, `✓ ce l'hai in 720p`.

I posseduti restano **smorzati** (opacità 62%, pieni all'hover): serve a togliere rumore
da ciò che non stai cercando, non a svalutare la copia che hai. Da riverificare a occhio
su una pagina piena.
