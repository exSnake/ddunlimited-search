# Sketch Manifest

## Design Direction

Vetro e profondità su fondo scuro, con la sidebar come guscio stabile e l'area di
lavoro dedicata alla ricerca. Il vetro deve leggersi come segnale di profondità e
gerarchia, mai come decorazione: l'azione che conta è "cerco un titolo preciso e
voglio il link al post in due secondi", quindi ogni effetto che allunga quel
percorso è sbagliato per definizione. Superfici traslucide con bordo luminoso
(visionOS), densità e velocità da tastiera (Arc/Raycast), locandine protagoniste
sul fondo (Plex). Accenti freddi per l'interazione, caldi per i voti, verde per
"ce l'ho già".

## Reference Points

- **Plex / Jellyfin** — griglie di locandine su fondo scuro, hover che rivela
- **Apple TV / visionOS** — vetro spesso, bordi luminosi, profondità a livelli
- **Arc / Raycast** — vetro leggero e funzionale, densità alta, tastiera al centro

## Constraints

- Flask + template Jinja, **zero build**: niente npm, niente React, niente Tailwind.
  Si lavora con HTML servito, JS vanilla e CSS moderno.
- `backdrop-filter` su 50 locandine per pagina è il rischio di performance da
  verificare: ogni sketch ha un interruttore per spegnere il vetro e confrontare.
- Il dataset è reale: 67.714 titoli, locandine e voti TMDB/IMDb, sezioni Movie /
  Series / Animazione* / Anime* / Documentari.
- Lo stato "ce l'ho già" arriva da Plex, **non ancora collegato**: il design deve
  reggere anche lo stato "non lo so ancora".
- La pagina Logs sparisce: i log vanno su Grafana con Alloy/Loki.

## Decisioni acquisite

- **L'unità di ricerca è il film, non il post** (sketch 001). Un film ha in media 1,79
  post e fino a 11: le release diventano pastiglie dentro la scheda del film. I titoli
  senza match TMDB non hanno un `tmdb_id` su cui raggruppare e restano post singoli:
  le due forme devono convivere nella stessa lista.

- **I filtri vivono in un pannello laterale destro** (sketch 002), richiudibile, con i
  soli filtri attivi ripetuti come pastiglie accanto al conteggio dei risultati. La
  sidebar sinistra resta navigazione e stato; i log escono verso Grafana come voce
  esterna.

## Sketches

| # | Name | Design Question | Winner | Tags |
|---|------|----------------|--------|------|
| 001 | result-shape | Che forma ha un risultato di ricerca? | **B** scheda raggruppata | risultato, densità, locandina |
| 002 | shell-and-search | Dove vivono guscio, ricerca e filtri? | **B** pannello laterale | layout, sidebar, ricerca |
| 003 | library-state | Come si legge "ce l'ho già" e come lo filtro? | — | plex, stato, filtri |
| 004 | service-surfaces | Le superfici di servizio parlano la stessa lingua? | — | revisione, admin, sezioni |
