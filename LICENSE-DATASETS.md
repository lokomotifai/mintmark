# Dataset license

This file covers **data**, not code. The code in this repository is Apache-2.0;
see `LICENSE`.

## The terms

Reference datasets published from this repository are licensed under the
**Creative Commons Attribution 4.0 International** license.

    SPDX identifier   CC-BY-4.0
    Full legal text   https://creativecommons.org/licenses/by/4.0/legalcode
    Plain summary     https://creativecommons.org/licenses/by/4.0/

The full text is not copied into this repository. It is a legal instrument
maintained by Creative Commons, and a transcribed copy that drifts from the
canonical one is worse than a pointer to it.

## What that means in practice

You may use these datasets for any purpose, including commercially, and you may
redistribute and adapt them. The one condition is that you credit the source.

That condition is deliberate. Commercial use is exactly what these datasets are
for: a bank, an insurer, or an employer filling a test environment is a
commercial user, and forbidding that would forbid the intended reader. What the
attribution condition prevents is somebody stripping the provenance and passing
the work off as their own.

## How to attribute

Every dataset carries its own credit line. It is in `MINTMARK.json` under
`license.attribution`, and `mintmark verify` prints it:

    mintmark-example 0.1.0 reference dataset (recipe demo, seed 42), lokomotifai, licensed CC-BY-4.0

Reproduce that line, or an equivalent that names the dataset, the source, and
the license. You do not need to construct it yourself, and you do not need to
ask permission.

The line is generated from the pack name, pack version, recipe, and seed, so two
runs that differ in any of those are different datasets and carry different
lines.

## What this license does not do

It grants no right to the Mintmark name or logo. Trademark is separate from
copyright and is covered in `TRADEMARKS.md`.

It makes no claim about your use being lawful. These datasets are synthetic and
contain no personal data, and that is a statement about their contents, not a
compliance opinion about your system. See `docs/kvkk.md`.

## Status

**Pending legal confirmation.** The license is declared here and written into
every manifest this repository produces, and confirmation by counsel is a
checkpoint before the first release. Nothing has been released yet.

## Why this changed

Earlier drafts proposed CC0-1.0, which places a work in the public domain and
requires nothing of anyone. It was chosen to remove friction from enterprise
legal review. It also meant a published dataset could be resold with the
provenance removed and no credit given anywhere.

Attribution keeps the enterprise path open, because CC BY is as routine in legal
review as CC0, while making the source impossible to strip silently. The manifest
carries the credit line so the requirement is machine readable rather than a
sentence in a README nobody downloads.
