# France–Croatia 2018 GI source

This directory contains the 1,462 original event records for Wyscout match **2058017**, selected from the World Cup events archive. It is independent of CounterPress's synthetic highlights and contains no footage.

Attribution: **Luca Pappalardo and Emanuele Massucco**, Wyscout football event dataset.

- Events: https://doi.org/10.6084/m9.figshare.7770599
- Matches (used for lineup-based alias assignment): https://doi.org/10.6084/m9.figshare.7770422
- Licence: [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
- Dataset-specific licence metadata: https://api.figshare.com/v2/articles/7770599 and https://api.figshare.com/v2/articles/7770422
- Paper: https://www.nature.com/articles/s41597-019-0247-7

Changes: selected this match; serialized its records as compact JSON. The reader scales percentage positions to a 105 × 68 metre display in the acting team's attacking direction, orders actions by period/time/source order, and derives outcome categories from tags. Raw provider fields remain in the fixture. `manifest.json` records source archive and fixture SHA-256 hashes.

`aliases.json` freezes provider player ID → fictional display alias assignments. Starting lineups use each team's 11 existing dashboard names; additional participants receive distinct substitute labels. These aliases are not the real players' identities and do not imply their involvement in the synthetic Matchday stories. Provider IDs remain intact for traceability. No player photographs, likenesses or club marks are included.

The public data licence does not license broadcast footage. GI links to the official FIFA replay; there are no downloaded clips or verified video offsets. The previously investigated StatsBomb files under ignored `var/` are not used by this application or included here.
