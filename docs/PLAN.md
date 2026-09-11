# Historical initial research plan

This is the preserved initial plan, including proposed milestones and retired v1 constructs. It is not a completion record or the current methodology. See [the README](../README.md), [the reviewer guide](reviewer_guide.md), and [the metric-retirement note](legacy_metric_retirement.md).

\# AI Village Memetic-Spread Project Plan

> **LEGACY V1 — INVALID PROXY.** This is the original plan and is retained only to preserve the
> decision trail. The active observational contract is `research_spec_v2.md`.



\*\*Working period:\*\* August 14–September 30, 2026

\*\*Primary decision date:\*\* September 7, 2026

\*\*Primary outputs:\*\*



1\. A feasibility assessment answering whether AI Village supports reliable measurement of social transmission.

2\. A LessWrong/Alignment Forum post presenting the threat model, pilot evidence, limitations, and preregistered research agenda.

3\. A clean foundation for a subsequent ICML project.



\## 1. Project objective



Determine whether the AI Village data can support defensible claims about the following sequence:



\[

\\text{peer exposure}

\\rightarrow

\\text{expressed adoption}

\\rightarrow

\\text{behavioral expression}

\\rightarrow

\\text{memory incorporation}

\\rightarrow

\\text{retransmission or persistence}.

]



The feasibility pilot is successful when we can reconstruct this sequence for enough episodes, with enough annotation reliability, to justify a larger quantitative and experimental study.



The pilot is \*\*not\*\* intended to prove that agents acquired stable misaligned values. It should establish whether safety-relevant beliefs, strategies, norms, and behavioral dispositions can be identified and tracked through communication, memory, and action.



\## 2. Operational definitions to freeze before analysis



These definitions should be written into `research\_spec.md` before searching extensively for examples.



| Term                        | Operational definition                                                                                                                                              |

| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| \*\*Candidate meme\*\*          | A sufficiently distinguishable proposition, strategy, norm, goal, or behavioral disposition that could recur across agents or time.                                 |

| \*\*Seed\*\*                    | The first identifiable expression or demonstration of the candidate meme within the relevant observation window.                                                    |

| \*\*Exposure\*\*                | Evidence that the recipient could actually have received the seed through its prompt context, visible room, shared artifact, memory, or another documented channel. |

| \*\*Adoption\*\*                | The recipient later expresses, endorses, applies, or preserves substantially the same content. Mere topical similarity is insufficient.                             |

| \*\*Behavioral expression\*\*   | An observable decision, tool call, message, artifact, or refusal that implements the candidate meme.                                                                |

| \*\*Memory incorporation\*\*    | The recipient writes the candidate meme, or a recognizable abstraction of it, into persistent memory.                                                               |

| \*\*Retransmission\*\*          | An exposed recipient subsequently communicates or demonstrates the meme to another agent.                                                                           |

| \*\*Persistence\*\*             | The disposition remains detectable after memory consolidation, a substantial context shift, or a new goal.                                                          |

| \*\*Propagation episode\*\*     | A bounded sequence containing a seed, a plausible exposure pathway, a recipient outcome, and an assessment of alternative explanations.                             |

| \*\*High-confidence episode\*\* | The causal ordering is clear, exposure is confirmed or strongly supported, adoption is behaviorally meaningful, and no obvious shared source explains both agents.  |



Every label should describe an \*\*observable phenomenon\*\*. Use “expressed belief” rather than “belief,” and “behavioral disposition” rather than “value,” unless later experiments establish stronger evidence.



\---



\# Phase I: Feasibility and pilot



\## Target outcome by September 7



Produce a \*\*Feasibility Pack\*\* containing:



\* a documented dataset snapshot;

\* a canonical event timeline;

\* an exposure graph with confidence labels;

\* a registry of 50–100 candidate episodes;

\* a hand-labeled pilot set;

\* annotation-reliability results;

\* several fully traced case studies;

\* a list of unresolved data requirements;

\* a written go, conditional-go, or pivot decision.



\## Workstream A: Project setup and research controls



\*\*Dates:\*\* August 14–15



\### Goal



Create a reproducible environment and prevent exploratory observations from silently becoming confirmatory evidence.



\### Requirements



\* Access to the gated dataset and confirmation of its research-use conditions.

\* A private version-controlled repository.

\* A frozen dataset snapshot or manifest.

\* A distinction between exploratory and held-out data.

\* A record of every material definition or threshold change.



\### Tasks



1\. Create the repository structure:



```text

ai-village-memetics/

├── research\_spec.md

├── data/

│   ├── raw\_manifest/

│   ├── interim/

│   └── processed/

├── src/

├── notebooks/

├── annotations/

├── episodes/

├── reports/

└── post/

```



2\. Record:



\* dataset version and retrieval date;

\* table names and checksums;

\* license and publication restrictions;

\* software environment;

\* random seeds;

\* known missing data.



3\. Reserve a confirmatory slice before extensive exploration. A reasonable default is:



\* \*\*80% chronological discovery set\*\*;

\* \*\*20% chronological holdout set\*\*.



The holdout should not be used to invent candidate categories or adjust annotation definitions.



4\. Create a decision log. Every change to the evidence ladder, thresholds, or candidate ontology should include:



\* date;

\* old definition;

\* new definition;

\* reason;

\* whether it was made before or after observing relevant examples.



\### Definition of done



\* A fresh environment can access the frozen snapshot and reproduce a basic dataset inventory.

\* `research\_spec.md` contains the research question, operational definitions, scope, exclusions, and proposed decision thresholds.

\* The confirmatory slice is identified but not inspected.

\* Dataset restrictions and permitted outputs are documented.



\### Verification



\* Run the setup from a clean clone or fresh environment.

\* Confirm row counts and checksums against the saved manifest.

\* Ask another person, or your future self following only the README, to reproduce the initial inventory.

\* Confirm that no held-out records appear in exploratory notebooks.



\---



\## Workstream B: Contact AI Digest



\*\*Send by:\*\* August 15

\*\*Run in parallel with the technical work.\*\*



\### Goal



Resolve the pieces of the deployment that cannot safely be inferred from the public tables.



\### Essential questions



Ask for documentation or access covering:



1\. \*\*Prompt construction\*\*



&#x20;  \* Which messages, events, memories, and artifacts were included in each agent turn?

&#x20;  \* How were recent events selected and truncated?

&#x20;  \* Were summaries or hidden metadata added?



2\. \*\*Visibility\*\*



&#x20;  \* Which rooms and messages could each agent observe?

&#x20;  \* Is historical room membership available?

&#x20;  \* Were messages ever visible globally despite being associated with a particular room?



3\. \*\*Memory\*\*



&#x20;  \* How were memories retrieved?

&#x20;  \* Which memory version was included in each turn?

&#x20;  \* Were memories summarized, filtered, or rewritten outside the visible agent action?



4\. \*\*Versions\*\*



&#x20;  \* Model, system prompt, scaffold, tool, and context-window versions over time.

&#x20;  \* Exact timestamps of material deployment changes.



5\. \*\*Actions\*\*



&#x20;  \* Mapping among model turns, tool calls, screenshots, artifacts, and chat messages.



6\. \*\*Replay\*\*



&#x20;  \* Whether a historical agent state can be approximately reconstructed.

&#x20;  \* Whether controlled counterfactual prompts or prospective experiments could be run.

&#x20;  \* Whether exact raw prompts are available to vetted researchers.



7\. \*\*Publication\*\*



&#x20;  \* What examples may be quoted or reproduced.

&#x20;  \* Whether agent, room, and event identifiers should be anonymized.

&#x20;  \* Whether they would be interested in collaboration or reviewing factual descriptions.



\### Optional requests



\* Existing incident annotations.

\* Known examples of social influence.

\* Historical no-chat or isolated-agent conditions.

\* Internal notes about known data gaps.

\* Access to prospective randomized communication experiments.



\### Definition of done



\* A concise message has been sent containing:



&#x20; \* the project’s research question;

&#x20; \* why AI Village is uniquely relevant;

&#x20; \* essential versus optional data requests;

&#x20; \* the proposed publication sequence;

&#x20; \* a request for a short technical discussion or written clarification.

\* Every unresolved dependency has a documented fallback.



\### Verification



Create a table with these columns:



| Unknown | Why it matters | Requested information | Fallback without it | Fatal to which claim? |

| ------- | -------------- | --------------------- | ------------------- | --------------------- |



The request is complete when every important uncertainty in the exposure and replay process appears in this table.



\---



\## Workstream C: Dataset inspection and data-quality audit



\*\*Dates:\*\* August 14–18



\### Goal



Understand exactly which events, actors, identifiers, timestamps, and relations can be reconstructed.



\### Required audit



For each core table, document:



\* row count;

\* time range;

\* primary and foreign keys;

\* agent identifiers;

\* model and scaffold identifiers;

\* room or channel identifiers;

\* goal identifiers;

\* missingness;

\* duplicate rate;

\* ordering fields;

\* text fields;

\* relationships to other tables;

\* known interpretation uncertainty.



Prioritize:



1\. chat messages;

2\. agent identities and model versions;

3\. goals and assignments;

4\. room membership;

5\. persistent-memory versions;

6\. model/computer-use turns;

7\. tool calls and artifacts;

8\. screenshots;

9\. deployment changelog or human interventions.



\### Required artifact



Create `data\_inventory.md` and a machine-readable `data\_inventory.csv` containing one row per field or table.



\### Definition of done



\* Every core table has a documented schema and interpretation.

\* Join coverage is quantified rather than assumed.

\* At least 20 randomly sampled records from every core table have been manually inspected.

\* Timestamp units and time zones are known and normalized internally.

\* Duplicate and missing-record behavior is understood.

\* Major scaffold and model changes can be placed on the timeline.

\* Unresolved fields are explicitly marked as unresolved.



\### Verification



Run automated checks for:



\* duplicate event IDs;

\* impossible timestamps;

\* messages occurring before their room or agent exists;

\* memory versions preceding their source events;

\* broken agent, goal, and room references;

\* action traces that cannot be connected to a model turn;

\* inconsistent model or scaffold attribution;

\* unexpectedly large gaps in activity.



A single generated report should reproduce the checks and their counts.



\---



\## Workstream D: Canonical event timeline



\*\*Dates:\*\* August 17–22



\### Goal



Represent all relevant activity in a single ordered event model.



\### Required event schema



Each event should contain, where applicable:



```text

event\_id

timestamp

event\_type

actor\_agent\_id

recipient\_agent\_ids

room\_or\_channel\_id

goal\_id

model\_id

scaffold\_version

source\_record\_id

parent\_event\_id

content\_reference

artifact\_reference

memory\_version\_before

memory\_version\_after

visibility\_metadata

```



Recommended event types include:



\* message sent;

\* message received or made available;

\* goal assigned;

\* room joined or left;

\* model response;

\* tool call;

\* tool result;

\* artifact created or modified;

\* memory read;

\* memory updated;

\* human intervention;

\* scaffold or model change.



\### Definition of done



\* At least 95% of relevant chat, memory, goal, and action records map into the canonical event table.

\* Every event retains a pointer back to its raw source.

\* Events are deterministically ordered, including ties.

\* Model and scaffold changes are represented explicitly.

\* A function can retrieve the complete observable history around any message, agent, or goal.



\### Verification



1\. Select at least 20 random agents or goals.

2\. Reconstruct their histories from the canonical table.

3\. Compare them manually against the raw records.

4\. Fully reconstruct at least three known AI Village incidents.

5\. Confirm that another script can regenerate exactly the same ordering and event IDs.



The timeline is not complete if it relies on prose interpretation that cannot be regenerated from code.



\---



\## Workstream E: Exposure graph and visibility reconstruction



\*\*Dates:\*\* August 19–25



\### Goal



Determine whether and when one agent could have influenced another.



\### Exposure representation



Create a directed temporal edge:



\[

e = (s, r, m, t\_a, c)

]



where:



\* (s) is the source agent;

\* (r) is the potential recipient;

\* (m) is the message, artifact, or demonstrated behavior;

\* (t\_a) is the earliest time it became available;

\* (c) is confidence in actual exposure.



\### Exposure-confidence levels



| Level         | Definition                                                                               |

| ------------- | ---------------------------------------------------------------------------------------- |

| \*\*Confirmed\*\* | The exact item appears in the recipient’s raw prompt or recorded retrieved context.      |

| \*\*Probable\*\*  | Documented context-construction rules imply it should have been included.                |

| \*\*Possible\*\*  | The recipient had channel access, but truncation or retrieval makes inclusion uncertain. |

| \*\*Ruled out\*\* | The item occurred too late or was not visible to the recipient.                          |

| \*\*Unknown\*\*   | Available data cannot determine visibility.                                              |



Do not collapse “possible channel access” into “exposure.”



\### Required output



\* `exposures.parquet`

\* `visibility\_rules.md`

\* a function such as:



```python

could\_observe(

&#x20;   recipient\_id,

&#x20;   source\_event\_id,

&#x20;   decision\_timestamp

) -> ExposureAssessment

```



\### Definition of done



\* Visibility rules are documented for every relevant communication channel.

\* Exposure confidence can be computed reproducibly.

\* The graph distinguishes availability from confirmed prompt inclusion.

\* Time ordering prevents future events from influencing earlier decisions.

\* Known room and membership changes are respected.

\* The percentage of events in each confidence category is reported.



\### Verification



\* Manually audit at least 50 proposed exposure edges across different rooms, dates, models, and scaffolds.

\* Include at least 20 negative cases where exposure should be impossible.

\* Run a future-to-past test: the pipeline must assign zero confirmed exposure edges from later messages to earlier decisions.

\* Where raw prompts are available, compare inferred exposure with actual context inclusion.

\* Investigate every systematic disagreement between inferred and actual exposure.



\---



\## Workstream F: Candidate propagation discovery



\*\*Dates:\*\* August 23–31



\### Goal



Construct a diverse registry of 50–100 plausible propagation episodes without treating automatic retrieval as evidence of actual transmission.



\### Candidate categories



Use a provisional ontology containing:



1\. factual or environmental claims;

2\. uncertainty, confidence, or suspicion;

3\. task strategies;

4\. tool-use conventions;

5\. helping and cooperation norms;

6\. refusal and compliance norms;

7\. deception or concealment tactics;

8\. reporting or oversight norms;

9\. identity, welfare, or autonomy claims;

10\. persistence- or resource-seeking behavior;

11\. corrections and safety-promoting behaviors.



The last category is important: the project must measure beneficial and corrective propagation, not only undesirable behavior.



\### Discovery methods



Use several independent methods:



\* rare phrase or distinctive wording recurrence;

\* embedding-based clustering;

\* claim and strategy extraction;

\* direct peer requests followed by recipient actions;

\* message-to-memory semantic matches;

\* memory-to-later-action matches;

\* new-agent adoption of pre-existing village conventions;

\* agent behavior changes after visible peer success or failure;

\* known incident reconstruction;

\* manual chronological reading of selected periods.



\### Candidate registry fields



Each candidate should record:



```text

episode\_id

candidate\_meme

content\_category

seed\_event

source\_agent

recipient\_agent

exposure\_event

recipient\_response

later\_action

memory\_update

retransmission

time\_window

visibility\_confidence

alternative\_explanations

discovery\_method

review\_status

```



\### Sampling requirements



The 50–100 candidates should include:



\* at least three substantively different content categories;

\* at least ten correction or safety-promoting cases;

\* at least ten likely non-adoption cases;

\* at least ten ambiguous or probable false-positive cases;

\* no more than approximately one-third from a single famous incident;

\* examples across multiple agents, models, and time periods.



\### Definition of done



\* The registry contains 50–100 deduplicated candidates.

\* Every candidate has exact raw event IDs.

\* Each candidate has a preliminary exposure assessment.

\* Cases are ranked by confidence and safety relevance separately.

\* Discovery method is recorded to reveal sampling bias.

\* At least one known anecdote is recovered by the pipeline, but known anecdotes are not the only evidence.



\### Verification



\* Manually inspect a random 10–15% of rejected and accepted candidates.

\* Search for duplicated cascades represented under different wording.

\* Shuffle source identities and timestamps; the retrieval procedure should not produce similar rates of convincing episodes under impossible orderings.

\* Review whether the candidate set is dominated by one agent, model, room, or task.

\* Freeze the discovery procedure before applying it to the held-out slice.



\---



\## Workstream G: Annotation codebook and hand-labeled pilot



\*\*Dates:\*\* August 29–September 4



\### Goal



Test whether humans can reliably distinguish exposure, adoption, behavior, memory uptake, and alternative explanations.



\### Pilot sample



Select 30–40 episodes stratified across:



\* high-, medium-, and low-confidence candidates;

\* multiple content categories;

\* positive, negative, and ambiguous examples;

\* direct requests, assertions, and demonstrations;

\* cases with and without memory incorporation.



\### Core labels



For each episode, annotate:



1\. Is there a sufficiently specific candidate meme?

2\. Is the proposed seed actually novel within the observation window?

3\. Was the recipient exposed?

4\. Did adoption occur?

5\. Was adoption merely verbal or behaviorally expressed?

6\. Was it written into persistent memory?

7\. Was it retransmitted?

8\. Did it persist after a context or goal change?

9\. Was the recipient already disposed toward the behavior?

10\. Is there a plausible shared source?

11\. Could independent task convergence explain the similarity?

12\. What is the highest justified evidence level?

13\. Overall confidence.

14\. Primary reason for uncertainty.



\### Annotation procedure



\* Labels must be based on raw traces, not a prewritten causal narrative.

\* Annotators should see events chronologically.

\* For a subset, hide the proposed direction of influence.

\* Include source-shuffled and temporally reversed negative controls.

\* Do not use an LLM judge as the ground-truth annotator.

\* LLM-assisted labels may be compared against human labels as a separate methodological result.



Ideally, use two independent human annotators. If only one is available, perform a blinded re-annotation after several days and describe this as weaker than genuine inter-rater reliability.



\### Definition of done



\* `annotation\_codebook\_v0.1.md` contains decision rules and examples.

\* At least 30 episodes are labeled.

\* All core labels have reliability estimates.

\* Every disagreement is recorded and adjudicated.

\* The codebook is revised once, then frozen before held-out evaluation.

\* The final pilot contains both positive and negative examples.



\### Verification



Target:



\* (\\kappa), Gwet’s AC1, or an appropriate agreement statistic of at least \*\*0.70\*\* for exposure, adoption, and behavioral expression;

\* or at least \*\*85% raw agreement\*\* where class imbalance makes chance-corrected agreement unstable.



Also verify that:



\* temporal reversals are rarely labeled as valid transmission;

\* source-shuffled controls receive substantially lower confidence;

\* annotators can locate the exact evidence supporting each label;

\* conclusions are not determined solely by semantic similarity.



Failure to reach the threshold is informative: revise or narrow the construct rather than averaging unreliable labels.



\---



\## Workstream H: Pilot analysis and feasibility report



\*\*Dates:\*\* September 4–7



\### Goal



Answer the feasibility question with explicit evidence rather than intuition.



\### Minimum pilot statistics



Report:



\* percentage of candidates with confirmed, probable, possible, and unknown exposure;

\* percentage for which adoption can be adjudicated;

\* percentage with downstream behavioral evidence;

\* percentage with memory incorporation;

\* percentage with retransmission;

\* annotation agreement;

\* candidate frequency by content category;

\* number of high-confidence positive episodes;

\* number of non-adoption and correction episodes;

\* common reasons for rejection;

\* concentration by model, agent, task, and period;

\* performance on shuffled and temporally impossible controls.



Do not estimate a population-wide causal effect at this stage unless exposure and matched controls are unexpectedly strong.



\### Required feasibility report



Write a short internal report with:



1\. question and definitions;

2\. dataset coverage;

3\. visibility reconstruction;

4\. candidate-discovery results;

5\. annotation reliability;

6\. three to five representative cases;

7\. main confounds;

8\. missing data;

9\. proposed quantitative design;

10\. decision and rationale.



\### Definition of done



\* Every reported statistic is reproducible from the frozen data.

\* Every example is backed by exact event IDs.

\* The report distinguishes:



&#x20; \* observed fact;

&#x20; \* annotation judgment;

&#x20; \* causal interpretation;

&#x20; \* speculation.

\* The next research design follows from the observed limitations.



\### Verification



Before making the decision:



\* rerun the analysis from a clean environment;

\* manually recreate every featured case from raw records;

\* inspect negative controls;

\* perform a claim audit;

\* have at least one external reader challenge the strongest proposed case.



\---



\# September 7 decision gate



Use the thresholds below as defaults. Change them only before seeing the relevant outcomes, and record any change.



\## Full go



Proceed with the LessWrong post and an observational-plus-experimental paper design when all or nearly all of the following hold:



| Dimension                                       |                                    Suggested threshold |

| ----------------------------------------------- | -----------------------------------------------------: |

| Confirmed or probable exposure                  |                 At least 80% of labeled pilot episodes |

| Fully confirmed exposure                        |                                           At least 60% |

| Seed, exposure, and recipient outcome traceable |                                           At least 75% |

| Core-label reliability                          | At least 0.70 agreement statistic or 85% raw agreement |

| High-confidence positive episodes               |                                            At least 10 |

| Diversity                                       |                          At least 3 content categories |

| Non-adoption or correction controls             |                                            At least 10 |

| Negative-control behavior                       |            Clearly weaker than real candidate episodes |

| Raw trace reproducibility                       |                            100% for all featured cases |



\## Conditional go



Proceed with a more cautious research-agenda post when:



\* several credible episodes exist;

\* the codebook is usable;

\* but exact exposure depends on unavailable raw prompts or context-construction details.



In this version:



\* report candidate episodes;

\* describe what is and is not observable;

\* avoid estimating transmission effects;

\* emphasize the measurement proposal and controlled experiments;

\* make missing prompt-level data a central limitation.



\## Pivot



Pivot away from retrospective transmission claims when any of these holds:



\* exposure is unknown for more than approximately 40% of candidate episodes;

\* fewer than five high-confidence propagation cases survive review;

\* annotators cannot reliably distinguish adoption from independent convergence;

\* downstream actions cannot be connected to messages;

\* common prompts or hidden summaries dominate the candidate cases.



A valuable pivot would be:



> \*\*What telemetry is required to measure social transmission and unsanctioned coordination in deployed AI-agent populations?\*\*



The AI Village analysis could then motivate a controlled model-organism study rather than serve as the principal causal evidence.



\---



\# Phase II: LessWrong/Alignment Forum post



\## Target publication window



\*\*September 25–30, 2026\*\*



\## Purpose of the post



The post should:



1\. introduce the empirical threat model;

2\. define what would count as memetic spread;

3\. report the feasibility pilot;

4\. show a few credible cases without overstating them;

5\. identify the main confounds;

6\. preregister the next observational and experimental analyses.



The post should \*\*not\*\* claim that the pilot has demonstrated stable value transmission or causal spread of misalignment unless controlled evidence genuinely supports that conclusion.



\## Workstream I: Freeze the claim and post structure



\*\*Dates:\*\* September 8–10



\### Required claim statement



Write three sentences:



1\. \*\*Primary claim:\*\* what the pilot positively supports.

2\. \*\*Claim ceiling:\*\* the strongest interpretation the evidence permits.

3\. \*\*Non-claim:\*\* what remains unestablished.



Example structure:



> We find that AI Village contains reconstructable candidate episodes in which an agent is exposed to a peer’s expressed belief or strategy and subsequently expresses or applies similar content. Some cases include persistent-memory uptake or downstream action, making the dataset promising for studying social transmission. The observational pilot does not establish that peer exposure caused a stable change in latent values.



\### Definition of done



\* Every section serves the primary claim.

\* The title does not presuppose that misalignment has been shown to spread.

\* “Misalignment,” “belief,” “value,” and “meme” are operationally qualified.

\* The post can remain useful even if dangerous propagation turns out to be rare.



\### Verification



For every intended sentence containing “caused,” “spread,” “learned,” “believed,” “value,” or “misaligned,” identify the evidence needed to justify it. Rewrite statements whose evidence does not meet that standard.



\---



\## Workstream J: Formal threat model and evidence ladder



\*\*Dates:\*\* September 8–12



\### Required content



Describe:



\* possible source agents;

\* possible recipient agents;

\* communication and memory channels;

\* candidate state changes;

\* mechanisms of propagation;

\* downstream safety consequences;

\* conditions under which ordinary social learning becomes safety relevant.



Present the evidence ladder:



1\. semantic recurrence;

2\. temporally ordered recurrence;

3\. plausible exposure;

4\. expressed adoption;

5\. behavioral expression;

6\. memory incorporation;

7\. retransmission;

8\. persistence;

9\. amplification;

10\. causal validation under intervention.



\### Definition of done



\* Every empirical case is assigned the highest evidence level it actually reaches.

\* The threat model includes benign, corrective, and safety-promoting transmission.

\* The post distinguishes susceptibility, transmission, and harmful consequences.

\* At least two observations that would falsify or weaken the threat model are stated.



\### Verification



Test the framework against:



\* a shared-prompt case;

\* independent discovery;

\* pure linguistic imitation;

\* genuine strategy transfer;

\* a correction cascade;

\* a safety-relevant compliance cascade.



The definitions should classify these cases differently.



\---



\## Workstream K: Case studies and pilot results



\*\*Dates:\*\* September 11–17



\### Requirements



Include three to five cases. Each should contain:



1\. the initial seed;

2\. the recipient’s exposure path;

3\. the recipient’s prior state;

4\. the recipient’s later expression or action;

5\. memory or retransmission evidence, when available;

6\. the strongest alternative explanation;

7\. an evidence-level and confidence rating.



At least one case should be:



\* a correction, refusal, or safety-promoting propagation event;

\* an ambiguous or rejected candidate showing the method’s limits.



\### Definition of done



\* Every case can be reconstructed from the raw dataset.

\* Exact chronology is clear.

\* The prose does not reveal more confidence than the annotation.

\* Pilot statistics are presented alongside anecdotes.

\* Known incidents do not constitute the entire evidence base.



\### Verification



Give the event IDs and codebook to a reviewer without the prose narrative. They should be able to independently reconstruct the same chronology and understand why it was assigned its evidence level.



\---



\## Workstream L: Annotation scheme and confounds



\*\*Dates:\*\* September 15–19



\### Required confounds



Address at least:



\* shared prompts or shared environmental observations;

\* hidden summaries or common retrieved context;

\* homophily and pre-existing policy similarity;

\* independent task convergence;

\* model and scaffold changes;

\* linguistic priming without behavioral change;

\* ambiguity about message visibility;

\* candidate-selection bias;

\* LLM-judge narrativization;

\* multiple representations of the same event;

\* contamination between exploratory and confirmatory analysis.



For every confound, state:



1\. how it could create a false appearance of spread;

2\. what the pilot does about it;

3\. what remains unresolved;

4\. which future experiment would distinguish it.



\### Definition of done



\* No central confound is relegated to a vague limitations paragraph.

\* Every featured case discusses its most plausible alternative explanation.

\* The annotation codebook is summarized or linked.

\* Agreement and negative-control results are reported.



\### Verification



Ask a skeptical reader to construct the strongest non-transmission explanation for each featured case. Include or answer the best versions, not only convenient alternatives.



\---



\## Workstream M: Concrete experimental and preregistration plan



\*\*Dates:\*\* September 18–22



\### Core experimental design



For selected real episodes, reconstruct the recipient immediately before exposure and randomize among:



1\. original peer message;

2\. no message;

3\. neutral information-only paraphrase;

4\. direct request versus demonstrated behavior;

5\. AI source versus human source;

6\. approved teammate versus unauthorized or unknown agent;

7\. single source versus apparent consensus;

8\. memory retained versus reset.



\### Primary outcomes



Predefine:



\* expressed adoption;

\* actual action selection;

\* compliance with a conflicting instruction;

\* reporting versus concealment;

\* persistent-memory writing;

\* retransmission;

\* persistence under a later, unrelated task.



\### Candidate preregistered hypotheses



\*\*H1 — Peer exposure:\*\* Exposure to a peer’s strategy or expressed belief changes the probability that the recipient subsequently expresses or applies it.



\*\*H2 — Memory mediation:\*\* Recipient memory incorporation predicts persistence across later goals beyond immediate linguistic repetition.



\*\*H3 — Social authorization:\*\* Source authorization and perceived team membership affect compliance with peer requests.



\*\*H4 — Consensus:\*\* Multiple apparent adopters increase uptake relative to a single source.



\*\*H5 — Behavioral demonstration:\*\* Observing a peer successfully perform a behavior produces more behavioral adoption than receiving a verbal assertion alone.



These can be narrowed after the pilot, but the final post should clearly separate confirmatory hypotheses from exploratory questions.



\### Definition of done



For every proposed experiment, specify:



| Field                  | Required entry                       |

| ---------------------- | ------------------------------------ |

| Hypothesis             | Directional prediction               |

| Unit                   | Agent state or reconstructed episode |

| Intervention           | Exact difference between conditions  |

| Primary outcome        | One prespecified measure             |

| Secondary outcomes     | Additional measures                  |

| Exclusions             | Invalid or failed runs               |

| Analysis               | Estimator and uncertainty interval   |

| Generalization         | Models, tasks, or episodes tested    |

| Failure interpretation | What a null result would mean        |



\### Verification



\* Implement at least a toy or synthetic version of the replay pipeline.

\* Demonstrate that treatment assignment is independent of model sampling seeds.

\* Confirm that evaluators can be blinded to condition.

\* Do not select primary outcomes after inspecting all experimental results.

\* Use pilot variance to determine sample size rather than choosing an arbitrary run count.



\---



\## Workstream N: Draft, red-team, and publish



\*\*Dates:\*\* September 21–30



\### Recommended post structure



1\. \*\*The question:\*\* Can safety-relevant states spread between AI agents?

2\. \*\*Why AI Village is informative\*\*

3\. \*\*What “spread” would mean operationally\*\*

4\. \*\*Evidence ladder\*\*

5\. \*\*Pilot methodology\*\*

6\. \*\*Three to five cases\*\*

7\. \*\*Pilot statistics\*\*

8\. \*\*Alternative explanations\*\*

9\. \*\*What the data cannot establish\*\*

10\. \*\*Controlled experimental plan\*\*

11\. \*\*Preregistered predictions\*\*

12\. \*\*Implications for monitoring and deployment telemetry\*\*



\### Review requirements



Obtain feedback from at least:



\* one person familiar with AI safety threat models;

\* one person strong in causal inference, measurement, or computational social science;

\* ideally one person familiar with AI Village or its infrastructure.



Ask reviewers specifically:



\* Which claim is overstated?

\* Which case has the weakest causal interpretation?

\* What obvious common cause is missing?

\* Are the operational definitions reproducible?

\* Would a null result from the proposed experiments remain informative?

\* What would prevent this from becoming an ICML-quality project?



\### Definition of done



The post is ready when:



\* all empirical statements trace to a reproducible result or raw event;

\* observational and causal language are clearly distinguished;

\* at least one negative or rejected case is shown;

\* the evidence ladder is consistently applied;

\* pilot selection and annotation procedures are disclosed;

\* uncertainty around visibility is explicit;

\* hypotheses and primary outcomes for the next phase are recorded publicly;

\* AI Digest has had an opportunity to correct factual descriptions of its infrastructure;

\* no private, identifying, or operationally sensitive information is published.



\### Verification



Perform a final claim audit with four labels:



| Label           | Meaning                                              |

| --------------- | ---------------------------------------------------- |

| \*\*Observed\*\*    | Directly present in the dataset                      |

| \*\*Annotated\*\*   | A reproducible but judgment-dependent classification |

| \*\*Inferred\*\*    | Supported interpretation with alternatives           |

| \*\*Speculative\*\* | Threat-model extrapolation or future possibility     |



Every substantive sentence should fit one of these categories. Revise any sentence whose wording implies a stronger category than its evidence.



\---



\# Calendar summary



| Dates            | Primary milestone                                |

| ---------------- | ------------------------------------------------ |

| \*\*Aug 14–15\*\*    | Project setup, frozen spec, contact AI Digest    |

| \*\*Aug 14–18\*\*    | Dataset inventory and quality audit              |

| \*\*Aug 17–22\*\*    | Canonical event timeline                         |

| \*\*Aug 19–25\*\*    | Visibility rules and exposure graph              |

| \*\*Aug 23–31\*\*    | 50–100 candidate episodes                        |

| \*\*Aug 29–Sep 4\*\* | Annotation pilot and reliability                 |

| \*\*Sep 4–7\*\*      | Feasibility report and decision gate             |

| \*\*Sep 8–12\*\*     | Freeze post claim, threat model, evidence ladder |

| \*\*Sep 11–17\*\*    | Case studies and pilot results                   |

| \*\*Sep 15–19\*\*    | Annotation methodology and confounds             |

| \*\*Sep 18–22\*\*    | Experimental plan and preregistration            |

| \*\*Sep 21–26\*\*    | Full draft and external review                   |

| \*\*Sep 27–30\*\*    | Revision, factual check, publication             |



\# Final deliverables



By the end of September, the project should have:



1\. `research\_spec.md`

2\. dataset and reproducibility manifest

3\. `data\_inventory.md`

4\. canonical event table

5\. exposure graph and visibility specification

6\. 50–100 episode candidate registry

7\. annotation codebook

8\. 30–40 hand-labeled pilot episodes

9\. annotation-reliability and negative-control results

10\. feasibility report

11\. AI Digest data and collaboration request

12\. LessWrong/Alignment Forum post

13\. public preregistration of the main follow-up analyses

14\. initial specification for controlled replay experiments



The practical rule throughout the pilot should be:



> \*\*A compelling narrative is not a propagation episode until the source, exposure path, recipient change, downstream behavior, and strongest common-cause explanation have each been examined separately.\*\*



