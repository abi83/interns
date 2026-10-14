# Metrics

Every agent run is recorded, so you can see what the pipeline costs and where it struggles.

## What is recorded

Each agent job appends one JSON record per `(run, job)` to `metrics.jsonl` on the orphan
`interns-metrics` branch of your repo: tokens (per model, sub-agents included), cost, turns,
duration, tool-call counts, permission denials, the `interns` ref and the agent's result.
The record shape is versioned by `schema_version` and specified in
[`pipeline-metrics.schema.json`](../.github/pipeline-metrics.schema.json).

A final `metrics` job on each workflow run commits the records its agent jobs uploaded in one
push. Concurrent runs are serialized by a `metrics-append` concurrency group.
`interns-install` creates the branch and protects it against deletion.

## Dashboard

The installer adds a static page, `interns-metrics/index.html`, served by GitHub Pages. It reads
`metrics.jsonl` in the browser and shows total spend, spend and average turns by job, agent
results, cost per run and per model, the most used tools, permission denials and the `interns`
versions in use. Pages must be on; the installer checks it.

## Raw data

One unauthenticated fetch reads the log:
`https://raw.githubusercontent.com/<owner>/<repo>/interns-metrics/metrics.jsonl`
