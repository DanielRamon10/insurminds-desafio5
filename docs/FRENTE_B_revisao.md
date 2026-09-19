# Review of the workstream B spreadsheet

A record of what came back from the domain expert, what was corrected and what still
needs confirmation. The thresholds themselves are all usable — no number was changed.

**Received on:** August 25, 2026
**Source:** `FRENTE_B_limiares_e_segurados_preenchido.xlsx`
**Result:** `data/regras.yaml`

---

## 1. One-row offset in the thresholds table

The values were filled in **one row above** their corresponding criterion. The first pair
of values landed on the header row, and every subsequent pair ended up on the previous
criterion's row.

The diagnosis is unambiguous because **the units line up perfectly** once everything is
shifted one row down — "60 km/h" can only be a wind gust, "800 J/kg" can only be CAPE. No
value was invented or guessed: they were only repositioned.

### How it was corrected

| Criterion | Unit | Watch | Alert |
| --- | --- | --- | --- |
| Rainfall accumulated over 24 h | mm | 40 | 60 |
| Rainfall in the heaviest hour | mm/h | 15 | 30 |
| Maximum gust | km/h | 60 | 80 |
| CAPE (lightning) | J/kg | 800 | 1,500 |
| CAPE (hail) | J/kg | 1,500 | 2,500 |
| Freezing level height | m | below 3,800 | below 3,200 |

The rationales followed the same offset and were realigned along with the values. Each
one lives in the `porque` field of `regras.yaml`, ready for the report.

### Duplicate resolved

The last two filled-in rows carried the same pair of values for the freezing level height
(3,800 / 3,200 m), with equivalent rationales. The wording of the last one was kept, as
it is the more complete: *"...the greater the chance of hail reaching the ground without
melting. This indicator must be analysed together with CAPE and the storm's other
conditions."*

---

## 2. Resolved: hail + home policy

The recommendation received for **hail + home** is about a vehicle:

> "If possible, keep the vehicle in a garage or under sturdy cover and avoid leaving it
> exposed to the weather until the storm is over."

That describes the **auto** policy, which already has its own recommendation on the
following row. The other six are correct and specific.

Wording proposed during the review, for the home policy:

> "Bring in objects that could be damaged in uncovered areas, avoid staying under
> skylights, translucent roof tiles or large panes of glass, and keep away from windows
> while hail is falling."

**Approved by the domain expert on August 25, 2026** and live in `regras.yaml`. For the
record on attribution: the thresholds and the other six recommendations are the expert's
work; this sentence was written during the review and validated by him.

With that, workstream B has no open definition items left.

---

## 3. An unplanned gain: composite events

The rationales carried information the spreadsheet did not explicitly ask for — and it
improves the rule:

- **Hail:** *"The criterion must be combined with instability (CAPE)"*
- **Lightning:** CAPE indicates *"an environment favourable to storms"*, not the discharge
  itself

In other words, neither lightning nor hail should be decided by a single number.
`regras.yaml` reflects this through the `combinacao` field:

| Event | Combination | Meaning |
| --- | --- | --- |
| Heavy rain | `qualquer` | one criterion reaching the threshold is enough |
| Strong wind | `qualquer` | single criterion |
| Lightning | `todos` | confirmed thunderstorm **and** sufficient CAPE |
| Hail | `todos` | high CAPE **and** low freezing level |

For lightning, the **WMO thunderstorm code** criterion (95, 96 or 99) was added. It wasn't
in the spreadsheet because it is a detail of the data source, not of insurance. Without
it, high CAPE on its own would classify any unstable summer afternoon as lightning.

---

## 4. Policyholders tab

No comments recorded across the 45 rows — the base was accepted as delivered.

---

## Status of the workstream B tasks

| Task | Status |
| --- | --- |
| B.1 Policyholder base | done — 45 policyholders, base accepted without reservations |
| B.2 Event classifier | thresholds and combinations defined; still to be implemented in code |
| B.3 Rules engine | `data/regras.yaml` — editable without touching Python |
| B.4 Justify every threshold | done — six rationales, ready for the report |
