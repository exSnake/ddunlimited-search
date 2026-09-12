---
name: sketch-findings-ddunlimited-search
description: Decisioni di design validate, pattern CSS e direzione visiva per la UI v2 di DDUnlimited Search. Da caricare quando si costruisce o si modifica l'interfaccia.
---

<context>
## Progetto: ddunlimited-search

Ricerca sui titoli del forum DDUnlimited: **67.714 titoli**, arricchiti con locandine e
voti TMDB, e con il voto IMDb dove OMDb è già arrivata. Backend Flask con template Jinja.

**Direzione visiva**: vetro e profondità su fondo scuro, sidebar come guscio stabile e
area di lavoro dedicata alla ricerca. Il vetro deve leggersi come segnale di profondità e
gerarchia, mai come decorazione: l'azione che conta è *«cerco un titolo preciso e voglio
il link al post in due secondi»*, quindi ogni effetto che allunga quel percorso è
sbagliato per definizione.

**Riferimenti dichiarati dall'utente**: Plex/Jellyfin (locandine su fondo scuro),
Apple TV/visionOS (vetro spesso, bordi luminosi, profondità a livelli), Arc/Raycast
(vetro leggero e funzionale, densità alta, tastiera al centro). Per la revisione
abbinamenti il riferimento esplicito è **FileBot**.

Sketch: 12 settembre 2026, quattro sessioni, tutte con dati veri di produzione.
</context>

<design_direction>
## Direzione validata

**Colore e materia** — fondo quasi nero con una dominante blu-violetta
(`--color-void: #07090f`, `--color-bg: #0b0e17`) e un alone ambientale fisso dietro
tutto. Le superfici vivono di alpha sul bianco (`--glass-1/2/3` da 4% a 11%) con
`backdrop-filter` e **un bordo luminoso** (`--edge`, bianco al 10%): è il bordo chiaro a
fare il volume, non l'ombra.

**Semantica dei colori** — e qui sta la decisione che vale più di tutte:

| Colore | Significato | Dove |
|---|---|---|
| Azzurro `#4cc2ff` | interazione, «qui puoi cliccare» | controlli, release che non possiedi |
| Verde `#3ddc97` | possesso, constatazione | «ce l'hai in 720p», la tua release |
| Oro `#f5c451` | voto IMDb | chip del voto |
| Azzurro TMDB `#01b4e4` | voto TMDB (il caso più frequente) | chip del voto |
| Rosso `#ff6b6b` | contraddizione fra dati | registi che non coincidono, post 404 |

L'ambra esiste nel tema (`--color-warn`) ma **non va usata sui contenuti dell'utente**:
vedi `references/tono-e-linguaggio.md`.

**Tipografia** — `system-ui` (SF Pro su macOS), nessuna dipendenza di rete. Monospace per
tutto ciò che è sigla tecnica: qualità, lingue, codec, id, confidenze. Scala da
`--text-2xs: 0.6875rem` a `--text-3xl`, titoli con `letter-spacing: -0.02em`.

**Movimento** — `cubic-bezier(0.2, 0.8, 0.2, 1)`, 120ms per il feedback immediato, 200ms
per i cambi di stato, 400ms solo per i cambi di layout. Morbido come visionOS, corto come
Arc.

**Vincolo tecnico non negoziabile** — Flask + Jinja, **zero build**: niente npm, niente
React, niente Tailwind. HTML servito, JS vanilla, CSS moderno. Ogni sketch ha un
interruttore per spegnere il vetro: `backdrop-filter` su cinquanta locandine è il rischio
di resa da verificare sul vero.
</design_direction>

<findings_index>
## Aree di design

| Area | Riferimento | Decisione chiave |
|---|---|---|
| Risultati e libreria | `references/risultati-e-libreria.md` | L'unità di ricerca è il **film**, non il post: un film ha in media 1,79 post |
| Guscio, ricerca e filtri | `references/guscio-e-ricerca.md` | Sidebar di navigazione a sinistra, **pannello filtri a destra** richiudibile |
| Tono e linguaggio | `references/tono-e-linguaggio.md` | **L'app espone fatti, non consigli** |
| Superfici di manutenzione | `references/superfici-di-manutenzione.md` | La revisione è una **coda di lavoro** a due colonne, con i registi affiancati |

## Tema

`sources/themes/default.css` — solo variabili CSS, nessuno stile di componente.

## Sorgenti

Gli HTML originali degli sketch stanno in `sources/`, con tutte le varianti navigabili e
il README che spiega cosa è stato scartato e perché. Si aprono nel browser così come sono.
</findings_index>

<metadata>
## Sketch elaborati

- 001-result-shape — vincitrice B, scheda raggruppata
- 002-shell-and-search — vincitrice B, pannello laterale
- 003-library-state — vincitrice D, indicazione attiva
- 004-service-surfaces — vincitrice B, coda di lavoro
</metadata>
