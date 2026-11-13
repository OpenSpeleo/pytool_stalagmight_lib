# stalagmight_lib Agent Instructions

## Project overview

`stalagmight_lib` reads native schema-18/19 SQLite `.stalx` cave surveys into
immutable Pydantic models and exports supported survey data as JSON.

- `stalagmight_lib/parser.py`, `section.py`, and `shot.py`: reading and survey
  data.
- `stalagmight_lib/survey.py`, `_model.py`, and `enums.py`: project metadata,
  strict model conventions, and native enum mappings.
- `stalagmight_lib/commands/`: the `stalagmight` CLI and JSON convert action.
- `tests/`: native fixture regression, synthetic SQLite validation, and CLI
  tests.

Preserve native field values, SQL nulls, UUID identity, positional station
comments, and bearing metadata. Cover malformed SQLite inputs, relationship
validation, JSON round-trips, connection cleanup, and read-only behavior when
changing parsing. Native writing and corrections are outside the reader scope.
Loop-closure preparation and coordinate computation belong to consuming adapters
in `openspeleo_lib`, not this reader. `Survey` preserves validated datum and
station-merge metadata for those adapters; the reader does not apply it.

## Documentation references

Do not copy literal commit SHAs, checksums, UUID values, or current package,
dependency, and runtime version numbers into documentation or agent
instructions. Refer to authoritative manifests, lockfiles, CI configuration,
source paths, and regression tests instead. Describe UUID behavior without
sample identity values. Stable file-format schema requirements and protocol
discriminants may be stated when they define supported behavior.

## Temporary agent files

Keep agent plans, task lists, TODO tracking, progress notes, review notes, and
scratch lessons outside the repository tree, including all submodules. Use a
unique task directory under `/tmp/` (for example, create one with
`mktemp -d /tmp/sdb-stalagmight-lib-task.XXXXXX`) or another OS temporary
directory whose resolved path is outside every checkout.

Never create or update these working files inside the checkout, even in ignored
directories such as `tasks/`, `todos/`, or `plans/`. Never stage or commit them.
Existing tracked task and lesson files are historical references; do not append
new work to them. Keep durable product and architecture documentation in
`docs/`, without embedding task checklists or linking to temporary files. Before
an authorized commit, inspect the staged filenames and exclude all agent working
files.

## Working rules

- Read the relevant source, tests, and configuration before editing. Keep
  changes focused and preserve public behavior unless the task requires changing
  it.
- Inspect staged and unstaged changes separately before and after work. Preserve
  unrelated user work, existing branches, and submodule revisions.
- Do not stage, commit, push, open a PR, tag, or publish without explicit user
  authorization. Never install Git hooks or configure `core.hooksPath`.
- Run commands from this repository's root unless stated otherwise. In the
  monorepo, also follow the integration root's `AGENTS.md`; keep this repository
  usable independently and keep product changes in their owning repository.
- For documentation-only changes, run `prek run prettier --files AGENTS.md` and
  whitespace checks. For behavior changes, run focused regression tests and the
  relevant full suite. Report commands, results, and any missing prerequisites.

## Python development and verification

Python support and dependencies are defined in `pyproject.toml`; the supported
Python range and CI matrix are authoritative there and in CI configuration. Keep
code compatible with that range. Follow the configured Ruff rules, use existing
package constants and helpers, and add regression coverage at the affected
parser, model, or command boundary. Test every Pydantic class independently,
including direct construction, invalid values, immutability, and JSON
round-trips. Use Hypothesis property tests for model inputs and relationships;
parser tests do not substitute for independent model coverage.

Run the standalone checks from this package directory:

```bash
uv sync --frozen --all-extras --dev
uv run pytest
uv run prek run --all-files
```

Prek is the entrypoint for linting and formatting. It may apply fixes; inspect
its diff and rerun affected checks. For test runs, prefer the CI command
`uv run pytest` over legacy Make targets that may require extra tools or perform
cleanup. Preserve test fixtures; put generated test outputs in temporary
directories.

## Dependencies and integration

Keep this package's `pyproject.toml` and `uv.lock` authoritative for standalone
use. Run `uv lock` here after dependency changes. When working in the monorepo,
also refresh the root integration lock and validate the root frozen sync as
directed by its `AGENTS.md`. Do not add a uv workspace or monorepo-only paths to
standalone dependency declarations.

This package uses Flit. Preserve its package layout, CLI entry points, and
module-owned version metadata. For packaging changes, run `uv run flit build`;
do not use cleanup targets as routine verification or change release workflows
without a task requirement.
