# Engineering notes

Operational know-how for this repository: build quirks, environment traps, and
conventions that would otherwise be re-derived every session. This file is
committed. It is the counterpart to the local-only plan, and it holds what a
contributor needs rather than what the build's memory needs.

## Toolchain

The runtime is CPython 3.12 only, pinned by `requires-python = ">=3.12,<3.13"`.
The system Python on a developer machine is usually newer. `uv` installs and
selects 3.12 on its own:

    uv python install 3.12
    uv sync

Do not widen the range to make a local machine work. Each added minor version
widens the determinism claim's surface, and the claim is the product.

## Packaging config is added by the milestone that creates the data

`pyproject.toml` deliberately does not declare `assets/`, `schemas/`, or
`packs/example` yet. Hatchling fails the build when a `force-include` path does
not exist, and creating empty directories to satisfy the config would be a
placeholder. Each directory is added to the build config by its owning
milestone: `assets/tables` at WP-02, `assets/denylist` at WP-05, `schemas` at
WP-06, `packs/example` at WP-12. WP-16's packaging manifest test asserts the
final set.

The `readme` key is absent from `[project]` for the same reason: `README.md` is
WP-15's deliverable, and hatchling errors on a missing readme file. WP-15 writes
the README and restores the key in the same change.

## import-linter contracts are activated in stages

The layers contract uses import-linter's optional-layer syntax, meaning each
layer name is wrapped in parentheses, so that the contract is enforceable from
WP-00 and tightens automatically as modules appear.

Forbidden contracts have no optional syntax and error out on a module that does
not exist. They are therefore commented out in `.importlinter` with the
milestone that activates each one named beside it. Uncomment a contract in its
owning milestone, never earlier and never later. WP-14's gate asserts that every
contract is active.

## The canary is never committed

`tools/canary.py` scans for a private-corpus canary string that must be absent
from the tree and from built artifacts. Committing the string would plant the
very thing the check looks for, and the first run would fail on its own
tripwire.

The canary is supplied at run time through `MINTMARK_CANARY` or `--canary-file`.
Only its SHA-256 is committed, so a run can prove it received the right string
rather than an empty one. Supplying the wrong canary is a hard error rather than
a silent pass, because a check scanning for the wrong string is worse than no
check at all.

In CI the canary comes from a repository secret. Locally it comes from the
owner's private materials directory, which is gitignored.

## The prose lint has to contain what it bans

`tools/mdlint.py` holds the em dash, the en dash, and the Turkish banned
vocabulary as literals, because it searches for them. Ruff's ambiguous-character
rule flags exactly these literals, and the file carries targeted `noqa`
directives for them. That is expected. Do not remove the literals to satisfy the
linter.

Fenced code blocks and inline code spans are exempt from the prose rules, so
that a command or an identifier does not trip a vocabulary check. Quoted
third-party text is exempted with a marker that carries a reason; a marker
without a reason is itself an error.

## Verification convention

No item is complete because a file exists or a command exited zero. Each check
in this repository is proven twice: once by passing on clean input, and once by
failing on deliberately broken input and then passing again after the breakage
is removed. A lint that has never been observed failing is not known to work.
