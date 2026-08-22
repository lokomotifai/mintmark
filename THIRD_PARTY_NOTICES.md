# Third-party notices

Mintmark depends on the following third-party software. Their licenses apply to
their own code and are reproduced in full in the distributions of those
projects.

## Runtime dependencies

| Package | Purpose | License |
| --- | --- | --- |
| jsonschema | Draft 2020-12 validation of pack and manifest schemas | MIT |
| PyYAML | YAML tokenization beneath the strict pack loader | MIT |

The runtime dependency list is deliberately two entries long. Every addition is
recorded as a numbered decision before it is made.

## Development dependencies

Development dependencies are not redistributed with Mintmark and are pinned in
`uv.lock`. They are listed in `pyproject.toml` under the `dev` group.

## Data assets

Data assets that ship inside the package, meaning lexicons, distribution tables,
and the institution denylist, are produced for this project. Factual reference
data carries an inline source note with its public source and retrieval date at
the point of use. Entries appear here when an asset carries third-party terms.
As of this revision, no shipped data asset carries third-party terms.

## Software bill of materials

A CycloneDX SBOM is generated at release and attached to the release. This file
is the human-readable summary; the SBOM is the machine-readable record.
