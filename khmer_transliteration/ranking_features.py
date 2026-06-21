FEATURE_NAMES = [
    "rule_score",
    "remaining_length",
    "input_length",
    "romanized_length",
    "khmer_length",
    "length_difference",
    "token_count",
    "chunk_count",
    "previous_word_context_score",
    "user_history_score",
]


# Convert one suggestion into numeric features for the ML ranking model.
def extract_ranking_features(user_input, suggestion):
    romanized = suggestion.get("romanized", "")
    tokens = suggestion.get("tokens", [])
    chunks = suggestion.get("chunks", [])
    return [
        suggestion.get("rule_score", 0),
        suggestion.get("remaining_length", 0),
        len(user_input),
        len(romanized),
        len(suggestion.get("khmer", "")),
        abs(len(romanized) - len(user_input)),
        len(tokens),
        len(chunks),
        suggestion.get("previous_word_context_score", 0),
        suggestion.get("user_history_score", 0),
    ]
