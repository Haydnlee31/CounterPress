# Comeback match source

Source: Belgium–Japan, 2 July 2018, Wyscout match **2058007**. Display adaptation: **Eastbridge 3–2 Northport — Back from two down**.

Event data by **Luca Pappalardo and Emanuele Massucco / Wyscout**, [Events](https://doi.org/10.6084/m9.figshare.7770599) and [Matches](https://doi.org/10.6084/m9.figshare.7770422), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Licence rechecked against the Figshare API on 18 October 2026.

`events.json` selects the 1,682 records with `matchId == 2058007` from `events_World_Cup.json` in the source events archive. It retains source order and provider IDs for verification. JSON is UTF-8, compact separators, one final newline. The archive and extracted-file SHA-256 values are in `manifest.json`.

`aliases.json` assigns the published starting lineup to the existing fictional club player aliases, followed by participating substitutes sorted by provider ID. Belgium's provider team 5629 maps to display team 4418 (Eastbridge); Japan's 12913 maps to display team 9598 (Northport). Display team IDs are application roles, not claims of source team identity. Aliases are scoped to this match, and do not establish identity across archive matches. No real player names, likenesses or club marks are used in the fan interface.

The adapter scales coordinates to 105 × 68 metres, derives outcomes from provider tags and verifies the 3–2 result. Underlying event outcomes and match chronology are preserved, not disguised as newly collected data. The UI adds comparison statistics, a goal timeline, contextual playback and fictional presentation.

Independent expectations in `tests/test_gi.py`: 890 first-half and 792 second-half actions; 26 participants; 24/9 shots; 572/432 passes; 501/377 completed passes; 71/55 unsuccessful passes. Goal order: Northport, Northport, Eastbridge, Eastbridge, Eastbridge.

[FIFA full-match replay](https://www.plus.fifa.com/en/content/belgium-v-japan-round-of-16-2018-fifa-world-cup-russia-full-match-replay/91f25d3d-d996-4a3f-a880-5b592de4c13e). This is an external source link: no video has been downloaded or redistributed, and video offsets remain unverified.
