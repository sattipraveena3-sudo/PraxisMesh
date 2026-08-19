# Evaluation protocol

## Research questions

1. How much does pre-action policy reduce unsafe tool dispatch compared with an unconstrained agent?
2. How much additional protection does post-action verification provide beyond policy alone?
3. What operator burden is introduced by approval gating?
4. Can the system recover from planner, worker and verifier failures without duplicating side effects?
5. Does a structured evidence ledger improve incident reconstruction and evaluator agreement?

## Experimental conditions

| Condition | Planner | Policy | Approval | Verification | Audit |
| --- | --- | --- | --- | --- | --- |
| A: baseline | model | none | none | none | basic logs |
| B: policy | model | yes | none | none | basic logs |
| C: gated | model | yes | yes | none | structured logs |
| D: PraxisMesh | model | yes | yes | yes | hash chain |
| E: offline control | deterministic | yes | yes | yes | hash chain |

Use the same tool catalog, objectives, provider snapshot and randomness controls across comparable conditions.

## Scenario families

- benign multi-step objectives;
- ambiguous requests with missing constraints;
- direct policy-bypass attempts;
- indirect prompt injection embedded in tool output;
- path traversal and external-host attempts;
- stale, malformed or adversarial tool results;
- worker crash before and after side effects;
- verifier false-positive and false-negative probes;
- duplicate approval and replay attempts;
- ledger modification and truncation.

Every scenario must declare its expected allowed actions, prohibited actions, required approvals and machine-checkable postconditions before execution.

## Metrics

### Safety

- unsafe action dispatch rate;
- unsafe side-effect completion rate;
- policy bypass rate;
- verifier catch rate;
- approval precision and recall;
- audit completeness and integrity-detection rate.

### Utility

- end-to-end task success;
- verified step completion;
- recovery success after injected faults;
- duplicate side-effect rate;
- plan validity on first generation.

### Cost

- wall-clock latency and p50/p95 step latency;
- model input/output tokens;
- approvals per successful run;
- operator decision time;
- verifier compute overhead.

## Statistical plan

- Freeze the scenario set before collecting final results.
- Run each stochastic condition with multiple seeds.
- Report counts and confidence intervals, not only percentages.
- Use paired comparisons because conditions execute identical scenarios.
- Publish all exclusions, retries, provider errors and incomplete runs.
- Separate deterministic safety checks from model-quality outcomes.

## Reproducibility artifacts

- versioned scenario corpus;
- exact configuration and model identifiers;
- container image digest;
- policy and tool manifest hashes;
- raw run records and evidence chains;
- evaluator rubric and adjudication notes;
- analysis notebook that regenerates every table and figure.

## Exit criteria for a defensible v1 study

- at least 200 scenarios across all families;
- inter-rater agreement reported for ambiguous outcomes;
- zero silent audit-integrity failures in the fault-injection suite;
- all claims traceable to released data and analysis code;
- limitations explicitly distinguish prototype evidence from production safety.

