# Tono e linguaggio

## La regola

**L'app espone fatti, non consigli.** Dice cosa hai e cosa c'è; cosa farne lo decide chi
guarda.

## Da dove viene

Il primo giro dello sketch 003 trattava il possesso come binario e aggiungeva un terzo
stato ambra, **«c'è di meglio»**, per i film posseduti in risoluzione inferiore a quella
disponibile sul forum. Scartato dall'utente, con questa motivazione:

> «Il mio avere dei film in risoluzioni più basse su Plex a volte è una scelta per
> risparmiare spazio, perché sono film a cui magari non serve avere una risoluzione alta
> per essere goduti oppure sono film di seconda fascia che si vedono così ogni tanto.»

Il 720p non è un difetto da correggere: spesso è una decisione. Un'interfaccia che lo
segnala in ambra — il colore dell'allarme — **dà un giudizio sulla libreria di chi la
usa**, e per giunta sbagliato. Il verbo «aggiornare» fa lo stesso danno in parole.

## Come si applica

| Invece di | Scrivi |
|---|---|
| «c'è di meglio» | `✓ ce l'hai in 720p` e la release migliore in blu |
| «da aggiornare» | «solo con release che non hai» |
| «qualità insufficiente» | la sigla della qualità, e basta |
| «abbinamento errato» | «abbinamento da confermare» |
| «dati mancanti» come colpa | «il titolo non segue lo schema atteso» |

**Il colore è linguaggio.** L'ambra e il rosso sono riservati alla contraddizione fra
dati — due registi che non coincidono, un post che risponde 404 — mai al contenuto
dell'utente. Quando c'è qualcosa su cui può agire, si usa il blu dell'interazione: dice
«qui puoi cliccare», non «qui c'è un problema».

**Lo stato sconosciuto è uno stato.** Finché Plex non è collegato l'app non finge: badge
tratteggiato «? non abbinato», filtri disattivati, una fascia che spiega perché e un
bottone per rimediare. Vale anche in modo permanente per i titoli senza scheda TMDB, che
non hanno un `tmdb_id` su cui interrogare Plex.

**I numeri della manutenzione sono informazione, non rimprovero.** 16.862 titoli senza
regista o anno stanno in sidebar come contatore neutro, non in rosso con un punto
esclamativo.

## Lingua

Italiano in tutta l'interfaccia, minuscolo nelle etichette tranne la prima lettera.
Niente maiuscole d'enfasi, niente punti esclamativi. Le sigle tecniche restano come sono
(`1080p`, `AC3`, `ITA·ENG`) in monospace.

## Origine

Sketch 003 (stato libreria), primo giro scartato e rifatto.
Sorgente in `sources/003-library-state/` — il README documenta cosa è stato scartato.
