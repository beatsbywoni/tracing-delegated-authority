# Replication package: Tracing Delegated Authority

Provision-level case study of the administrative rules of the Ministry of Education (Korea), snapshot 15 August 2026.

## Rebuild every count in the article

    python reproduce.py results_check

Requires Python 3.9+ and the standard library only. The script reads the stored reader outputs under `work/`, writes `provisions.csv`, `tables.json` and `checks.json` into the (new, empty) output folder, and compares the rebuilt numbers with those printed in the article (`expected_numbers.json`). `results/` holds the output of this command as run before release. No model is called: this is a deterministic re-aggregation. Calling the models again will not necessarily reproduce the same labels.

## How the files are distributed

The repository root holds this README, `LICENSE`, `reproduce.py`, `expected_numbers.json` and `MANIFEST.tsv`. Everything else (`work/`, `index/`, `results/` and the packet builders) is split across `data_part01.zip`, `data_part02.zip` and so on, each under 10 MB. Unzip all parts into the repository root; the parts do not overlap. `MANIFEST.tsv` lists every file with its role and SHA-256 hash, so the unpacked tree can be checked. Parts 01 to 04 contain everything needed to run `reproduce.py`; parts 04 to 06 also hold `work/s2/` (the superseded first packets and outputs) and `index/` (the statute index used to build packets), which document the inputs and the correction.

## Keys in `tables.json`

`table1` = article Table 3; `table3_kind` = Table 4; `table2_final_labels` = Table S2; `sensitivity` = Table S3; `refutation` = Table S4; `decisions` = Section V.D and Table S5; `table4_addressee_reader1` = addressee counts in V.E; `purpose_clause` = first remedy in VII.E; `screen` = first-stage screen in IV.C.

## Decision rules implemented in `reproduce.py`

- Second-stage label: agreed label of reader 1 (Claude Sonnet) and reader 2 (GPT-6); for the 393 discordant provisions, the class chosen by at least two of three readers (reader 3: Claude Opus). In 63 provisions all three readers chose different classes; these records are marked `adjudicator_only` and carry the third reader's label. Eight received a break label from the third reader and are excluded from the candidate, not-refuted and core sets (they remain in `set_either` and `set_both` only if the second-stage readers' own labels qualify). The remaining 55 have non-break labels; those labels are retained in the descriptive distribution but are not majority decisions.
- Packets changed by the extraction fix (`work/s2c/changed_ids.json`, 708) use the re-read outputs (`work/s2c/out`, `work/s2c/gpt`); others use the first outputs (`work/s2b`).
- Refutation: Claude Opus outputs from two rounds (`work/refute/out`, `work/refute/out2`), stronger refutation kept; GPT-6 outputs in `work/gptref`. Provisions whose refutation task had no statute file are flagged `refute_statutes_supplied = 0`.
- Sets: `set_either`, `set_both`, `set_candidate` (agreement or majority), `set_not_refuted` (no refuted or partly refuted result), `set_core` (both refutation results `not_refuted` and statute text supplied).

## Layout

- `work/s1/` first-stage screen (instructions, inputs, outputs of Claude Haiku and GPT-6)
- `work/INSTRUCTIONS.md` second-stage instructions v0.2; `work/INSTRUCTIONS_v0.1.md` pilot version; `work/pilot_*`, `work/out/` pilot
- `work/s2/` first extraction (superseded packets, kept for the record); `work/s2c/s2_packets.jsonl` final packets
- `work/s2b/` second-stage outputs on the first packets; `work/s2c/` re-read outputs, discordant list, third-reader outputs
- `work/refute/` refutation instructions, Claude Opus tasks (`tasks/` round 1, `tasks2/` round 2 with all statutes cited in the rule), statute texts, outputs; `work/gptref/` GPT-6 refutation and case outputs, with GPT-6 refutation tasks in `work/gptref/tasks/`
- `work/cases/` five-provision analysis (instructions v1.1, Claude Opus outputs; `out_v10` superseded)
- `work/dec/` decision cross-check (search hits, matched pairs, blind packets, outputs). Raw decision texts are not redistributed; they can be retrieved from the National Law Information Center Open API by the identifiers in `work/dec/hits.json`.
- `work/origin/` kind-of-rule classification
- `index/` statute and decree article index built by `build_index.py` / `build_index_ext.py` from raw API responses. The raw responses are not distributed because their request URLs may contain an access key.
- `build_articles_v2.py`, `build_s2_v2.py` packet builders (need `index/` moved to `work/`)
- Helper scripts inside `work/` (`gen*.py`, `mk*.py`, `w*.py`) were used by readers to write their own labels to JSONL. They contain the labels as literal strings and do not perform inference; `check_*.py` and `agree.py` are completeness and agreement checks used during reading.

`MANIFEST.tsv` lists every file with its role and SHA-256 hash.

## Licence

Data: CC BY 4.0. Code: MIT.
