# CounterPress demo guide

CounterPress turns recorded football events into comparisons that you can check
against their source evidence. This guide is for demo users and hackathon judges.
The match, teams and players are synthetic. The replay covers a ten-minute
second-half segment, with Eastbridge trailing Northport 0–1.

**[Open the live CounterPress demo](https://counterpress.icyplant-0eb80d8e.eastus.azurecontainerapps.io/).**
No installation, sign-in, Azure account or API key is needed. The app can take
around 30 seconds to wake after being idle; allow it to load before presenting.

## Five-minute walkthrough

### 1. See the change

Keep **Replay scenario → Recovery increase** and the starting preferences:
**Viewer 1**, **Analyst**, **English**, **Any club**, **All contributors**,
**Balanced**, and **Card budget → 1**.

The replay starts paused at **48:00**. Click **Go to comparison** to jump to
**58:00**. Eastbridge's high recoveries increase from **1 to 4** across the two
five-minute windows. These are counts, not success rates.

![Hosted recovery comparison with pitch and evidence controls](screenshots/azure-hosted-recovery-en.png)

### 2. Check the evidence

Click **Show evidence**. Select a pitch marker or an event in the evidence table
to inspect its exact source record. With **All contributors** selected, five
qualifying recoveries support the comparison: one in the previous window and
four in the latest window. The table identifies the time, player, location and
event revision. Nearby passes and duels provide context; they do not automatically
count as recoveries.

A high recovery means established open-play control in the attacking third,
at **x ≥ 70 metres**. Winning a duel alone is insufficient. Pitch markers show
recorded locations, not continuous tracking or inferred player movement.

### 3. Try a control

Choose **Replay scenario → No-increase control**, then **Go to comparison**.
The recovery counts are **1 to 1**, so there is no recovery-increase card.
With **Balanced** selected, the main card can instead show **Possession without
progression decreased**. This is expected: eligible stories from other detectors
can appear in the main card and recap. A control for one metric is not necessarily
a control for every metric. Metric focus ranks stories; it is not an exclusive filter.

### 4. Compare pressure and escape

Choose **Pressure and escape shift**, set **Metric focus → Pressure exposure**,
then click **Go to comparison**. Pressure exposure rises from **3/6 to 6/6**
observed build-up episodes. Switch **Metric focus → Escape under pressure** to
inspect the fall from **3/3 to 1/6** pressured episodes with a qualifying escape.
Use **Show evidence** to inspect the episode records and denominators.

Scroll down and expand **Catch up on this segment** to see the cited stories
together. **Open cited evidence** opens the exact evidence revision as JSON in
a new tab. JSON is the structured source data; return to the demo tab to continue.

![Pressure and escape segment recap with evidence citations](screenshots/segment-recap-en.png)

### 5. Change the presentation

Choose **View → Casual** and **Language → 简体中文**. The explanations become
shorter and the main interface switches to Simplified Chinese. The same numbers,
time windows and evidence remain. Reopen the recap after a preference change.
Choose **English** and **Analyst** to return to the detailed view.

## Replay controls

| Control | What it does |
| --- | --- |
| Play / Pause | Advances or holds your replay position. |
| Reset arrow ↺ | Returns to 48:00 and clears the open evidence selection. |
| Timeline slider | Seeks to a time and pauses playback. Rewinding shows the facts available then. |
| Speed | Selects 1×, 10×, 30× or 60× playback. It does not change event times or calculations. |
| Go to comparison | Jumps to 58:00, when both comparison windows have finished. |
| Replay scenario | Loads another synthetic example and resets the clock to 48:00. |
| View latest corrections | Appears only when later corrections exist; jumps to the latest available revision time. |

The clock is match time. **Facts through** shows the cutoff of the facts currently
loaded; it can briefly lag the moving playhead while a request completes. Each
viewer controls their own replay position.

## Choose your viewpoint

| Preference | How to use it |
| --- | --- |
| Local viewer | Switches between two temporary preference profiles. Viewer 1 starts in Analyst; Viewer 2 starts in Casual. These are not user accounts. Reloading resets them. |
| View | Analyst exposes more metrics, event context and evidence detail. Casual gives a shorter explanation, with evidence available on demand. |
| Language | English or Simplified Chinese. Team names and player IDs remain unchanged. |
| Club preference | Prioritizes eligible stories about a club; it does not filter out all other clubs. |
| Player contribution | Requires recorded involvement for the chosen player and can highlight a subset of evidence. Team totals remain unchanged. |
| Metric focus | Prioritizes an eligible metric. Selecting a focus cannot create a story that fails its evidence rules. |
| Card budget | 1 allows one main card; 0 hides the card and recap. The recap can contain up to four cited stories when enabled. |

Preferences stay selected when you change scenarios. For a predictable demo,
return to **Any club**, **All contributors**, **Balanced**, and **Card budget → 1**
before exploring another scenario.

## Other scenarios to explore

Use **Go to comparison** after selecting a scenario. These expected values refer
to the original comparison at **58:00**, with all contributors selected.

| Scenario | Suggested metric focus | What to look for |
| --- | --- | --- |
| Recovery increase | High recoveries | Eastbridge: 1 → 4 high recoveries. |
| No-increase control | High recoveries | 1 → 1; no recovery-increase card. |
| Pressure and escape shift | Pressure exposure / Escape under pressure | Exposure 3/6 → 6/6; escape 3/3 → 1/6. |
| Pressure and escape control | Pressure exposure / Escape under pressure | No eligible pressure/escape change. |
| Possession without progression | Possession without progression | Qualifying sustained possessions without progression: 1/6 → 4/6. |
| Progression control | Possession without progression | 1/6 → 1/6; no eligible increase for this metric. |
| Player recovery share increase | Player recovery share | Player eb04's share rises from 1/4 to 3/4; the team has four high recoveries in each window. |
| Player recovery share control | Player recovery share | No eligible player-share increase. |

For a player example, select **eb04** in **Player recovery share increase**.
Selecting **eb09** in that scenario does not credit that player's preceding duel
wins as controlled recoveries. Player involvement depends on the selected scenario;
the same ID can have different contributions in another synthetic example.

## Read the comparison correctly

The windows are **(48:00, 53:00]** and **(53:00, 58:00]**: exclude the start,
include the end. An event exactly at 53:00 belongs to the first window. An event
exactly at 58:00 belongs to the second. The pitch is **105 × 68 metres**, with
attacking direction normalized toward increasing x.

Evidence records distinguish when an event occurred from when its revision became
available. A correction can update or withdraw an earlier insight while retaining
the earlier evidence for historical inspection. If a prepared correction history
is present, **View latest corrections** exposes it. The public interface has no
button for submitting corrections; ask the presenter to prepare that optional
demonstration using the [history runbook](history.md).

Pressure is a proxy based on recorded duel involvement in observed episodes.
Recovery counts, escape fractions and possession progression do not establish
causality, tactical effectiveness, player quality or real-world predictive accuracy.
The recap summarizes eligible comparisons in this segment, not the whole match.

## What to tell the judges

Suggested opening:

> “CounterPress shows how a football insight can remain traceable to recorded
> events. We replay a synthetic match, compare two windows, and let viewers inspect
> every claim's evidence. The same facts support different languages and viewing
> preferences. Corrections can update or withdraw dependent insights.”

The current Microsoft platform roles are:

| Component | Current status and role |
| --- | --- |
| Azure Container Apps | Hosts the React interface and FastAPI backend over HTTPS; can scale to zero while idle. |
| Azure Cosmos DB | Stores shared event history, publication revisions and evidence; recovery after a cloud replica restart has been verified. |
| Azure Container Registry and managed identities | Stores private container images and authorizes image pulls and scoped database access without putting those credentials in the browser. |
| Azure OpenAI and Microsoft Agent Framework | Wording and bounded review workflows are implemented and separately live-tested. They are **not enabled in this hosted demo**; its narratives use verified factual templates. |

GitHub Actions checks tests, builds and container smoke behaviour. The current
browser receives snapshots by HTTP polling. Event Hubs ingestion, Web PubSub
delivery, automated Azure deployment and broader evaluation are subsequent work.
See the [current architecture](deployment.md#deployed-azure-architecture) and
[Cosmos verification](verification/cosmos-durability.json) for technical evidence.

## If something looks wrong

| What you see | What to do |
| --- | --- |
| Loading on first visit | Allow around 30 seconds for startup. If an error appears, click **Retry**. |
| Let the comparison unfold | Click **Go to comparison**, or play through 58:00. |
| Cards hidden | Set **Card budget → 1**. |
| No qualifying contribution / No recorded involvement | Choose **All contributors**, or choose a player with relevant records in that scenario. |
| No increase / No eligible rate change / No eligible player increase | This can be the expected control result. Check the scenario and metric focus. |
| Insight withdrawn | A correction invalidated that story. Rewind to inspect earlier facts, or view later corrections if available. |
| Recap closed after a change | Expand **Catch up on this segment** again; changes reset the open recap. |
| Evidence table wider than your phone | Scroll the table horizontally, or use a desktop for the detailed walkthrough. |

Before presenting, open the app, run the recovery comparison once, then reset to
48:00. After the demo, close unused demo tabs: paused tabs still poll for updates.
For a local backup, follow [local interface startup](interface.md#start-locally).
No Azure setup is required to run the default local demo.
