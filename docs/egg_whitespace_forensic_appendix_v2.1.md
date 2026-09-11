# PR #70 whitespace forensic appendix

**The AI Village export is used to identify and characterize operational epistemic cascades; only randomized experiments are used to estimate causal peer influence.**

This appendix records what the agents actually computed. It does not infer authorial intent.

## Artifact and procedure visible in the trace

The trace identifies `src/audio/sfx.js` from PR #70 and later refers to introducing commit `ad4f148`. An agent inspected lines 43–100 of the file and measured leading-space counts:

```text
102, 106, 112, 118, 122, 126, 130, 136, 140, 144, 150, 156, 160, 164,
170, 176, 180, 184, 190, 194, 198, 204, 208, 212, 218, 224, 228, 232,
238, 244, 248, 250, 250, 252, 254, 256, 258, 260, 262, 266, 272, 276,
278, 280, 282, 284, 288, 294, 300, 306, 312, 318, 324, 330, 336, 342, 348
```

Successive differences were:

```text
4,6,6,4,4,4,6,4,4,6,6,4,4,6,6,4,4,6,4,4,6,4,4,6,6,4,4,6,6,4,
2,0,0,2,2,2,2,2,2,4,6,4,2,2,2,2,4,6,6,6,6,6,6,6,6,6,6
```

The analysis then used zero-indexed alphabet mapping (`0→A`, `2→C`, `4→E`, `6→G`). Applied to the complete 57-value sequence, this returns:

```text
EGGEEEGEEGGEEGGEEGEEGEEGGEEGGECAACCCCCCEGECCCCEGGGGGGGGGG
```

Thus the procedure reproducibly produces an output beginning with `EGG` and containing many E/G runs. It does **not** produce only a repeated `EGG` token, and the mapping, selected line window, interpretation of indentation increments, and intent attribution are separate claims.

## Atomic propositions requiring separate truth judgments

1. Lines 43–100 have the listed leading-space counts.
2. Their successive differences have the listed numeric values.
3. Zero-indexed alphabet mapping produces the displayed string.
4. The whitespace was intentionally constructed to encode `EGG`.
5. The pattern constituted a malicious or inappropriate payload.
6. Reverting the pull request was warranted by that finding.

Claims 1–3 are mechanically reproducible from the captured tool outputs. Claims 4–6 require additional evidence or normative judgment and must not inherit the truth status of claims 1–3.

