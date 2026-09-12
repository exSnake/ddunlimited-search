---
sketch: 004
name: service-surfaces
question: "Le superfici di servizio parlano la stessa lingua della ricerca, o servono una forma loro?"
winner: "B"
tags: [revisione, admin, sezioni, coda]
---

# Sketch 004: Superfici di servizio

## Design Question

La ricerca è risolta. Restano revisione abbinamenti, sezioni, dati mancanti e
amministrazione: **ereditano il linguaggio della ricerca o hanno bisogno di una forma
propria?**

Il caso rappresentativo è la **revisione degli abbinamenti**, perché è la più interattiva
e perché è una *coda di lavoro*: 234 elementi veri in attesa, ognuno da confermare,
scartare o correggere. Le altre superfici sono elenchi filtrabili, e quelle seguono
qualunque cosa vinca qui.

## Il materiale è vero

Gli otto abbinamenti nello sketch sono i peggiori per confidenza presi dalla coda di
produzione, e mostrano che tipo di errore va sbrigato:

| Sul forum | TMDB propone | Conf. |
|---|---|---|
| Due (Meneghetti, 2019) | It - Capitolo due (2019) | 0.32 |
| Don Camillo V - Il Compagno Don Camillo (1965) | Don Camillo (1952) | 0.33 |
| Caccia al serial killer (Azzopardi, 1998) | The Fall - Caccia al serial killer (2013) | 0.27 |

Sono quasi-centri: parole in comune, film diverso. Si smascherano in un secondo **se le
due parti stanno vicine**, molto più lentamente se vanno lette in una frase.

## How to View

```
open .planning/sketches/004-service-surfaces/index.html
```

## Variants

- **A: Stessa scheda** — la scheda della ricerca con le azioni sotto. Coerenza massima,
  ma 234 elementi a quell'altezza sono una giornata di scroll.
- **B: Coda di lavoro** ★ VINCITRICE — una riga per abbinamento, forum a sinistra e TMDB a destra:
  l'occhio confronta due colonne invece di leggere una frase. Tastiera `J`/`K`, `↵`
  conferma, `⌫` scarta.
- **C: Una alla volta** — un abbinamento grande al centro, due locandine a confronto e
  tre scelte. Ottima sui casi difficili, lenta sui quaranta di fila.

In fondo a ogni variante c'è la striscia delle altre superfici (sezioni, dati mancanti,
eliminati) per verificare che lo stesso vocabolario — numero grande, etichetta, riga di
contesto — regga anche lì.

## What to Look For

1. **Trova l'errore in `Don Camillo V` → `Don Camillo (1952)`**: quanto ci metti in A,
   in B e in C?
2. **Conta quanti ne sbrigheresti in dieci minuti** per variante. La coda è 234, e cresce
   a ogni import.
3. **In B prova la tastiera**: `J`/`K` per muoverti, `↵` per confermare. Il gesto regge?
4. **Il titolo del forum non ha locandina** (è solo testo): in C metà schermo è un
   rettangolo vuoto. Accettabile o spreco?
5. **La striscia in fondo**: quattro numeri grandi. È la stessa lingua della ricerca o
   sembra un'altra app?

## Esito

**Vince B — coda di lavoro**, con una correzione chiesta durante la revisione: mancava il
**regista proposto**. È il riferimento di FileBot, la schermata a cui l'utente è abituato,
e il regista è il discriminante che FileBot mette in chiaro.

TMDB lo espone già — `credits.crew` con `job: "Director"` per i film, `created_by` per le
serie — e `ratings.py` lo scarica di suo (`append_to_response=credits`) per pesare il
punteggio: semplicemente non lo salva. Aggiungere `matched_director` a `title_ratings`
non costa **nessuna richiesta in più**.

Il guadagno si vede sui dati veri: i due cognomi affiancati, in rosso quando non
coincidono, smascherano l'errore prima che si legga il titolo.

| Sul forum | TMDB propone | Regia proposta |
|---|---|---|
| Violent People (**Saviano**, 2005) | I violenti (1956) | **Rudolph Maté** |
| Don Camillo V (**Comencini**, 1965) | Don Camillo (1952) | **Julien Duvivier** |
| Christmas Story (**Wuolijoki**, 2007) | Una storia di Natale (1983) | **Bob Clark** |

Per le serie il posto del regista lo prende il creatore: *The Fall* mostra
«serie · creata da Allan Cubitt».
