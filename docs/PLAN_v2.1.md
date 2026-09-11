# Part I execution plan v2.1

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

This plan records the amendments frozen after the v2 reconstruction and before human annotation or holdout semantic inspection.

| Amendment | Status | Output |
| --- | --- | --- |
| Reinterpret author shuffle | Complete | `author_autocorrelation_diagnostic_v2_1.*`; excluded from Gate 1 |
| Fixed-author local null | Complete | 4,744 candidate-local alternatives with unchanged author sequence |
| Hard-control prioritization | Complete | 7 hard controls used; 23-candidate shortfall explicit |
| Source-linked retrieval channel | Frozen and run on development data | 85,520 rule matches; capped 60-case development sample |
| Atomic claims | Complete as blank extraction schema | 120 message-level extraction units; no supplied propositions |
| Evidence-lineage diversity | Complete as blank annotation schema | lineage, observation, and inference independence |
| Action dependency | Complete as blank annotation schema | semantic relevance, consistency, dependency, A0–A6 execution |
| Memory distinction | Complete as blank annotation schema | recorded claim separated from later behavioral use |
| Independent truth audit | Complete as review scaffold | 14 atomic claims across three featured incidents |
| EGG forensic appendix | Complete | exact whitespace counts, differences, mapping, and claim decomposition |
| Staged annotation | Complete | 60 packets per stage; 12-case A0 full-trace audit sample |
| Structural audit | Complete as blank reviewer schema | separate from semantic reliability |
| Clustered reliability | Implemented | AC1 primary; raw agreement and kappa diagnostic; cluster bootstrap CIs |
| Layered Gate 1 | Frozen | Gates 1A–1E reported separately |

## Current non-substantive diagnostics

- The revised 60-unit set contains 30 lexical candidates, 20 controls, and 10 placebos.
- Seven candidates have an adequate same-artifact or same-code hard control; 23 do not.
- Revised exact-response eligibility contains 51 `eligible`, 6 `source_acknowledged`, and 3 `ineligible` rows, with no observed prompt inclusion.
- Revised action windows contain 28,505 raw events, including 3,909 visual-state candidates.
- All 60 units have before/after memory snapshots.
- The third-party extractor returns 95 structural candidates across 13 units; none is semantically validated.
- The source-linked channel's 60-case development sample contains 23 agent-level attribution cases, 20 direct-request cases, 15 artifact-handoff cases, and 2 unique-phrase cases. These remain retrieval candidates, not validated L2 events.
- The holdout remains semantically unopened.

## Human sequence

1. Complete and freeze Stage A claim extraction.
2. Populate and freeze Stage B comparisons from the extracted claims.
3. Complete Stage C operational annotation, including the prespecified A0 audit.
4. Complete Stage D memory and restatement annotation.
5. Complete the independent structural audit and featured-case truth audit.
6. Compute cluster-bootstrap semantic reliability.
7. Revise the development codebook once, freeze all rules, and only then open the holdout.

