# Repository review, September 11, 2026

The repository can support a public engineering and methodology review. Its results remain exploratory. Independent human validation, detector evaluation, and causal experiments are unfinished. The original v2.2 freeze also has two unresolved historical hash mismatches, documented rather than overwritten.

## Findings addressed

| Finding | Change |
| --- | --- |
| README omitted the current result and assumed existing local artifacts | Added objective, motivation, method, results with denominators, limitations, navigation, and separate public/data reproduction paths. |
| Restricted machine outputs and later-stage labels could enter Git | Changed generated directories to explicit public allowlists; kept original local files intact. Added a checker that also rejects force-staged research files. |
| Field inventory contained samples of nested raw text | Removed the sample-values column and its collection in the generator. Preserved the original inventory locally and added a synthetic nested-content regression test. |
| Tests assumed private data were present | Marked 11 data integration tests and made them opt-in with `--run-data`; they fail on missing inputs when requested. Public tests run without those files. |
| Atomic-claim counts included unused template rows | Corrected counts from 360/360 to 289/308 populated claims. Reran aggregation from the same saved labels; the one-episode finding is unchanged. Added a regression test. |
| Machine extraction was described more strongly than implemented | Disclosed the three-claim cap, mixed model provenance, interactive Sol workflow, and incomplete human adapter. |
| Saved original-freeze verification was stale | Reran it and preserved the resulting failure. Recorded original and current hashes in the integrity review without changing the original freeze. |
| Regeneration could overwrite completed annotations | Added CLI checks before broad rebuilds and Stage B recompilation; tested that populated human labels remain intact. |
| Verification could print failure but exit successfully | Made top-level failed/blocked CLI results return a nonzero exit code. |
| Public result reproduction depended on restricted label files | Added an aggregate-only exporter with input hashes and a data-free YAML syntax demonstration. |
| Missing public project metadata and CI | Added MIT license, upstream-data notice, citation metadata, contribution instructions, Python reference version, and a Linux/Windows CI matrix for Python 3.11 through 3.13. |
| PyYAML was only an indirect dependency | Declared it directly in the development environment used by the syntax audit. |

## Validation

The original local suite passed all 41 tests before changes. Final checks used Windows, Python 3.11.15, and uv 0.9.26.

| Check | Result |
| --- | --- |
| All tests with existing approved local data | 55 passed, including all 11 data integration tests |
| Separate checkout containing only proposed public files | 44 passed; 11 data integration tests explicitly skipped |
| Locked environment installation in the public checkout | Passed without dataset access or API credentials |
| Ruff over `src`, `tests`, and `scripts` | Passed |
| Public working-file and Git-index checks | Passed for 89 proposed files; original protocol drift reported separately |
| Local Markdown file links and credential-pattern scan | Passed within the limits of the checker |
| Data-free YAML syntax counterexample | Passed with PyYAML 6.0.3 |
| Source distribution and wheel builds | Passed in local and public-only checkouts; restricted paths absent from the inspected source distribution |
| Remote Linux/Windows CI matrix | Configured, not run remotely during this review |
| Original v2.2 research freeze | Failed on the two documented hash mismatches |

The public checkout was populated from tracked and unignored working files into a separate temporary Git repository. Files were staged and checked out through Git to exercise the line-ending rules. It contained no raw data, local labels, or copied development environment. Tests were rerun after removing the inventory's sample-values column.

`village-pipeline v2-2-verify` was rerun and correctly failed only `frozen_hashes_match`. Both the specification and holdout plan match the original freeze. The compiler and codebook do not; the codebook includes an August 17 development amendment. The old bytes for a complete compiler/codebook comparison have not been recovered.

The public repository checker distinguishes two questions: whether the proposed public files match the reviewed versions, and whether those versions satisfy the original research freeze. It can pass the former while reporting `original_freeze_mismatch` for the latter. The original hashes are retained in [the freeze record](pre_annotation_freeze_v2_2.json); current hashes are in [the integrity review](protocol_integrity_review.json).

## Remaining research work

Before new human or holdout annotation, reconcile the protocol amendments and hash history, remove the extraction cap, finish the v2.2 human Stage C/D and reliability path, and record a corrected version. Independent semantic review and structural auditing remain pending. The separate source-linked development channel has not been annotated. The holdout remains unavailable for confirmatory interpretation until those steps are resolved.

The 60-unit development sample yielded only 11 proposition-comparable units and six effective clusters for Stages B-D. One of seven hard controls was comparable. These numbers do not establish detector validity or population prevalence. The only positive incident has a documented shared-artifact alternative explanation. See [the reviewer guide](../docs/reviewer_guide.md).

## Limits of this review

This review does not certify a retrospective preregistration, independently validate machine labels, replay both model runs, or establish causal influence. A full rebuild from an empty data directory and a fresh multi-gigabyte download were not performed. Remote CI execution remains pending a push containing the workflow.

The public-file checker found no matching credential patterns in the proposed files; pattern matching is not a complete privacy audit. The public version excludes raw evidence and populated annotations, so an independent recheck of the episode requires separately authorized dataset and label access.

Most project files were untracked when this review began. Changes remain in the working tree for the owner's review. Nothing was committed, pushed, published, or sent to AI Digest by this task. Existing raw data, labels, discarded-run archives, and prior user work remain local.
