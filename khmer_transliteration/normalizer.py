"""Input normalization shared by dictionary, rule generation, and UI routes."""

import re


def normalize_input(text):
    """Normalize one romanized word: lowercase, remove spaces, reduce repeats."""
    text = text.lower().strip()
    text = re.sub(r"\s+", "", text)
    text = reduce_repeated_letters(text)
    return text


def normalize_phrase_input(text):
    """Normalize a space-separated phrase while preserving single word gaps."""
    parts = re.split(r"\s+", text.lower().strip())
    normalized_parts = [
        normalize_input(part)
        for part in parts
        if part
    ]
    return " ".join(normalized_parts)


def reduce_repeated_letters(text):
    """Collapse very long key repeats, while allowing normal double letters."""
    return re.sub(r"([a-z])\1{2,}", r"\1", text)
