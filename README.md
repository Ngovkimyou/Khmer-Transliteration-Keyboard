# Khmer Transliteration Keyboard

Romanized Khmer to Khmer script suggestion system with dictionary lookup,
rule-based generation, fuzzy lookup, manual ranking labels, and a simple
FastAPI UI.

## Project Structure

- `khmer_transliteration/` - core Python package
  - `candidate_generator.py` - rule-based candidate generation
  - `suggestion_engine.py` - dictionary/rule/fuzzy/ML suggestion merge
  - `dictionary_lookup.py` - dataset lookup helpers
  - `mapping_rules.py` - mapping rule loader
  - `collection.py` - manual ranking-label CSV collection
  - `web.py` - FastAPI app implementation
  - `paths.py` - shared project paths
- `data/` - CSV datasets and `mapping_rules.json`
  - `user_selection_history.csv` - auto-created from clicked suggestions
  - `word_pair_frequency.csv` - auto-created previous-word pair counts
- `models/` - trained ranking model artifacts
- `scripts/` - command-line reports, training, and data utilities
- `reports/` - generated HTML/text reports
- `static/` and `assets/` - UI files and images
- `app.py` - compatibility wrapper for `uvicorn app:app`
- `docs/scoring_logic_snapshot.md` - current scoring/ranking reference

## Common Commands

```powershell
python scripts/candidate_test_report.py
python scripts/suggestion_test_report.py
python scripts/train_ranking_model.py --max-inputs 500 --candidates-per-input 10
python scripts/collect_ranking_examples.py somtos leakk
python scripts/auto_label_training_examples.py --dry-run
python scripts/auto_label_training_examples.py --overwrite-auto
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Retrain the ranking model after collecting selection history or word-pair data
so ML can learn the new context/history features.

By default, training skips fuzzy and compound generation for speed. Add
`--include-fuzzy` or `--include-compound` when you want slower, broader training.

## Auto-label UI-collected Ranking Rows

`data/ranking_training_examples.csv` is for candidates collected from the UI.
Use the auto-label tool to compare those existing rows against `data/all_words.csv`.

Preview labels without writing:

```powershell
python scripts/auto_label_training_examples.py --dry-run
```

Write auto labels. Existing human labels are preserved:

```powershell
python scripts/auto_label_training_examples.py --overwrite-auto
```

Label only specific collected inputs:

```powershell
python scripts/auto_label_training_examples.py chir som --overwrite-auto
```

Process only the first few collected inputs:

```powershell
python scripts/auto_label_training_examples.py --max-inputs 10 --dry-run
```

The default mode only labels rows already collected from the UI. It labels
dataset-matching Khmer candidates as `1`, labels wrong candidates above/between
correct matches as `0`, and leaves lower rows blank.

Dataset-wide generation is still available, but it must be requested explicitly:

```powershell
python scripts/auto_label_training_examples.py --from-dataset --max-inputs 100 --dry-run
```
