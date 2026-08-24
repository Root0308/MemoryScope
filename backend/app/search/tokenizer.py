import unicodedata


CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F),
    (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF),
    (0x2CEB0, 0x2EBEF),
    (0x30000, 0x323AF),
)


def _is_cjk_character(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in CJK_RANGES)


def _append_cjk_tokens(tokens: list[str], characters: list[str]) -> None:
    if not characters:
        return
    tokens.extend(characters)
    tokens.extend(
        characters[index] + characters[index + 1]
        for index in range(len(characters) - 1)
    )
    characters.clear()


def tokenize(text: str) -> list[str]:
    """Tokenize normalized Latin/numeric words and Chinese uni/bi-grams."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    word: list[str] = []
    word_kind: str | None = None
    cjk_characters: list[str] = []

    def flush_word() -> None:
        nonlocal word_kind
        if word:
            tokens.append("".join(word))
            word.clear()
        word_kind = None

    for character in normalized:
        if _is_cjk_character(character):
            flush_word()
            cjk_characters.append(character)
            continue

        _append_cjk_tokens(tokens, cjk_characters)
        character_kind = (
            "letter"
            if character.isalpha()
            else "number"
            if character.isdecimal()
            else None
        )
        if character_kind is None:
            flush_word()
            continue
        if word_kind != character_kind:
            flush_word()
            word_kind = character_kind
        word.append(character)

    flush_word()
    _append_cjk_tokens(tokens, cjk_characters)
    return tokens
