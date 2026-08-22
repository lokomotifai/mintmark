# Taxonomy

## The closed set

Eighteen labels. Twelve named-entity types from the hushmark-tr v0.1 taxonomy:

    PERSON  ADDRESS  ORG  DOB  HEALTH  RELIGION
    ETHNICITY  POLITICAL  SEXUAL_LIFE  CRIMINAL  BIOMETRIC_REF  UNION

and six deterministic identifier labels:

    TCKN  VKN  IBAN  PAN  PHONE  EMAIL

Eight of the twelve carry special-category personal data: HEALTH, RELIGION,
ETHNICITY, POLITICAL, SEXUAL_LIFE, CRIMINAL, BIOMETRIC_REF, and UNION. A
recipe's `special_rate` governs how often they are injected into documents.

## Why the set is closed

A label outside the set fails closed: pack loading rejects it with exit code 2
and `verify` rejects it with exit code 3.

That strictness is what makes a Mintmark dataset usable as an evaluation set. A
detector scored against a label the taxonomy never defined produces a number
that means nothing, and the failure is silent unless something refuses the label
outright.

There is no PLATE label. The insurance pack emits vehicle plates unlabeled as a
result, which is settled in its brief rather than worked around.

## The pin

Every manifest records the taxonomy name, version, and a digest over the
canonical NER label list. The digest covers only the twelve upstream types, not
this project's own identifier labels, because upstream drift is what the pin
exists to detect.

The pin is computed locally, so verification needs no network. Checking it
against upstream is a cadence concern.

## Drift procedure

The weekly workflow re-checks the pin against the hushmark upstream. On drift it
opens an issue. It never re-pins automatically.

That is deliberate. A taxonomy change alters what every published dataset means,
so adopting one is a decision with a version consequence, not an update. The
steps:

1. Read what changed upstream and why.
2. Decide whether this project adopts it. A label added upstream that this
   project cannot generate surfaces for is not adoptable yet.
3. If adopting, record the decision, update the enum and the pin digest, and
   treat it as a major version event.
4. If not adopting, record why, and leave the pin where it is. A dataset pinned
   to v0.1 stays interpretable regardless of what v0.2 says.

## Special-category content

Special-category spans are drawn from curated, neutral-register Turkish
descriptor lexicons at category granularity: a class of thing, never a clinical
detail, never an accusation.

Organizations named in special-category context are fictional, including unions
and political parties. The person a special category attaches to is always
synthetic. A template never attaches a special category to a real organization
or a real public figure, and never uses defamatory framing.
