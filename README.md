# TrueTrail

Mule Network Graphing and Spatiotemporal Correlation and Timeline Reconstruction
**All data in this repo is synthetic.**

## Quick start
```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                                   # 26 tests
uvicorn backend.api:app --reload --port 8000          # http://localhost:8000/docs
curl -X POST localhost:8000/ingest/synthetic          # load the demo dataset
```

## Layout
```
backend/schemas.py              canonical data contract (v1.1) - shared by everyone
backend/ingestion/config.py     column maps, date formats, narration rules  <- edit to add a new source format
backend/ingestion/parsers/      upi, cdr, bank_statement, ipdr, device_forensics
backend/ingestion/pipeline.py   detect -> parse -> dedupe -> reconcile
backend/storage.py              SQLite store (rebuilt from the evidence files)
backend/api.py                  FastAPI app
backend/synthetic/generator.py  scripted scenario generator (do NOT re-run casually: xlsx hash changes)
data/synthetic/                 golden dataset + ground_truth.json (answer key) + SHA256SUMS.txt
data/canonical/                 frozen sample of the parsed output
```

## Assumptions
* Every timestamp is stored in UTC. Sources: UPI log = UTC, bank/IPDR/device dump = IST, CDR = epoch.
* RRN links a UPI log row to the matching bank-statement rows; the UPI log wins and statements go in `corroborated_by`.
## 16. Glossary and Acronyms

### Acronyms

| Acronym | Full Form |
|---|---|
| AI | Artificial Intelligence |
| ML | Machine Learning |
| XGBoost | Extreme Gradient Boosting |
| SHAP | SHapley Additive exPlanations |
| CSV | Comma-Separated Values |
| JSON | JavaScript Object Notation |
| API | Application Programming Interface |
| AUC | Area Under the Curve |
| PR-AUC | Precision-Recall Area Under the Curve |
| TP | True Positive |
| FP | False Positive |
| FN | False Negative |
| TN | True Negative |
| UTC | Coordinated Universal Time |

### Glossary

| Term | Definition |
|---|---|
| Fraud Detection | Identifying transactions that may involve fraudulent activity. |
| Mule Account | An account used to receive or transfer potentially illicit funds. |
| Sender Mule | An account suspected of acting as a mule while sending funds. |
| Receiver Mule | An account suspected of acting as a mule while receiving funds. |
| Transaction Chain | A sequence of financial transactions connecting multiple accounts. |
| Developing Chain | A transaction chain analyzed as it progresses. |
| Feature Engineering | Creating useful input variables from raw data. |
| Historical Features | Features derived from previously observed transaction activity. |
| Chain Snapshot | A representation of a transaction chain at a particular stage. |
| Feature | An input variable used by a machine learning model. |
| Target Label | The outcome a model is trained to predict. |
| Classification | Assigning observations to predefined categories. |
| Training Set | Data used to train a machine learning model. |
| Validation Set | Data used to tune model settings and select thresholds. |
| Test Set | Unseen data used to evaluate model performance. |
| Data Leakage | Unintended use of information unavailable at prediction time. |
| Precision | Proportion of predicted positive cases that are actually positive. |
| Recall | Proportion of actual positive cases correctly identified. |
| F1-score | A metric combining precision and recall. |
| PR-AUC | A metric summarizing precision-recall performance across thresholds. |
| Classification Threshold | Probability cutoff used to assign a predicted class. |
| SHAP Value | A value representing a feature's contribution to a model prediction. |
| Feature Importance | A measure of a feature's influence on model predictions. |
| Model Bundle | A saved collection containing a trained model and its configuration. |
| Synthetic Data | Artificially generated data used for development and testing. |
| Graph Analysis | Analysis of relationships between entities represented as nodes and connections. |
| Fan-in | Number of incoming connections to an account or node. |
| Fan-out | Number of outgoing connections from an account or node. |
| Cycle | A path in a graph that returns to a previously visited node. |
| Joblib | A Python library used to save and load machine learning objects. |
* The same call appears as two CDR rows (caller side `OUT`, callee side `IN`); they are kept separate.
* Original uploaded files are the source of truth; the DB is disposable.

## Numbers on the synthetic set
5 files -> 4 schemas -> 274 transactions, 392 calls, 111 IP sessions, 25 device artifacts;
2 rejected, 3 duplicates removed, 93 cross-source matches, 14 IPDR chunks merged.
