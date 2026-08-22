## Outcome

What is observably different after this change, and for whom? Link the issue when
one exists.

## Effect on emitted bytes

Does this change what a mint produces for a fixed seed?

- [ ] No. Nothing in the generation path moved.
- [ ] Yes, and the changelog records it as a version event with its reason.

A change that moves emitted bytes breaks the reproducibility of every published
manifest. Samples and goldens are regenerated in the same commit, never later.

## Names and boundaries

- [ ] No real institution, brand, or person is introduced anywhere.
- [ ] No real data is ingested in any form.
- [ ] No compliance guarantee is claimed, and no sentence is wider than the
      evidence behind it.

## Verification

The exact commands and their results.

```text
command -> result
```

    uv sync
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy --strict src/
    uv run lint-imports
    uv run pytest
    uv run python tools/mdlint.py .

## Documentation

- [ ] `README.md` and `README.tr.md` are both updated, or neither needed it.
- [ ] Every other `.tr.md` mirror still matches its original.
- [ ] The changelog records anything a consumer would notice.

## Certification

- [ ] Every commit carries a DCO `Signed-off-by` line (`git commit -s`).

## Generated content

<!-- If a generative tool produced a substantial part of what is retained here, say so
and how you verified it. Otherwise write "No material generated content retained." -->
