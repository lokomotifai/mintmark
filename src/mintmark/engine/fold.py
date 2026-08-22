"""Turkish case and diacritic folding, with length preserved exactly.

`str.lower()` is wrong for Turkish twice over. It maps `I` to `i` where Turkish
maps it to `ı`, and it maps `İ` to `i` plus U+0307 COMBINING DOT ABOVE, which is
two code points where there was one.

That second behavior is not a cosmetic problem. Label spans are recorded as code
point offsets into the emitted text, so a fold that changes a string's length
shifts every span after it. A name containing `İ` would silently misalign every
label that followed it in the same document.

The table below therefore folds the Turkish-specific letters explicitly, before
any call to `lower()`, and a property test asserts that folding never changes a
string's code point count.
"""

from __future__ import annotations

# Applied before lowercasing. Every entry maps one code point to one ASCII code
# point, so the length of the result always equals the length of the input.
TURKISH_FOLD: dict[int, str] = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "I": "i",
        "ş": "s",
        "Ş": "s",
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "â": "a",
        "Â": "a",
        "î": "i",
        "Î": "i",
        "û": "u",
        "Û": "u",
    }
)


def fold(text: str) -> str:
    """Fold Turkish letters to ASCII and lowercase, preserving length.

    Order matters: the translation runs first so that `İ` becomes `i` directly
    rather than reaching `str.lower()` and expanding into two code points.
    """
    return text.translate(TURKISH_FOLD).lower()


def fold_for_local_part(text: str) -> str:
    """Fold a name into the character set an email local part may carry.

    Anything outside ASCII letters and digits after folding is dropped, which is
    the only place a length change is permitted, because the result is a new
    string rather than a span-bearing surface.
    """
    return "".join(ch for ch in fold(text) if ch.isascii() and ch.isalnum())
