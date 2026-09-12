# Sketch Wrap-Up Summary

**Data:** 12 settembre 2026
**Sketch elaborati:** 4 (tutti inclusi)
**Aree di design:** risultati e libreria · guscio e ricerca · tono e linguaggio · superfici di manutenzione
**Skill prodotto:** `./.claude/skills/sketch-findings-ddunlimited-search/`

## Sketch inclusi

| # | Nome | Vincitrice | Area |
|---|---|---|---|
| 001 | result-shape | **B** scheda raggruppata | risultati e libreria |
| 002 | shell-and-search | **B** pannello laterale | guscio e ricerca |
| 003 | library-state | **D** indicazione attiva | risultati e libreria · tono e linguaggio |
| 004 | service-surfaces | **B** coda di lavoro | superfici di manutenzione |

Nessuno escluso.

## Direzione

Vetro e profondità su fondo scuro, sidebar come guscio stabile e area di lavoro dedicata
alla ricerca. Il vetro è segnale di profondità, mai decorazione: l'azione che conta è
«cerco un titolo preciso e voglio il link al post in due secondi». Riferimenti:
Plex/Jellyfin, Apple TV/visionOS, Arc/Raycast; FileBot per la revisione abbinamenti.

## Decisioni chiave

1. **L'unità di ricerca è il film, non il post.** Il 46% dei film ha più di un post
   (media 1,79, Avatar ne ha 11): le release diventano pastiglie dentro la scheda. I
   titoli senza `tmdb_id` restano post orfani e convivono nella stessa lista.
2. **I filtri vivono in un pannello laterale destro**, richiudibile, con i soli attivi
   ripetuti come pastiglie accanto al conteggio. La pagina Logs sparisce verso Grafana.
3. **L'app espone fatti, non consigli.** Tenere un film in 720p è spesso una scelta, non
   un difetto: niente ambra sul posseduto, il blu dice «puoi cliccare» e non «c'è un
   problema». Il badge dice il fatto completo, `✓ ce l'hai in 720p`.
4. **La revisione è una coda di lavoro a due colonne**, con i registi affiancati e in
   rosso quando divergono. Serve `matched_director`, che TMDB restituisce già dentro i
   credits che scarichiamo.

## Strategia di rilascio

Decisa con l'utente: **le pagine nuove vivono accanto alle attuali** finché non sono
complete, poi si sposta la rotta e **si cancellano le vecchie**. Nessun momento in cui
l'app è a metà.

## Questioni aperte

- I posseduti smorzati (62%) vanno riverificati a occhio su una pagina piena.
- Il pannello filtri deve essere richiudibile: su schermo stretto mangia i risultati.
- Le qualità nel database sono scritte in modi diversi (`720p`/`720P`, `4K`/`2160P`):
  vanno normalizzate prima di poterle confrontare con quelle di Plex.
- `backdrop-filter` su cinquanta locandine per pagina è da verificare sul vero. Ogni
  sketch ha l'interruttore per spegnere il vetro e confrontare.
- Plex non è collegato: serve decidere come leggere la libreria, e serve la
  **risoluzione** di ogni copia posseduta, non solo la presenza.
