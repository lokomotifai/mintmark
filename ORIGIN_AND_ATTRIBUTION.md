# Origin and attribution

This file records where Mintmark came from and what it incorporates from
others. It is maintained as a register, not as a one-time statement.

## Origin

Mintmark originates in the lokomotifai product family and is the fourth
repository in it. The family enforces one doctrine at different boundaries:
authority stays outside the model, and every run leaves verifiable evidence.
Mintmark seals the data supply boundary.

## Attribution register

| Item | Source | What is used | Terms |
| --- | --- | --- | --- |
| Personal-data label taxonomy | The hushmark-tr closed v0.1 label set | The twelve NER label names, pinned by digest | Same organization; pin recorded in every manifest |
| Code of conduct | Contributor Covenant | Adapted text | CC BY 4.0, attribution retained in the file |
| Reserved domain names | RFC 2606 and RFC 6761 | The `.example` top-level domain and the example.com family | Public specifications |

## Data provenance

Mintmark generates data. It ingests none. No real personal data, no customer
data, and no production data of any kind is used to build, train, fit, or tune
anything in this repository. There is no model to train, because generation is
deterministic grammar plus curated lexicons plus seeded streams.

Factual reference data, meaning place names and public registry lists, carries
an inline source note with the public source and the retrieval date at the point
of use, and is versioned like code. Those notes are the authority; this file
does not duplicate them.

## Adding an entry

A new dependency, a vendored asset, or a borrowed text adds a row above in the
same change that introduces it. An entry added later than the code it describes
is a review failure.
