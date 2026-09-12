# Superfici di manutenzione

Revisione abbinamenti, sezioni, dati mancanti, amministrazione. La revisione è il caso
che le detta tutte, perché è la più interattiva e perché è una **coda di lavoro**: 234
elementi in attesa, che crescono a ogni import.

## Decisioni

### La revisione è due colonne a confronto, non una lista

Titolo del forum a sinistra, proposta TMDB a destra, freccia in mezzo. **L'occhio
confronta due colonne** invece di leggere una frase, e gli errori si smascherano in un
secondo. Una riga per abbinamento: nello spazio in cui la scheda della ricerca ne mostra
due, la coda ne mostra otto.

### Il regista affiancato è il discriminante

Su richiesta esplicita dell'utente, che usa FileBot da anni ed è abituato a vederlo. I
due cognomi stanno uno di fronte all'altro e diventano **rossi quando non coincidono**:

| Sul forum | TMDB propone | Regia proposta |
|---|---|---|
| Violent People (**Saviano**, 2005) | I violenti (1956) | **Rudolph Maté** |
| Don Camillo V (**Comencini**, 1965) | Don Camillo (1952) | **Julien Duvivier** |
| Christmas Story (**Wuolijoki**, 2007) | Una storia di Natale (1983) | **Bob Clark** |

Tre errori letti senza nemmeno guardare il titolo.

TMDB lo espone già: `credits.crew` con `job: "Director"` per i film, `created_by` per le
serie (dove l'etichetta diventa «serie · creata da»). `ratings.py` **scarica già i
credits** per pesare il punteggio, semplicemente non salva il nome: serve una colonna
`matched_director` in `title_ratings` e **nessuna richiesta in più**.

Il confronto è fra cognomi normalizzati (minuscole, senza accenti, ultimo token). Sbaglia
per difetto sui nomi non latini e sulle regie multiple — va trattato come segnale, non
come verdetto.

### Da tastiera

`J`/`K` o frecce per muoversi, `↵` conferma, `⌫` scarta, `/` cerca un'altra scheda. Una
barra sopra la coda mostra le scorciatoie e l'avanzamento.

### Le altre superfici parlano per numeri

Sezioni, dati mancanti ed eliminati sono riquadri con un numero grande, un'etichetta e
una riga di contesto. Stesso vocabolario della ricerca, nessuna forma nuova da imparare.

## Pattern CSS

```css
.queue {
  display: flex; flex-direction: column; gap: 1px;
  border: 1px solid var(--edge); border-radius: var(--radius-lg); overflow: hidden;
}
.qrow {
  display: grid; grid-template-columns: 1fr 22px 1fr auto;
  align-items: center; gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--glass-1); cursor: pointer;
  transition: background var(--dur-fast) var(--ease);
}
.qrow:hover { background: var(--glass-2); }
.qrow.sel { background: var(--color-primary-dim); box-shadow: inset 2px 0 0 var(--color-primary); }

/* il segnale che conta: i due registi non coincidono */
.dir-clash { color: var(--color-danger); }

.conf { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-mono); }
.conf-bar { width: 44px; height: 4px; border-radius: var(--radius-full); background: var(--glass-3); overflow: hidden; }
.conf-bar i { display: block; height: 100%; background: var(--color-warn); }

.btn-confirm { background: var(--color-owned-dim); border-color: rgba(61,220,151,0.4); color: var(--color-owned); }
.btn-drop { background: rgba(255,107,107,0.08); border-color: rgba(255,107,107,0.3); color: var(--color-danger); }

.tile { padding: var(--space-4); border-radius: var(--radius-lg); background: var(--glass-1); border: 1px solid var(--edge); }
.tile .n { font-size: var(--text-xl); font-weight: 650; font-variant-numeric: tabular-nums; }
```

## Struttura HTML

```html
<div class="qrow sel">
  <div class="qside">
    <div class="poster poster-empty">DD</div>
    <div>
      <div class="qtitle">Don Camillo V - Il Compagno Don Camillo</div>
      <div class="qsub"><span class="dir-clash">Comencini</span>, 1965</div>
    </div>
  </div>
  <div class="qarrow">→</div>
  <div class="qside">
    <img class="poster" src="…" alt="">
    <div>
      <div class="qtitle">Don Camillo <span class="year">1952</span></div>
      <div class="qsub"><span class="dir-clash">Julien Duvivier</span> · <span class="conf">…</span></div>
    </div>
  </div>
  <div class="qacts">
    <button class="btn btn-confirm">✓</button>
    <button class="btn btn-drop">✕</button>
    <button class="btn">cerca</button>
  </div>
</div>
```

## Da evitare

- **La scheda della ricerca con le azioni sotto** (variante A): coerente ma altissima,
  234 elementi diventano una giornata di scroll.
- **Un abbinamento alla volta a tutto schermo** (variante C): ottima sui casi difficili,
  ma il titolo del forum non ha locandina e metà schermo resta un rettangolo vuoto — e i
  234 in coda non si vedono mai tutti insieme.

## Origine

Sketch 004 (superfici di servizio). Sorgente in `sources/004-service-surfaces/`.
