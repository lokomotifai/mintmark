# Normative source verification record

Some facts this project depends on are not settled by any document inside it.
They live in public registries and specifications that move, and coding them from
memory would produce software that is confidently wrong. This file records what
was verified, against which sources, on what date, and what the outcome was.

Each entry names its owning milestone. An entry whose source can drift is also
wired into the cadence workflow, so that a fact verified once does not quietly
stop being true.

## VKN check digit algorithm

**Owning milestone:** WP-03. **Verified:** 2026-08-22. **Drift risk:** low. The
algorithm is fixed by the tax administration and has not changed in the period
covered by the sources below.

**Why this needed verifying rather than implementing.** A subtly wrong check
digit algorithm still produces ten plausible digits. Safe mode would still emit
something, and it would still look correct. What breaks silently is the safety
claim: values intended to be provably invalid could land on valid ones, and no
test written against the same wrong algorithm would notice.

**Sources.** Two independent open implementations, in different languages, by
different authors:

1. `python-stdnum`, module `stdnum/tr/vkn.py`, by Arthur de Jong, LGPL 2.1.
   Retrieved 2026-08-22 from
   <https://raw.githubusercontent.com/arthurdejong/python-stdnum/master/stdnum/tr/vkn.py>.
   Carries a documented test vector: `4540536920` valid, `4540536921` an invalid
   checksum.
2. A JavaScript implementation published as a public gist by Ziyahan Albeniz,
   retrieved 2026-08-22 from <https://gist.github.com/ziyahan/3938729>. Written
   independently and structured differently, unrolling the nine positions rather
   than looping.

**Method.** Both implementations were transcribed and executed against 200 000
pseudorandomly generated nine-digit inputs, comparing the check digit each
produced.

**Outcome.** Zero disagreements across 200 000 inputs. Both reproduce the
published vector. The algorithm is:

    total = 0
    for position, digit in enumerate(reversed(first_nine), start=1):
        shifted = (digit + position) mod 10
        if shifted != 0:
            total += (shifted * 2**position) mod 9, or 9 when that is zero
    check = (10 - total) mod 10

The published vector is asserted as a test, so that a later refactor cannot drift
away from the algorithm that was verified without the suite failing.

## TCMB bank code 99999, unassigned status

**Owning milestone:** WP-03. **Verified:** 2026-08-22. **Drift risk:** real. The
participant list changes as institutions are licensed, merge, and are wound up.
**Wired into the cadence workflow.**

**Why this needed verifying.** Both identifier policies emit IBANs carrying the
bank code 99999. Under the validator policy the check digits are deliberately
correct, so the fictional bank code is the only thing standing between a
generated IBAN and one that names a real institution. If the code were assigned,
a checksum-valid synthetic IBAN would point at a real bank.

**Source.** TCMB Ödeme Sistemleri Katılımcıları, revision 072025, retrieved
2026-08-22 from
<https://www.tcmb.gov.tr/wps/wcm/connect/9fa62a85-5b6d-46c5-9b01-eb461d43723d/TCMB+%C3%96deme+Sistemleri+Kat%C4%B1l%C4%B1mc%C4%B1lar%C4%B1+(072025).pdf?MOD=AJPERES>

**Method.** The published list was extracted to text and every participant code
was enumerated.

**Outcome.** 71 participants. Codes are four digits, zero-padded, spanning 0001
through 0807. Nothing in the 9xxxx range appears, and the code 99999 does not
appear anywhere in the document. Turkish IBANs carry the four-digit code widened
to five digits, so a real bank code in an IBAN falls in the 00001 to 00807 range.
99999 is therefore not merely unassigned today; it lies far outside the allocated
space and could not become assigned without a renumbering of the whole scheme.

**If this changes.** The cadence workflow re-fetches the list. If a 9xxxx code
appears, select another unassigned five-digit code by the same procedure, record
the substitution as a new decision, and treat the change as a major version event,
because it alters emitted bytes for every previously published seed.

## Reserved documentation domain names

**Owning milestone:** WP-03. **Verified:** 2026-08-22. **Drift risk:** very low.

RFC 2606 section 2 reserves `example.com`, `example.net`, and `example.org`. RFC
6761 section 6.5 reserves the `.example` top-level domain. These names cannot be
registered by anyone, which is what makes a generated address unable to reach a
real mailbox. The engine emits nothing outside this set, and a test sweeps every
generated address to prove it.

## Turkish mobile numbering, absence of a reserved fictional range

**Owning milestone:** WP-03. **Verified:** 2026-08-22. **Outcome: negative, and
the negative result is the finding.**

Unlike the United Kingdom, which reserves 07700 900000 to 07700 900999 for drama
and documentation, and North America, which reserves 555-0100 to 555-0199, the
Turkish numbering plan sets aside no mobile range guaranteed never to be assigned.

There is therefore no engineering fix. A generated Turkish mobile number can
coincide with an assigned one. Both READMEs state this limitation and state the
purpose limitation that follows: this data is for testing systems, never for
contacting anyone.

## Institution denylist

**Owning milestone:** WP-05. **Verified:** 2026-08-22. **Drift risk:** real.
Institutions are licensed, merge, rename, and are wound up. **Wired into the
cadence workflow.**

**Source.** The same TCMB participant list used for the bank code check, revision
072025, retrieved 2026-08-22. It names 71 licensed institutions, which is the
authoritative public register of who actually exists.

**Outcome.** 70 denylist entries, covering all 71 participants. Every entry is
matched back against the institution it came from by a test, so an entry that
cannot match its own source fails the build.

**Two extraction rules, both learned from a miss rather than anticipated.**

Stripping legal-form and category words is necessary, because every fictional
bank this project generates contains the word "bank" and an unstripped entry
would match all of them. But stripping went too far twice.

First, a short brand disappeared. "T. İŞ BANKASI A.Ş." reduces to "is", two
characters, which fell below the minimum entry length and silently removed one of
the country's largest banks from the list. Short cores now keep the whole name.

Second, a connector was dropped. "YAPI VE KREDİ BANKASI A.Ş." became the phrase
"yapi kredi bankasi", and because matching is contiguous, that phrase never
appears inside the institution's own name. The entry matched nothing while
looking like coverage, which is worse than an absent entry. Connectors inside a
name are now preserved.

**The opposing constraint.** Several real institutions are named after ordinary
Turkish words: hayat means life, dunya means world, hedef means target, destek
means support, is means work. An entry consisting of one of those alone fires on
ordinary prose in every document this project generates, and a lint that cries
wolf is switched off within a week. Generic cores therefore keep the whole name
too, and a test sweeps ten ordinary Turkish sentences to prove none of them trips
the scan.

## Turkey's permanent UTC+3 status

**Owning milestone:** WP-07. **Verified:** 2026-08-22. **Drift risk:** low, but
real: it is a policy decision, and Turkey changed it once already.

**Why this needed verifying.** Timestamps are rendered with a fixed `+03:00`
offset. If Turkey still observed daylight saving, that rendering would be wrong
for roughly half of every year, and wrong in a way no test written inside this
project could notice.

**Source.** The IANA time zone database, zone `Europe/Istanbul`, as shipped with
CPython through `tzdata`. Retrieved 2026-08-22.

**Method.** The UTC offset and daylight-saving offset were evaluated in January,
April, July, and October of 2017, 2020, 2023, 2026, 2027, and 2030.

**Outcome.** One distinct offset across the whole range: `+03:00`, with a
daylight-saving offset of zero at every sampled instant. Turkey moved to
permanent UTC+3 in 2016. The fixed rendering is correct.

**If this changes.** A reintroduction of daylight saving makes the fixed offset
wrong. The correct response is a proper zone-aware rendering and a major version
bump, not a widened tolerance.

## Turkish insurance companies, and a real brand that reached a fictional lexicon

**Owning milestone:** the insurance pack's lexicon work. **Verified:**
2026-08-22. **Drift risk:** real. **Wired into the cadence loop.**

**What went wrong first.** The core denylist is built from the payment systems
participant register, which lists banks. It cannot catch a collision with an
insurer, and one was already sitting in the insurance pack's fictional lexicon:
Bereket Sigorta, a real company incorporated in 1995 and acquired by the Turkish
Wealth Fund in 2023.

The name reached a fictional list because "bereket" is an ordinary Turkish word
for abundance. That is the same property the denylist's generic-word rule exists
to handle, but in the opposite direction: the rule stops an ordinary word from
firing on ordinary prose, and nothing stopped an ordinary word from being chosen
as an invented brand that happens to be taken.

The root turned out to be in three lexicons across two packs and in the core's own
organization descriptors. All of them were corrected, and the family was
re-scanned against the widest list available.

**Source.** A public compilation of Turkish insurance, reinsurance, and pension
companies, retrieved 2026-08-22, cross-checked against individual company records
for the entries that mattered.

**A limitation of this verification, stated rather than papered over.** The
Turkish insurance association publishes the authoritative member list, and its
page renders client side; it could not be read programmatically. The list used
here is a public compilation of 40 companies, which is not the same as the
authoritative register. It is enough to have caught a real collision and it is
not enough to prove there are none. The cadence workflow re-checks it, and a
manual read of the association's own page belongs in the release checklist.

**Outcome.** 110 denylist entries in the insurance pack: the core's banks plus 40
insurers. Every fictional name in all three packs and in the core descriptors was
scanned against it, and the family is clean.

## Still to verify

These belong to milestones that have not run yet and are listed so that nobody
mistakes their absence for a completed check.

| Fact | Owning milestone | Wired into cadence |
| --- | --- | --- |
| Taxonomy pin against the hushmark-tr closed v0.1 label set | WP-04 | Yes |

## How to add an entry

Verify first, write the entry, then write the code. An entry added after the code
records what was believed rather than what was checked, which is the failure mode
this file exists to prevent.
