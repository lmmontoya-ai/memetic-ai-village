# Dataset access and public files

The dataset is provided by [AI Digest / AI Village on Hugging Face](https://huggingface.co/datasets/aidigestorg/ai-village) under its own research terms. The repository's MIT license covers original project code and documentation; it does not grant rights to the upstream data or third-party excerpts.

## Pinned source

- Dataset: `aidigestorg/ai-village`
- Revision: `504ae8dc5fd254917c4ccbb071d932ad93b3584c`
- Upstream modification time recorded in the manifest: 2026-07-26 11:44:27 UTC
- Original local retrieval: 2026-08-14 UTC
- Scope: ten exported JSONL tables and their documentation, about 3.25 GiB compressed

The [manifest](../data/raw_manifest/dataset_manifest.json) records file sizes, local SHA-256 hashes, upstream LFS hashes where available, row counts, software versions, and the revision. Initial retrieval excluded screenshots. A later development-case step downloaded 25 selected screenshots. Those files remain local and ignored; the original claim that this workspace contains no downloaded screenshots was outdated.

## Upstream conditions

The publicly visible access conditions, checked September 11, 2026, require research/analysis use, no training or fine-tuning without written permission, no attempted re-identification, citation of AI Digest / AI Village, and notification of publications. Access is reviewed by AI Digest. Consult the [upstream page](https://huggingface.co/datasets/aidigestorg/ai-village) for the actual conditions.

A repository review does not itself send a publication notification. This preparation has not contacted AI Digest or changed repository visibility. The dataset provider warns that its redaction is best effort. Discovered credentials must not be used or copied into public issues.

## What this public repository includes

The project publishes original analysis code, methods, selected aggregate counts, source-file hashes, non-sensitive evidence identifiers, and a small synthetic YAML counterexample. The narrative result describes an incident without reproducing a transcript. This is the project's publication policy, not an assertion that upstream terms permit arbitrary redistribution of derived records.

Raw tables, bulk text, screenshots, full action traces, filled reviewer sheets, model responses, discarded runs, and blinding keys remain local. Generated research directories are ignored by default. New public outputs need explicit allowlist entries and content review. `scripts/export_public_results.py` selects named aggregate fields; `scripts/check_repository.py` checks the proposed public files and common credential patterns.

Keep tokens in the local Hugging Face credential store or environment. `.env` files and private-key files are ignored. The checks reduce accidental publication risk but cannot certify all free text as safe. Minimized excerpts beyond the current reviewed outputs require a separate review of content and applicable data terms.

## Missing telemetry

The pinned snapshot omits exact recipient prompts and raw LLM-call logs. It also lacks the `villages`, `village_goals`, `summaries`, upstream `manifest.json`, and convenience transcript files described by a later dataset-card schema. Provider-shaped response objects are outputs, not authoritative prompt snapshots. The private scaffolding is represented here only by the supplied change log.

These omissions limit claims about prompt inclusion, shared goals, memory-writing mechanisms, and causal influence. The current dataset card may describe files added after this pinned revision. Use the manifest and inventory when evaluating this study's actual coverage.
