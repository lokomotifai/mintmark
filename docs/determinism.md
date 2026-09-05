# Determinism

## The claim, stated exactly

Identical engine version, pack digest, recipe, seed, identifier policy, and
output format produce byte-identical data files and label sidecars, on CPython
3.12 on Linux x86_64, Linux arm64, and macOS arm64.

The manifest's `provenance` block, meaning `created_utc` and the invocation
line, is excluded. Everything else in the manifest is included.

Windows is not claimed and is not tested.

The engine also installs on CPython 3.13 and 3.14. Required CI runs the whole
suite, the golden bytes included, on those interpreters on the same three
platforms, and observes the same bytes. The claim recorded in every manifest
still names CPython 3.12: `verify` holds the `determinism` block to the engine's
fixed text, so widening the recorded list would fail every dataset minted so
far. The recorded claim widens with the next manifest schema revision, which
is a version event of its own.

## Why the claim is narrow on purpose

Every term in it is load-bearing.

**Engine version.** A change to the generator changes the bytes. That is why a
change altering emitted bytes for a fixed seed is a major version event even
when no function signature moved.

**Pack digest, not pack version.** Two builds of one version can differ. The
digest is what a consumer can check.

**Identifier policy and output format.** Both change what is written, so both
belong in the claim rather than in the small print.

**Those three platforms.** Each one is a promise someone has to keep. Widening
the list is a decision, not a configuration change.

## What makes it hold

**No floating point in emitted data.** Monetary values are integer kuruş in a
field suffixed `_kurus`; rates and ratios are decimal strings. The emission
encoder refuses a float rather than formatting one, because a float's text form
depends on the platform's formatting of a binary approximation.

**No transcendental function in the mint path.** libm results differ across
platforms and across libm versions on one platform, so a single `math.log` would
make the claim false on a machine nobody tested. Log-normal distributions are
sampled from 1024-knot inverse-CDF tables generated offline by
`tools/gen_tables.py`, committed with checksums, and interpolated with integer
arithmetic and floor division.

**No model anywhere.** Generation is deterministic grammar plus curated lexicons
plus seeded streams.

**Per-site streams.** Every value comes from a stream derived from the master
seed and a stable site path such as `customer/17/first_name`. Sites are
therefore independent: adding a field to a record type shifts no other field's
values, where a single shared stream would shift everything after the insertion
point and silently invalidate every published manifest.

**A NUL separator in stream derivation.** Joining the derivation's fields
without one lets a pack named `ab` at version `c` hash identically to a pack
named `a` at version `bc`, aliasing two different streams into one.

**Unbiased draws.** Bounded draws use rejection sampling rather than modulo, so
no residue class is over-represented.

**Canonical serialization.** UTF-8, LF, one record per line, a trailing newline,
ASCII escaping off, and object keys in the order the record type declares them.
Declaration order rather than sorted or insertion order, so that a serializer
change cannot report a mismatch that is not one.

**A fixed clock.** Wall-clock time never influences data content. Timestamps
come from the recipe's window through the record's own stream and render with
the fixed `+03:00` offset, which is correct because Turkey moved to permanent
UTC+3 in 2016. That fact is verified against the IANA database and recorded in
`normative-verification.md`.

## Reproducing a published dataset

You need the artifacts, the pack at the version the manifest records, and a core
in the range the pack pins.

    mintmark verify ./dataset      # recompute every checksum and re-extract every span
    mintmark reproduce ./dataset   # re-mint from the manifest and compare bytes

`verify` checks that the dataset is internally consistent and untampered.
`reproduce` checks something stronger: that the recorded inputs still produce
these exact bytes. A dataset whose checksums were updated after an edit passes
the first and fails the second.

A dataset does not carry its pack, so `reproduce` looks for it in a fixed set of
places: a `pack` directory inside the dataset, a directory named after the pack
beside the dataset or in the working directory, `packs/<name>` under the working
directory, the working directory itself, and, for the example pack, the copy the
engine ships. Running `reproduce` from inside a checkout of the pack is the
simplest way to satisfy it. When none of those holds a matching pack the error
names every place it looked.

## How the claim is checked

`tests/golden/demo-run/` holds the committed output of

    mintmark mint --pack packs/example --recipe demo --seed 42

as bytes, not as a re-execution. A test that mints twice in one process proves
the code is a function of its inputs; only committed bytes prove that today's
code is the same function yesterday's was.

Required CI runs the whole suite, including that comparison, on all three
platforms in the same workflow run. A platform where the bytes differ fails the
build rather than quietly narrowing the claim.

## If a golden test fails

Do not update the golden files to make it pass. Emitted bytes moving for a fixed
seed breaks the reproducibility of every published manifest. Find out what
changed, decide whether it should have, and if it should, record the decision
and treat it as a major version event.
