---
spike: 001
name: filebot-matching
question: "Conviene usare FileBot al posto del matcher fatto in casa?"
verdict: "No nel percorso principale. Sì come passata di recupero sui non agganciati, con il regista come filtro di accettazione."
date: 2026-09-12
---

# Spike 001: FileBot al posto del matcher

## Domanda

L'utente ha licenza FileBot e lo usa da anni. Conviene riusare il suo motore di
riconoscimento invece della logica di abbinamento scritta in `ratings.py`?

## Come è stato provato

- Immagine ufficiale CLI `rednoah/filebot` su xhub, in un container separato da quello
  del NAS (che resta manuale, con la GUI, come documentato in `hosts/nas/filebot`).
- Licenza copiata dal NAS e attivata nel volume `filebot-data`.
- Campione: **i 234 incerti al completo più 200 non agganciati a caso**, 401 titoli
  unici, passati come file finti a `-rename --action test`.
- Giudice: **il regista**, che il titolo del forum già contiene. Se il cognome coincide
  con quello della scheda proposta, l'abbinamento è quasi certamente giusto. È la stessa
  misura per entrambi i matcher, quindi il confronto è equo.

## Due trappole da ricordare

1. **FileBot usa il nome della cartella come indizio.** Con i file in una cartella
   chiamata `probe`, tre titoli su cinque sono stati abbinati a un film intitolato
   *Probe*. La cartella deve avere un nome che non somigli a un titolo.
2. **FileBot ripulisce i caratteri illegali nei nomi file**, separatore `|` compreso:
   `{tmdbid}|{n}` esce concatenato. Serve un separatore che sopravviva, es. ` ~ `.

## Risultati

**Strict contro non-strict**, sugli stessi 401 titoli:

| Modalità | Abbinati |
|---|---|
| `--db TheMovieDB` (strict) | **1** su 401 |
| `-non-strict` | **344** su 401 |

I titoli del forum non sono nomi di release, quindi la modalità rigorosa li rifiuta
quasi tutti. Con `-non-strict` FileBot **tira sempre a indovinare**: non dice mai
"non lo so", e propone spazzatura con la stessa sicurezza con cui propone la cosa giusta.

**Sui 211 incerti** (quelli su cui il matcher attuale aveva già una proposta debole):

| | Regista concorde |
|---|---|
| Matcher attuale | **83** |
| FileBot | **72** |

Stesso `tmdb_id` per entrambi: 116 casi. FileBot vince (giusto lui, sbagliato io) 33
volte, perde 23. **Guadagno netto: +10 su 211.** In pratica un pareggio.

**Sui 190 non agganciati** (dove il matcher attuale si era arreso):

FileBot propone qualcosa per 136, ma solo **21 col regista concorde**. Gli altri ~115
sono rumore travestito da risposta.

## L'idea che vale, e che non era la domanda di partenza

L'accordo fra i due matcher **non** predice la correttezza: quando propongono lo stesso
film il regista coincide solo nel 51% dei casi. L'idea "se sono d'accordo fidati" non
regge.

Quello che regge è il contrario: **FileBot propone, il regista conferma.** I 21 recuperi
sui non agganciati sono di ottima qualità, e hanno tutti la stessa forma — le due classi
che la similarità di stringa non può chiudere:

| Titolo forum | FileBot |
|---|---|
| DEAD Jerry Maguire (Crowe, 1996) | Jerry Maguire (1996), Cameron Crowe |
| 8½ Otto e mezzo (Fellini, 1963) [CRITERION] | 8½ (1963), Federico Fellini |
| Eliza Graves (Anderson, 2014) | Stonehearst Asylum (2014), Brad Anderson |
| Attacco Glaciale (Trenchard-Smith, 2012) | Arctic Blast - Attacco glaciale (2010) |
| Capitan Fracassa (Gaspard-Huit, 1961) *NEW LINK* | Capitan Fracassa (1961) |

1. **Rumore di forum** — `DEAD`, `*NEW LINK*`, `[CRITERION]`: FileBot lo ignora.
2. **Titoli alias o localizzati** — `Eliza Graves` e `Stonehearst Asylum` non hanno
   nessuna parola in comune. Nessun confronto di stringhe potrà mai chiuderlo.

## Verdetto

**No come sostituto nel percorso principale.** Il guadagno sugli incerti è +10 su 211, e
in cambio si porta in casa una JVM, una licenza e un motore che non sa dire "non lo so"
dentro una pipeline che gira da sola ogni sei ore.

**Sì come passata di recupero occasionale sui non agganciati**, con il regista come
filtro di accettazione: si tiene solo ciò che il regista conferma. Sui 190 provati sono
21 recuperi (11%) praticamente senza falsi positivi. Sui circa 12.000 non agganciati del
catalogo sarebbero **~1.300 titoli**, in un lavoro batch da lanciare quando fa comodo e
non in linea.

La cucitura è già pronta: `ratings.match_by_tmdb_id(media_type, tmdb_id)` prende un id e
costruisce il resto. FileBot deve rispondere a una domanda sola.

## Limite del metodo

Il giudice sbaglia per difetto, allo stesso modo per entrambi: fallisce sui nomi non
latini (Ozu compare come `小津安二郎`), sulle regie multiple (`Horne-McCarey` contro
`James W. Horne`) e su `AA.VV.`. Le percentuali assolute sono quindi sottostimate; il
confronto fra i due resta valido perché la distorsione è identica.

## Cosa NON è emerso

Ripulire il rumore di forum nel matcher attuale sposta poco: in tutto il catalogo sono
145 prefissi `DEAD/NEW/RIUP`, 15 marcatori fra asterischi e 2.004 edizioni fra quadre,
ma fra i non agganciati pesano appena 76 titoli. Da fare perché costa niente, non da
aspettarsi miracoli.
