# Coverage Notes — jurisdictions needing follow-up connectors

Verified 2026-07-06 by parallel discovery agents. Every entry below is real and reachable; it just needs a connector we didn't build on night one. All are also flagged `enabled: false` with a `note` in `sources.json`.

## High-value follow-ups (biggest cities first)

| Jurisdiction | Platform | Why deferred | Path forward |
|---|---|---|---|
| City of Tampa | OnBase Agenda Online (JS) | Meeting list rendered client-side | Hit the JSON backend the page calls |
| City of Orlando | eScribe | Different platform | eScribe meeting pages have HTML agendas — parseable |
| St. Petersburg | City CMS | Agendas are PDFs | PDF text extraction |
| Hialeah | CivicPlus AgendaCenter | Agendas are PDFs | One CivicPlus connector covers 7+ cities below |
| West Palm Beach | OpenCities CMS | PDFs + bot protection (403 non-browser UA) | Browser UA + PDF extraction |
| Boca Raton | Granicus MediaManager | AgendaViewer HTML pages | Parse ViewPublisher listing → AgendaViewer |
| Boynton Beach | Granicus MediaManager | Same as Boca | Same connector as Boca |
| Miami-Dade County (BOCC) | Custom legislative hub | Legistar tenant dead since 2018 | County RER "Zoning Hearing Track" needs ASP.NET VIEWSTATE postbacks |

## CivicPlus AgendaCenter family (one connector unlocks all)

Hialeah, Homestead, North Miami, Miami Gardens, Aventura, Altamonte Springs, Royal Palm Beach — same URL scheme (`/AgendaCenter`, PDFs at `/AgendaCenter/ViewFile/Agenda/_MMDDYYYY-NNN`).

## Others

- **Lake Worth Beach** — Municode Meetings (meetings.municode.com PublishPage, client `LAKEWTHFL`); PDF docs on Azure Gov blob storage.
- **Palm Beach Gardens** — Swagit video portal, JS-rendered; has JSON endpoints.
- **Largo** — CivicWeb/Diligent; server-rendered HTML + JSON endpoints, quite doable.
- **Lakeland** — direct PDFs on DNN CMS.
- **Winter Haven** — Granicus MediaManager (same connector as Boca/Boynton).
- **Osceola County** — OnBase Agenda Online, agenda PDFs.
- **Plant City** — inline HTML agendas on Revize CMS; Legistar tenant dormant (do not use).

## County development trackers deferred

- **Palm Beach County ePZB** — Angular SPA; scrape underlying XHR API.
- **Orange County FastTrack** — WebForms postback search; needs VIEWSTATE simulation.

## Traps discovered (do not trip on these again)

- `*.iqm2.com`, `*.novusagenda.com`, `*.civicclerk.com`, `*.legistar.com` all wildcard-resolve ANY subdomain with HTTP 200 — verify tenants by content, never by status code.
- Legistar client `lakecounty` is Lake County **Illinois**, not Florida.
- Legistar clients `miamidade` (dead since 2018) and `plantcity` (dormant since 2017) return valid JSON — check Events recency, not just Bodies.
- Non-obvious Legistar client names: `ppines`, `pompano`, `hollywoodfl`, `pbc`, `occompt` (Orange County via Comptroller), `seminolecountyfl`, `polkcountyfl`, `pinellas`.
