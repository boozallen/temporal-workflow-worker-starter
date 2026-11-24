# Contributing to Temporal Workflow Worker Starter

Thank you for your interest in contributing! This guide covers how to get started,
submit changes, and what to expect during review.

Note what this repository is: a fork-and-customize template. Most people who use it
should **fork it and change whatever they like in their own fork** — no contribution
back is expected or needed. Contribute here when the template itself is wrong or could
serve every fork better: a broken command, a stale doc, a pattern worth demonstrating.
Domain-specific business logic belongs in your fork, not here.

## Code of Conduct

All participants are expected to treat others with respect and professionalism.
Harassment or abusive behavior will not be tolerated.

## Getting Started

### Fork and Clone

1. Fork this repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/temporal-workflow-worker-starter.git
   cd temporal-workflow-worker-starter
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/boozallen/temporal-workflow-worker-starter.git
   ```

### Development Setup

This is a Python project managed with [uv](https://docs.astral.sh/uv/) and
[just](https://github.com/casey/just). You need Python 3.15 — [`pyproject.toml`](pyproject.toml) requires
`>=3.15,<3.16`, and there is no `.python-version` file, so make sure the interpreter uv
picks satisfies that.

```bash
cp env.template .env
just setup          # uv sync --group dev --group test, then uv lock
just check          # verify the setup
```

The `foundry-*` dependencies install from their public GitHub release wheels, which
`[tool.uv.sources]` in `pyproject.toml` names, so `just setup` needs no extra package index.

Running the local stack additionally needs Docker with Compose and the
[Temporal CLI](https://docs.temporal.io/cli):

```bash
just temporal       # Temporal dev server
just start          # worker + mock agent
just logs           # follow worker output
just reset          # stop everything, re-run setup
```

### Common Commands

| Command | Description |
|---------|-------------|
| `just sync` | Install dependencies only (no `.env` or lockfile work) |
| `just setup` | `sync` plus local env prep — creates `.env` from [`env.template`](env.template), runs `uv lock` |
| `just lint` | Ruff lint plus the bandit command-injection sink set (`B602,B603,B605,B607`) |
| `just lint-fix` | Auto-fix ruff lint findings |
| `just format` / `just format-fix` | Check / apply formatting |
| `just type-check` | basedpyright type checking |
| `just check` | Full gate: `lint` + `format` + `type-check` + `test`. Run before opening a PR |
| `just test` | Both test tiers (writes `htmlcov/` via pytest config) |
| `just test-unit` / `just test-integration` | One tier only |
| `just validate-docker` | Build the container image and assert its metadata |
| `just add-package <pkg>` / `just add-dev-package <pkg>` | Add a dependency and relock |
| `just temporal` | Temporal dev server (needs the Temporal CLI) |
| `just dev` / `just run` | Run the worker locally, no Docker (alias) |
| `just up` / `just down` (aliases: `start` / `stop`) | Start / stop the worker and mock agent containers |
| `just logs [service]` / `just status` / `just reset` | Local stack lifecycle |
| `just build` | Build the worker Docker image |
| `just clean` / `just clean-all` | Remove build artifacts and caches / plus this project's Docker containers and volumes |

`just --list` shows the full recipe surface.

`just validate-docker` needs a reachable Docker daemon. If it can't reach one natively but
`wsl.exe` is present, it retries automatically through WSL — this covers the common Windows
case where WSL2 mirrored networking (`networkingMode=mirrored` in `.wslconfig`, often
required behind a corporate proxy) breaks the native Docker Desktop/Rancher Desktop
connection but a WSL distro with Docker integration enabled still works.

Since this template ships no CI workflows, these recipes are the verification gates.
Run `just check` locally before opening a PR — nothing else will run it for you.

### Testing Conventions

- New tests go in [`tests/unit/`](tests/unit/) unless they need external services or a running Temporal
  server, in which case they go in [`tests/integration/`](tests/integration/). The tier is decided by the
  **directory**, not by a marker, so the classification cannot be forgotten.
- `just test-integration` treats "no tests collected" (pytest exit code 5) as success, so
  it is safe to run on a branch with no integration tests yet.
- `just check` does not call `sync` — `uv run` auto-syncs on every invocation, so a cold
  clone can run it directly.
- Markers are retained only for cross-cutting traits a directory cannot express — `slow`,
  `network`, `docker`, `temporal`, and similar. `--strict-markers` is on, so a new marker
  has to be registered before use; run `pytest --markers` to see the current set.
- `just lint` runs ruff plus the narrow bandit command-injection sink set
  (`B602,B603,B605,B607`), so the local gate exercises the same sinks a security review
  will look at.
- Tests that assert on the template's own structure — file layout, documentation paths —
  live in `tests/integration/`. If you move or rename a documented file, expect to update
  them.

### Recipe Conventions

These conventions are shared across the sibling repos
(`temporal-workflow-api-starter`, `strands-base-agent`), so a recipe body reads the same
regardless of which repo you're in:

- Every recipe invokes its tool as plain `uv run <tool> ...`, with no `--group` flag and no
  `python -m` wrapper
- `just clean` removes `build/`, `dist/`, `htmlcov/`, `*.egg-info/`, `.pytest_cache/`,
  `.ruff_cache/`, `.coverage`, `__pycache__/`, and `*.pyc`, then prints
  `Cleaned build artifacts`. It skips `.venv/` so a clean does not invalidate the
  environment, and never touches Docker, so it works with no daemon running
- Container recipes use one naming set: `up`/`down` with `start`/`stop` as aliases,
  `logs [service]`, `status`, `build`, `reset` (down + clean + setup), and `clean-all`
  (clean + `docker compose down -v --remove-orphans`). `clean-all` is scoped to this
  project's compose file — it does not prune the Docker host, so it cannot disturb
  unrelated services
- The local, non-Docker run recipe is `just dev` in every repo, with `just run` as an alias

## Making Changes

### Branch Workflow

1. Sync your fork with upstream:
   ```bash
   git fetch upstream
   git checkout develop
   git merge upstream/develop
   ```
2. Create a feature branch from `develop`:
   ```bash
   git checkout -b feature/your-change
   ```
3. Make your changes, keeping commits focused (one logical change per commit)
4. Push to your fork:
   ```bash
   git push origin feature/your-change
   ```

### Branch Naming

- `feature/<short-description>` for new features
- `fix/<short-description>` for bug fixes
- `docs/<short-description>` for documentation-only changes

### PR Conventions

- All PRs target the `develop` branch
- Keep changes focused and small
- Include a clear description of what changed and why
- Reference any related issues
- Add or update tests for behavioral changes
- Update docs when behavior or interfaces change
- Keep template code generic — placeholder names like `MyWorkflow` and `my_activity` are
  deliberate, and a change that hardcodes one domain's logic makes the template worse for
  everyone else
- Ensure all checks pass before requesting review

## Submitting a Pull Request

1. Open a pull request from your fork's branch to `upstream/develop`
2. Fill out the PR template checklist
3. Wait for CI checks to pass
4. A maintainer will review your PR — only designated maintainers have merge rights

### What to Expect

- Maintainers review all PRs before merging (role-based permissions)
- You may be asked to make changes; push additional commits to your branch
- Once approved, a maintainer will merge your PR
- External contributors do not have direct push or merge access

## Review and Merge Process

This project uses a maintainer-controlled merge model:

- Only designated maintainers (defined in [`.github/CODEOWNERS`](.github/CODEOWNERS))
  can merge pull requests
- At least two approving reviews are required
- At least one CODEOWNERS review is required
- All CI checks must pass before merge
- Stale approvals are dismissed when new commits are pushed
- No bypass is allowed — maintainers follow the same review process

## Reporting Security Issues

**Do not report security vulnerabilities through public GitHub issues.**

See [SECURITY.md](SECURITY.md) for instructions on reporting vulnerabilities privately.

## Questions

Open an issue or start a discussion for help with contributions or with adapting the
template to your use case.

## License

By contributing, you agree that your contributions will be licensed under the same
license as this project. See [LICENSE](LICENSE) for details.
