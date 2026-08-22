# Mintmark and KVKK

<sub><a href="kvkk.tr.md">Türkçe</a></sub>

Turkish data protection law is the reason this project exists, so it deserves a
plain statement rather than a sentence buried in a README.

**This is not legal advice.** It is a description of what this project produces
and what it does not, written so that your own counsel has something concrete to
assess.

## The law

Kişisel Verilerin Korunması Kanunu, law number 6698, in force since 2016 and
amended in March 2024. It defines personal data as information relating to an
identified or identifiable natural person, and it singles out a set of
categories for stricter treatment.

## Why synthetic data is a different question

Personal data has a data subject: a real person the information relates to. The
data this project produces has none.

Every value is computed from a seed by a deterministic function. No real record
is read, no model trained on real records is involved, and nothing is
transformed from a real person's data into a fictional one. There is no original
that a value corresponds to, no re-identification path back to anyone, and no
person whose rights attach to it.

That is a statement about how the data is produced, and it is verifiable rather
than asserted: the manifest records the engine version, the pack digest, the
recipe and the seed, and `mintmark reproduce` re-derives the identical bytes
from them.

This is different from anonymization, and the difference matters. Anonymized
data began as somebody's personal data. This never was.

## The special categories, and how they are labeled

Article 6 enumerates the categories that receive stricter treatment: race and
ethnic origin, political opinion, philosophical belief, religion, sect or other
beliefs, appearance and dress, association, foundation or union membership,
health, sexual life, criminal conviction and security measures, and biometric
and genetic data.

The taxonomy this project pins carries labels for most of them, because a
detector cannot be measured on what a dataset never contains:

| Article 6 category | Label in this taxonomy |
| --- | --- |
| Race, ethnic origin | `ETHNICITY` |
| Political opinion | `POLITICAL` |
| Philosophical belief, religion, sect, other beliefs | `RELIGION` |
| Union membership | `UNION` |
| Health | `HEALTH` |
| Sexual life | `SEXUAL_LIFE` |
| Criminal conviction and security measures | `CRIMINAL` |
| Biometric data | `BIOMETRIC_REF` |
| Appearance and dress | no label |
| Association or foundation membership | no label; `UNION` covers unions only |
| Genetic data | no label |

Three gaps are stated rather than left to be discovered. A detector evaluated
against these datasets is not evaluated on those three, and a coverage number
from this project should not be read as covering them.

**A span labeled `HEALTH` in this data is not health data about anybody.** It is
a fictional phrase in a fictional document, labeled so that a detector can be
scored on whether it found it. The label describes the category a detector
should recognize, not a fact about a person.

## What this project does not claim

It is not a compliance guarantee. No dataset makes a system lawful, and nothing
here is a defense to anything.

It is not anonymization of your data. This project ingests nothing. If you need
to make real records safe, that is a different problem and this is not the tool.

It says nothing about your processing. Whether your system's handling of real
personal data satisfies the law depends on your system, your purpose, your legal
basis and your safeguards. None of those are visible from here.

## What it does give you

A test environment you can fill without moving real records into it, and an
evaluation set you can measure a detector against. Those are the two places
where teams most often end up copying production data, and both are avoidable.

## Two boundaries worth knowing before you ingest

**Identifier policy.** The default is `safe`, which emits values that fail their
own checksum on purpose, so nothing generated can be mistaken for an assigned
identifier. An opt-in `validator` policy produces checksum-valid values for
teams testing their own validation logic; every such dataset carries a warning
in its manifest, and every reference dataset published by this project is minted
`safe`.

**Phone numbers.** The Turkish numbering plan reserves no fictional range, so a
generated number can coincide with an assigned one. Never contact a number from
this data. This is recorded in the README as a known limitation and is not
fixable from inside the project.

## Reporting a problem

If you believe a dataset here contains something that relates to a real person,
that is a security issue and not a bug report. Use the private route in
[SECURITY.md](../SECURITY.md).
