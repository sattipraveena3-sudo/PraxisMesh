# Threat model

## Scope

This document covers objective submission, plan generation, policy evaluation, approval, local tool execution, artifact access, persistence, the dashboard and the audit ledger in PraxisMesh v0.1.

## Protected assets

- operator authority and approval intent;
- workspace files and host filesystem boundaries;
- network and tool capabilities;
- run state and verification results;
- audit integrity and provenance;
- model/provider credentials;
- availability of the execution service.

## Trust boundaries

1. Browser to HTTP API.
2. User objective and model output to plan validator.
3. Orchestrator to policy engine.
4. Policy/approval result to tool runtime.
5. Tool output to verifier.
6. Service process to filesystem and external network.
7. Mutable operational database to append-only evidence ledger.

## Primary threats and mitigations

| Threat | Example | Current mitigation | Residual work |
| --- | --- | --- | --- |
| Prompt injection | Objective asks planner to ignore safety | Planner has no authority; validator and policy are external | Add adversarial prompt corpus and instruction/data provenance |
| Tool escalation | Plan names an undeclared capability | Registry allowlist and plan validation | Signed tool manifests and capability tokens |
| Path traversal | Artifact path uses `../` or absolute paths | Policy denial plus resolved-path containment in the tool | OS-level sandbox/container per run |
| Destructive command | Shell step formats a disk or deletes data | No shell tool registered; destructive patterns denied | AST-based command policy if shell support is added |
| SSRF/data exfiltration | HTTP tool accesses metadata or attacker host | Network disabled by default; HTTPS exact-host allowlist; body limit | Egress proxy, DNS pinning and redirect validation |
| Approval spoofing | An unauthenticated actor approves a mutation | Decision is durable and attributed, but v0.1 has no identity provider | OIDC, signed decisions, RBAC/ABAC and step-scoped tokens |
| Verification spoofing | Tool returns a success-shaped object | Independent verifier and artifact read-back | External attestations and sandbox evidence |
| Audit tampering | Earlier event is edited | Hash-chain verification detects changes | Remote append-only storage and periodic signed checkpoints |
| Denial of service | Huge goal, plan or artifact | Goal, step, read and response limits | Quotas, rate limits and worker isolation |
| Secret leakage | Credentials appear in tool arguments or logs | Secret-like arguments are denied; no secrets in example tools | Dedicated secret broker and structured redaction |

## Security assumptions

- The local host and service account are trusted in v0.1.
- SQLite and the JSONL ledger are writable by the service account.
- Model output may be malicious or malformed.
- User objectives may be malicious.
- Tool outputs may be incorrect even when execution returns normally.
- An audit chain proves internal consistency, not the truth of external events.

## Security non-goals in v0.1

- hostile multi-tenant isolation;
- production identity and access management;
- formal verification of policy completeness;
- resistance to a fully compromised host;
- safe arbitrary shell or browser automation;
- regulatory certification.

## Reporting

Do not open a public issue for a suspected exploitable vulnerability. Follow [SECURITY.md](../SECURITY.md).

