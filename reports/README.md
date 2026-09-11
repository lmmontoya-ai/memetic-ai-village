# Public reports

| File | Meaning |
| --- | --- |
| [Preliminary results](machine_annotation_preliminary_v2_2.md) | Current machine-annotation findings, denominators, and limitations |
| [Public aggregate JSON](public_results_v2_2.json) | Numeric aggregates and hashes of local evidence; no raw labels or transcripts |
| [YAML truth audit](yaml_blank_line_truth_audit_v2_2.json) | Reproducible general syntax counterexample; original workflow root cause unresolved |
| [Original freeze record](pre_annotation_freeze_v2_2.json) | Preserved v2.2 hashes, not a claim that current files still match |
| [Current original-freeze verification](verification_v2_2.json) | Fails because two recorded file hashes differ |
| [Protocol integrity review](protocol_integrity_review.json) | Dated record of that drift and current file hashes |
| [Repository review](repository_review.md) | Engineering checks and remaining research work |

Detailed JSON containing excerpts, historical proxy reports, audit samples, and other generated outputs remain local. The allowlist in `.gitignore` controls which reports enter public Git. A generated report is a result at a particular run, not independent validation of its own assertions.
