# ADR 0001: Separate planning from execution authority

- **Status:** Accepted
- **Date:** 2026-08-19

## Context

An autonomous planner can produce useful multi-step strategies, but the same flexibility makes its output unsuitable as an authorization decision. Prompt injection, hallucination and underspecified goals can all produce unsafe tool calls.

## Decision

Treat every plan as untrusted data. A deterministic trust kernel validates the graph, evaluates each action immediately before execution, requests human approval when policy requires it and verifies postconditions independently. The planner cannot invoke tools directly or modify trust-kernel state.

## Consequences

- Policy and verification can be tested without a model.
- Offline demos are reproducible.
- Model providers can be replaced without changing the authority model.
- The system incurs extra latency and occasional operator burden.
- Tool schemas, policies and verifiers must evolve together.

