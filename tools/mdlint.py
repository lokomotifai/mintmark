#!/usr/bin/env python3
"""Prose lint for repository markdown.

Enforces the language rules of the lokomotifai public repository standard,
section 4, as executable checks rather than as advice:

1. Sentence-case headings.
2. Banned vocabulary in any language, including in docs and code comments.
3. The em dash U+2014 and the en dash U+2013 never appear in repository prose.
   Hyphen-minus is unrestricted.

Scope. Fenced code blocks and inline code spans are excluded from the prose
checks, because they carry commands and identifiers rather than prose. Every
other line of every tracked markdown file is checked.

Allowlist. Quoted third-party text is exempted with HTML comment markers, so
that the exemption is visible in the source and reviewable in a diff:

    <!-- mdlint-allow: quoting the Apache-2.0 header verbatim -->
    a single exempt line follows this marker

    <!-- mdlint-allow-start: quoting an upstream model card -->
    several exempt lines
    <!-- mdlint-allow-end -->

A marker without a reason is itself an error. The reason is the point: an
exemption a reviewer cannot evaluate is an exemption nobody granted.

Exit codes: 0 clean, 1 violations found, 2 usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# These two literals are the subject of rule 3. RUF001 flags them as ambiguous
# characters, which is exactly why they are banned in prose and exactly why
# this lint must contain them.
EM_DASH = "—"
EN_DASH = "–"  # noqa: RUF001

# Section 4.2 of the repository standard. English terms and their Turkish
# equivalents are one list, because the rule binds "any language" and the
# Turkish README mirror is repository prose like any other file.
BANNED_TERMS: dict[str, str] = {
    "revolutionary": "en",
    "revolutionize": "en",
    "transformative": "en",
    "seamless": "en",
    "seamlessly": "en",
    "cutting-edge": "en",
    "next-gen": "en",
    "next-generation": "en",
    "intelligent": "en",
    "game-changing": "en",
    "game-changer": "en",
    "powerful": "en",
    "power": "en",
    "ai-powered": "en",
    "devrim": "tr",
    "devrimsel": "tr",
    "transformatif": "tr",
    "kusursuz": "tr",
    "en ileri": "tr",
    "yeni nesil": "tr",
    "akilli": "tr",
    "akıllı": "tr",
    "oyun degistirici": "tr",
    "oyun değiştirici": "tr",
    "guclu": "tr",
    "güçlü": "tr",
    "guc": "tr",
    "güç": "tr",
}

# Words that may legitimately carry an interior capital in a sentence-case
# heading: proper nouns, acronyms, and product names.
PROPER_NOUNS: frozenset[str] = frozenset(
    {
        "Mintmark",
        "Hushmark",
        "Pactmark",
        "Permitmark",
        "Komunite",
        "Komünite",
        "GitHub",
        "PyPI",
        "Python",
        "CPython",
        "Apache",
        "Renovate",
        "CycloneDX",
        "Turkish",
        "Turkey",
        "Türkiye",
        "English",
        "Linux",
        "macOS",
        "Windows",
        "SemVer",
        "JSON",
        "YAML",
        "CSV",
        "JSONL",
        "UTF",
        "LF",
        "SHA",
        "RFC",
        "CI",
        "CLI",
        "API",
        "README",
        "SBOM",
        "OIDC",
        "PRNG",
        "CDF",
        "NER",
        "KVKK",
        "GDPR",
        "EU",
        "AI",
        "Act",
        "CC0",
        "DCO",
        "MIT",
        "ISO",
        "TCKN",
        "VKN",
        "IBAN",
        "PAN",
        "TCMB",
        "TBB",
        "KAP",
        "TSB",
        "TURKPATENT",
        "TÜRKPATENT",
        "EUIPO",
        "USPTO",
        "WIPO",
        "Mintmark's",
        "I",
        "A",
    }
)

ALLOW_ONE = re.compile(r"<!--\s*mdlint-allow:\s*(?P<reason>.*?)\s*-->")
ALLOW_START = re.compile(r"<!--\s*mdlint-allow-start:\s*(?P<reason>.*?)\s*-->")
ALLOW_END = re.compile(r"<!--\s*mdlint-allow-end\s*-->")
ALLOW_MALFORMED = re.compile(r"<!--\s*mdlint-allow(-start)?\s*(:\s*)?-->")

FENCE = re.compile(r"^\s*(?P<ticks>`{3,}|~{3,})")
INLINE_CODE = re.compile(r"`[^`]*`")
HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.+?)\s*#*\s*$")
EDGE_PUNCT = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    rule: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line_no}: {self.rule}: {self.detail}"


def strip_code(text: str) -> str:
    """Remove inline code spans so identifiers do not trip the prose rules."""
    return INLINE_CODE.sub(" ", text)


def heading_findings(path: Path, line_no: int, text: str) -> list[Finding]:
    words = LINK_TEXT.sub(r"\1", text).split()
    if not words:
        return []
    offenders = [
        w for w in words[1:] if w[:1].isupper() and EDGE_PUNCT.sub("", w) not in PROPER_NOUNS
    ]
    # One interior capital is normal prose. Two or more reads as Title Case.
    if len(offenders) >= 2:
        return [
            Finding(
                path,
                line_no,
                "sentence-case-heading",
                f"heading looks title-cased; capitalized words: {' '.join(offenders)}",
            )
        ]
    return []


def check_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    in_fence = False
    fence_marker = ""
    allow_block = False
    allow_next = False

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if ALLOW_MALFORMED.search(raw):
            findings.append(
                Finding(
                    path,
                    line_no,
                    "allowlist-without-reason",
                    "mdlint-allow marker carries no reason",
                )
            )

        if ALLOW_END.search(raw):
            allow_block = False
            continue
        if m := ALLOW_START.search(raw):
            allow_block = bool(m.group("reason"))
            continue
        if m := ALLOW_ONE.search(raw):
            allow_next = bool(m.group("reason"))
            continue

        fence_match = FENCE.match(raw)
        if fence_match:
            marker = fence_match.group("ticks")
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker.startswith(fence_marker[0]) and len(marker) >= len(fence_marker):
                in_fence, fence_marker = False, ""
            continue

        exempt = in_fence or allow_block or allow_next
        allow_next = False
        if exempt:
            continue

        prose = strip_code(raw)

        if EM_DASH in prose:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "forbidden-dash",
                    "em dash U+2014 in repository prose; use hyphen-minus",
                )
            )
        if EN_DASH in prose:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "forbidden-dash",
                    "en dash U+2013 in repository prose; use hyphen-minus",
                )
            )

        lowered = prose.lower()
        for term, lang in BANNED_TERMS.items():
            if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", lowered):
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "banned-vocabulary",
                        f"{term!r} ({lang}) is banned by the repository standard section 4.2",
                    )
                )

        if head := HEADING.match(raw):
            findings.extend(heading_findings(path, line_no, strip_code(head.group("text"))))

    if allow_block:
        findings.append(
            Finding(path, 0, "allowlist-unclosed", "mdlint-allow-start without a matching end")
        )
    return findings


def tracked_markdown(root: Path) -> list[Path]:
    """Prefer git so that ignored paths such as PLAN.md are never scanned."""
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "*.md",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return sorted(root / p for p in out.split("\0") if p)
    except (subprocess.CalledProcessError, FileNotFoundError):
        skip = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
        return sorted(p for p in root.rglob("*.md") if not any(part in skip for part in p.parts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=".", help="directory to scan")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"mdlint: not a directory: {root}", file=sys.stderr)
        return 2

    files = tracked_markdown(root)
    findings = [f for path in files for f in check_file(path)]

    for finding in findings:
        print(finding.render(), file=sys.stderr)

    if findings:
        print(f"\nmdlint: {len(findings)} violation(s) in {len(files)} file(s)", file=sys.stderr)
        return 1
    print(f"mdlint: clean, {len(files)} file(s) checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
