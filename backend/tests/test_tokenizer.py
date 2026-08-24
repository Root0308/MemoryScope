import pytest

from app.search.tokenizer import tokenize


def test_tokenizes_english_letters_and_numbers() -> None:
    assert tokenize("Hello agent007 memory 42") == [
        "hello",
        "agent",
        "007",
        "memory",
        "42",
    ]


def test_tokenizes_chinese_unigrams_and_adjacent_bigrams() -> None:
    assert tokenize("用户喜欢") == [
        "用",
        "户",
        "喜",
        "欢",
        "用户",
        "户喜",
        "喜欢",
    ]


def test_tokenizes_mixed_chinese_english_and_numbers() -> None:
    assert tokenize("Memory用户42") == [
        "memory",
        "用",
        "户",
        "用户",
        "42",
    ]


def test_applies_nfkc_normalization() -> None:
    assert tokenize("Ｍｅｍｏｒｙ ① 用户") == [
        "memory",
        "1",
        "用",
        "户",
        "用户",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("HELLO, World!", ["hello", "world"]),
        ("  hello---WORLD...", ["hello", "world"]),
        ("中，文", ["中", "文"]),
    ],
)
def test_lowercases_and_ignores_whitespace_and_punctuation(
    text: str,
    expected: list[str],
) -> None:
    assert tokenize(text) == expected
