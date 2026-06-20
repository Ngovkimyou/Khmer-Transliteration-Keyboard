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
- `models/` - trained ranking model artifacts
- `scripts/` - command-line reports, training, and data utilities
- `reports/` - generated HTML/text reports
- `static/` and `assets/` - UI files and images
- `app.py` - compatibility wrapper for `uvicorn app:app`

## Common Commands

```powershell
python scripts/candidate_test_report.py
python scripts/suggestion_test_report.py
python scripts/train_ranking_model.py
python scripts/collect_ranking_examples.py somtos leakk
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
