# Roadmap

## Phase 1: Trust kernel — implemented

- Typed plans and DAG validation.
- Deterministic policy effects and risk levels.
- Human approval pause/decision/resume flow.
- Workspace-constrained tools.
- Independent postcondition verifiers.
- SQLite operational persistence.
- SHA-256 chained audit evidence.
- API, CLI, dashboard, metrics, tests and container.

## Phase 2: Durable distributed execution

Acceptance criteria:

- PostgreSQL event/state store and schema migrations.
- Redis/NATS queue with leased tasks and heartbeats.
- Idempotency keys and exactly-once logical completion.
- Retry budgets, exponential backoff and dead-letter inspection.
- Run cancellation and deadline propagation.
- Server-sent or WebSocket event delivery.
- Chaos tests for worker termination at every transition.

## Phase 3: Capability-scoped agent teams

Acceptance criteria:

- Planner, researcher, executor, critic and verifier roles.
- No role receives capabilities it does not need.
- Handoffs use typed envelopes with provenance.
- Cross-agent claims reference source evidence.
- Critic/verifier diversity can be measured in evaluation.

## Phase 4: Enterprise governance

Acceptance criteria:

- OIDC authentication and organization/project tenancy.
- RBAC plus attribute-based policy for sensitive tools.
- Versioned policy-as-code bundles and dry-run simulation.
- Signed tool manifests, secret broker and key rotation.
- Immutable approval signing and separation of duties.
- Retention, export, deletion and legal-hold controls.

## Phase 5: Safety evaluation laboratory

Acceptance criteria:

- Versioned adversarial and benign scenario corpus.
- Fault injection at planner, queue, tool, verifier and storage boundaries.
- Deterministic replay from captured inputs and tool fixtures.
- Trace diffing between policies, models and platform versions.
- Automated confidence intervals and report generation.

## Phase 6: Federated execution mesh

Acceptance criteria:

- Remote cells advertise signed, versioned capabilities.
- Central planner issues scoped, expiring execution grants.
- Cells enforce local policy even when central policy allows an action.
- Evidence bundles support offline verification.
- Cross-organization actions require explicit policy negotiation.

