from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
STATIC_DIR = ROOT_DIR / "static"
ASSETS_DIR = ROOT_DIR / "assets"
REPORTS_DIR = ROOT_DIR / "reports"

ALL_WORDS_FILE = DATA_DIR / "all_words.csv"
CUSTOM_WORDS_FILE = DATA_DIR / "custom_words.csv"
DATASET_SUMMARY_FILE = DATA_DIR / "dataset_summary.txt"
MAPPING_RULES_FILE = DATA_DIR / "mapping_rules.json"
RANKING_TRAINING_EXAMPLES_FILE = DATA_DIR / "ranking_training_examples.csv"
USER_SELECTION_HISTORY_FILE = DATA_DIR / "user_selection_history.csv"
WORD_PAIR_FREQUENCY_FILE = DATA_DIR / "word_pair_frequency.csv"

RANKING_MODEL_FILE = MODELS_DIR / "ranking_model.joblib"
RANKING_MODEL_METADATA_FILE = MODELS_DIR / "ranking_model_metadata.json"
RANKING_MODEL_REPORT_FILE = REPORTS_DIR / "ranking_model_report.txt"

CANDIDATE_TEST_REPORT_FILE = REPORTS_DIR / "candidate_test_report.html"
SUGGESTION_TEST_REPORT_FILE = REPORTS_DIR / "suggestion_test_report.html"
