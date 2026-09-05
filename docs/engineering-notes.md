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

## Output conventions worth knowing before they surprise you

A mint writes into a staging directory created with `mkdtemp`, so the finished
dataset directory is mode 0700 and its files are mode 0600: readable by the
owner alone. Sharing a dataset through a shared directory means loosening those
modes deliberately; the engine does not consult the umask.

Two byte budgets bound a mint independently of the record-count ceiling. Each
output file may not exceed 256 MiB and a dataset may not exceed 512 MiB in
total. The million-record ceiling on a single type is therefore reachable only
for compact record types; the example pack's customer records run into the
aggregate budget first, and the mint is refused with `dataset-output-byte-limit`
after the staging directory is discarded.

CSV emission refuses any cell whose first meaningful character would make a
spreadsheet evaluate it, with one deliberate exemption: a Turkish mobile number
in the emitted `+90 5xx xxx xx xx` shape, and signed numerals, are passed
through. A phone number is the value a consumer expects in that column, and it
is not an active payload. The exemption is fixed in `emit/csv_writer.py` and
covers nothing else.

SIGINT and SIGTERM both leave nothing behind. A keyboard interrupt unwinds
through `staged_output`, which discards the staging directory; SIGTERM is turned
into the same unwinding by a handler installed for the duration of the mint,
and only when the process has not installed one of its own. SIGKILL cannot be
intercepted, so a `.<name>.staging-*` directory next to the target is the trace
of a mint that was killed rather than stopped. It is safe to delete.

## Invariant to test map

Every invariant in the plan, the file that proves it, and the command that
runs that proof alone. Generated by inspection of the suite, so a claim that
an invariant has a test cannot outlive the test.

| # | Invariant | Proof | Command |
| --- | --- | --- | --- |
| 1 | Determinism | `tests/golden/test_golden_bytes.py` | `uv run pytest tests/golden -q` |
| 2 | Safe-mode purity | `tests/property/test_safe_mode_purity.py` | `uv run pytest tests/property/test_safe_mode_purity.py -q` |
| 3 | Manifest integrity | `tests/adversarial/test_tamper_detection.py` | `uv run pytest tests/adversarial/test_tamper_detection.py -q` |
| 4 | Fail-closed pack loading | `tests/adversarial/test_pack_rejection.py` | `uv run pytest tests/adversarial/test_pack_rejection.py -q` |
| 5 | Label alignment | `tests/property/test_span_alignment.py` | `uv run pytest tests/property/test_span_alignment.py -q` |
| 6 | No network at mint time | `tests/unit/test_mint_invariants.py` | `uv run pytest tests/unit/test_mint_invariants.py -k socket -q` |
| 7 | No real-brand leakage | `tests/unit/test_denylist.py` | `uv run pytest tests/unit/test_denylist.py -q` |
| 8 | Reserved domains only | `tests/unit/test_mint_invariants.py` | `uv run pytest tests/unit/test_mint_invariants.py -k reserved -q` |
| 9 | Validator watermark | `tests/adversarial/test_tamper_detection.py` | `uv run pytest tests/adversarial/test_tamper_detection.py -k validator -q` |
| 10 | Taxonomy closure | `tests/unit/test_taxonomy.py` | `uv run pytest tests/unit/test_taxonomy.py -q` |
| 11 | No floats in emitted data | `tests/unit/test_emit.py` | `uv run pytest tests/unit/test_emit.py -q` |
| 12 | Referential integrity | `tests/property/test_records.py` | `uv run pytest tests/property/test_records.py -q` |
| 13 | Exit-code contract | `tests/unit/test_cli.py` | `uv run pytest tests/unit/test_cli.py -q` |
| 14 | Module boundary integrity | `.importlinter` | `uv run lint-imports` |
| 15 | No transcendental calls | `tests/unit/test_no_libm.py` | `uv run pytest tests/unit/test_no_libm.py -q` |
| 16 | Private-input containment | `tests/unit/test_canary.py` | `uv run pytest tests/unit/test_canary.py -q` |
| 17 | Prose language rules | `tests/unit/test_prose_lint.py` | `uv run pytest tests/unit/test_prose_lint.py -q` |
| 18 | README parity | `tests/unit/test_readme_mirror.py` | `uv run pytest tests/unit/test_readme_mirror.py -q` |

Two invariants are enforced outside pytest. Number 14 is an `import-linter`
contract set, and the prose lint of number 17 is a standalone script; both run
in required CI alongside the suite.
