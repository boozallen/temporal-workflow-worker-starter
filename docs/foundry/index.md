---
sidebar_position: 1
---

# Overview

A fork-and-customize template for Temporal workflow workers.

`temporal-workflow-worker-starter` is a complete, running Temporal worker — not a library.
You fork it, replace the template workflow and activities with your own business logic, and
deploy the result as your team's service. It composes the
[`temporal-packages`](https://github.com/boozallen/temporal-packages) libraries into
something deployable: [`foundry-temporal`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal/index.md) supplies the workflow primitives (signals,
queries, retry policies, worker bootstrap) and the agent integration package supplies the
activity for calling Strands agents.

## What ships in the template

- **A working 3-step workflow** — [`MyWorkflow`](../../src/workflows.py) demonstrating activity execution, an agent
  call, and a human-in-the-loop approval gate
- **Configuration-driven registration** — workflows, activities, and external services
  declared in [`config/*.yaml`](../../config/) rather than hardcoded
- **A local dev stack** — [`compose.yaml`](../../compose.yaml) runs the worker against a mock Strands agent, so
  nothing external is required to see a workflow execute end to end
- **Unit and integration test tiers** — split by directory under [`tests/`](../../tests/)
- **A multi-stage [Dockerfile](../../Dockerfile)** — non-root runtime user, health check, Chainguard base

## Where to go next

- **[Getting Started](./getting-started/index.md)** — prerequisites, first run, and the
  worker architecture
- **[Guides](./guides/index.md)** — the end-to-end walkthrough of the full stack, and how
  to customize the template for your domain
- **[Operations](./operations/index.md)** — production deployment and high-availability
  worker tuning
- **[Contributing](https://github.com/boozallen/temporal-workflow-worker-starter/blob/HEAD/CONTRIBUTING.md)**
  — fork workflow, dev setup, review and merge process
- **[Security](https://github.com/boozallen/temporal-workflow-worker-starter/blob/HEAD/SECURITY.md)**
  — reporting a vulnerability
