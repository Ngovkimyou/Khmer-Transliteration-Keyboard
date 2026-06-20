import re

def normalize_input(text):
    text = text.lower().strip()
    text = re.sub(r"\s+", "", text)
    text = reduce_repeated_letters(text)
    return text


def reduce_repeated_letters(text):
    return re.sub(r"([a-z])\1{2,}", r"\1", text)
