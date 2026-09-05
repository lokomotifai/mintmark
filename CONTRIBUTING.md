# Contributing

<sub><a href="CONTRIBUTING.tr.md">Türkçe</a></sub>

Thank you for considering a contribution. This project is small and its review
discipline is deliberate, so read this before opening a pull request.

## Sign your commits

Contributions are accepted under the Developer Certificate of Origin, version
1.1. There is no contributor license agreement. Every commit carries a sign-off
line matching the commit author:

    git commit -s -m "your message"

A pull request with an unsigned commit is not merged until it is signed.

## Before you open a pull request

Run the same checks required CI runs. All of them work offline once dependencies
are installed. `pyproject.toml` accepts any uv in the 0.12 series; required CI
runs 0.12.3.

    uv sync
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy --strict src/
    uv run lint-imports
    uv run pytest
    uv run python tools/mdlint.py .

## Language rules for prose

These are enforced by `tools/mdlint.py` in required CI, in every language:

1. Headings are sentence case.
2. A list of promotional terms is banned, in English and in Turkish. The list
   lives in `tools/mdlint.py` and is the authority.
3. The em dash and the en dash never appear in repository prose. Hyphen-minus is
   unrestricted.

Quoted third-party text is exempted with an allowlist marker that carries a
reason. An exemption without a reason is a lint error.

## The Turkish mirror

`README.md` is canonical and `README.tr.md` is a full mirror, not a summary. A
change to one without the other fails review. The same rule covers every other
`.tr.md` mirror in this repository. If you are not comfortable writing
the Turkish, say so in the pull request and it will be handled; do not leave the
mirror stale.

## What makes a change easy to accept

State the observable behavior that changed and the command that proves it. A
change to the mint path additionally states its effect on byte-level output for
a fixed seed, because that determines whether the change is a major version
event.

## What will be declined

Changes that add a runtime dependency without a recorded decision. Changes that
put a model anywhere in the generation path. Changes that ingest real data in
any form. Changes that weaken an invariant rather than replacing it with a
stronger one.
