# Scoring Logic Snapshot

Date: 2026-06-21

This file records the current ranking/scoring behavior so we can compare later
if auto-labeling or ML ranking changes cause bad results.

## Candidate Sources

Suggestions can come from:

- `direct_*`: direct consonant / independent vowel / vowel key options.
- `dictionary_exact`: exact `romanized -> khmer` dataset match.
- `dictionary_completion`: dataset word starts with typed input.
- `dictionary_compound`: input split into known/generated word chunks.
- `phrase_space`: explicit space-separated romanized words combined into one Khmer phrase.
- `dictionary_fuzzy`: fuzzy romanized dataset match, enabled for input length >= 5.
- `rule_*`: rule-generated candidates from `candidate_generator.py`.

## Source Rank Weights

Final ranking no longer uses `source_priority * 100`.

Current source weights in `khmer_transliteration/suggestion_engine.py`:

```python
SOURCE_RANK_WEIGHTS = {
    "direct": 6.0,
    "dictionary_exact": 5.0,
    "dictionary_completion": 3.5,
    "phrase_space": 3.0,
    "dictionary_compound": 2.5,
    "dictionary_fuzzy": 2.0,
    "rule": 1.0,
}
```

These are trust weights, not hard ordering. A fuzzy/history/context candidate can
beat a compound candidate if its learned scores are stronger.

## Space-Separated Phrase Input

If the user types spaces, spaces are preserved as word boundaries:

```text
chnang touch
chnang     touch
```

Both normalize to:

```text
chnang touch
```

Then each word is suggested separately and combined:

```text
chnang -> ឆ្នាំង
touch  -> តូច
result -> ឆ្នាំងតូច
```

This uses source `phrase_space`, with source weight `3.0`.

This path is different from no-space compound segmentation:

```text
chnangtoch
```

No-space input still uses `dictionary_compound`.

Phrase suggestions also use learned pair scores between selected segment options,
so:

```text
nh jg -> ខ្ញុំចង់
```

can benefit from the saved pair `ខ្ញុំ + ចង់`.

## Main Score Components

Each suggestion has a normal `score`, then `rank_score` is computed from that.

`score` can include:

- base dictionary/rule/fuzzy/compound score
- dataset match score
- user history score
- previous word context score
- compound pair context score
- high-confidence fuzzy boost
- compound no-dataset penalty

Current `rank_score` formula:

```python
rank_score =
    source_rank_weight
    + manual_label_score * 10
    + score
    + ml_score * 0.25
```

Then suggestions sort by:

```python
(
    rank_score,
    manual_label_score,
    source_rank_weight,
    frequency,
)
```

descending.

So source weight is no longer a hard wall. Strong fuzzy matches, manual labels,
history, and context can beat weaker compound guesses.

## Dataset Match Score

If a candidate Khmer exists in the dataset, it receives a dataset boost:

```python
DATASET_KHMER_EXISTS_BOOST = 0.25
DATASET_ROMANIZED_SIMILARITY_BOOST = 0.75
DATASET_FREQUENCY_BOOST_FACTOR = 0.001
```

Dataset score is added into `suggestion["score"]`.

## Source Quality Adjustments

High-confidence fuzzy dataset matches should outrank unsupported compound guesses.

Current constants:

```python
HIGH_CONFIDENCE_FUZZY_THRESHOLD = 0.90
HIGH_CONFIDENCE_FUZZY_BOOST = 1.35
COMPOUND_NO_DATASET_PENALTY = 0.75
```

Behavior:

- `dictionary_fuzzy` gets `+1.35` when `fuzzy_score >= 0.90` and the candidate exists in the dataset.
- `dictionary_compound` gets `-0.75` when it has no dataset match and no learned compound pair context.
- Learned compound pairs, such as `nhjg -> ខ្ញុំចង់`, are protected from this compound penalty.

Fields:

```python
high_confidence_fuzzy_boost
compound_no_dataset_penalty
source_quality_adjustment
```

These are added into `suggestion["score"]` before `rank_score` is calculated.

Example goal:

```text
chnang -> ឆ្នាំង
```

because `chnang` is close to dataset romanized `chhnang`.

## Manual Labels

Manual labels come from `data/ranking_training_examples.csv`.

- `label = 1`: strong boost.
- `label = 0`: strong demotion.
- blank: ignored.

Manual label scoring:

```python
manual_label_score = 1   # label 1
manual_label_score = -1  # label 0
manual_label_score = 0   # blank/missing
```

Because `rank_score` uses `manual_label_score * 10`:

- label `1` adds about `+10`.
- label `0` subtracts about `-10`.

Label `0` does not delete a suggestion; it pushes it lower.

## User Selection History

User clicks are stored in:

```text
data/user_selection_history.csv
```

Current score constants:

```python
USER_HISTORY_BOOST_FACTOR = 0.5
USER_HISTORY_MAX_BOOST = 2.00
```

Each repeated click for the same `(input, khmer)` adds `+0.5` up to `+2.0`.

This score is stored as:

```python
user_history_score
```

and added into `suggestion["score"]`.

## Previous Word Context

Clicked word pairs are stored in:

```text
data/word_pair_frequency.csv
```

Current score constants:

```python
PREVIOUS_WORD_BOOST_FACTOR = 0.5
PREVIOUS_WORD_MAX_BOOST = 2.00
```

Each pair click adds `+0.5` up to `+2.0`.

This supports:

- previous selected word -> next suggestion
- compound pair context inside `dictionary_compound`, such as `nhjg -> ខ្ញុំចង់`

Fields:

```python
previous_word_context_score
compound_pair_context_score
```

Both are added into `suggestion["score"]`.

## ML Ranking

ML is a reranking helper, not the only ranking system.

Current ML influence:

```python
rank_score += ml_score * 0.25
```

So ML gently adjusts close candidates. It does not override manual labels,
history, context, or strong dictionary/rule scores.

Current ML features in `khmer_transliteration/ranking_features.py`:

```python
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
```

If the model was trained with an old feature list, ML scores may be skipped until
retraining.

Recommended fast retrain:

```powershell
python scripts/train_ranking_model.py --max-inputs 500 --candidates-per-input 10
```

Training skips fuzzy and compound by default for speed.

Use slower options only when needed:

```powershell
--include-fuzzy
--include-compound
```

## Auto-Label Logic

Auto-label tool:

```powershell
python scripts/auto_label_training_examples.py
```

Important behavior:

1. Group dataset by romanized input.
2. Treat all dataset Khmer outputs for the same romanized input as valid.
3. Generate suggestions once per romanized input.
4. Label dataset-valid suggestions as `1`.
5. Label non-dataset candidates before/between valid outputs as `0`.
6. Leave candidates after the last valid output blank/ignored.

Example:

```text
som -> {សុំ, សំ, សម}
```

All valid outputs are label `1`; only interfering candidates above/between them
become label `0`.

Safe preview:

```powershell
python scripts/auto_label_training_examples.py som chir --limit 30 --dry-run
```

## UI Debug Pills

The UI currently shows useful debug pills:

- `rank`
- `source`
- `dataset`
- `context`
- `pair`
- `history`
- `fuzzy boost`
- `compound penalty`
- `ML`
- `manual`

These should help identify why one candidate ranked above another.
