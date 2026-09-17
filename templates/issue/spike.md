---
name: Spike / Decision
about: A question that needs an answer, not code — e.g. choosing between architectures, tools, or platforms.
title: "Spike: "
labels: type:spike
---

## Value

<!-- Why this decision matters now — what stays blocked or ambiguous without
     it. One or two sentences.
     Example: "Two coding tasks are queued behind this — both need a queue
     backend, and building against the wrong one means rework." -->

## Question to Answer

<!-- The specific question this spike must answer. Not "figure out X" — a
     question with a real yes/no or A/B/C shape.
     Example: "Should the job queue run on Redis (already in our stack) or
     Postgres (via a `SKIP LOCKED` table), given our throughput is under
     100 jobs/minute?" -->

## Alternatives Considered

<!-- Name at least two concrete options. A spike that only evaluates one
     option isn't a decision, it's a confirmation.
     Example:
     - Redis with a list-based queue (e.g. via `rq`)
     - Postgres table with `SELECT ... FOR UPDATE SKIP LOCKED` -->

-
-

## Decision Criteria

<!-- What makes one alternative win over another — cost, fit with existing
     architecture, maintenance burden, etc.
     Example: "No new infrastructure to operate; visibility into queue
     depth from existing tooling; acceptable latency at our volume." -->

## Deliverable

<!-- Where the decision gets recorded so dependent tickets can reference it.
     If it's an ADR: include a comparison matrix (alternatives as columns,
     Decision Criteria as rows, an explicit winner per row) — not prose in
     table cells, and grounded in facts rather than "the requester wants X."
     Example: "ADR at `docs/adr/0007-job-queue-backend.md`, linked from
     both queued coding tasks." -->
