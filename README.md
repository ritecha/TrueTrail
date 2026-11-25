# Suspicious Transaction Detection Using Machine Learning

## 1. Project Overview

This project focuses on identifying suspicious financial transaction patterns using machine learning and graph-based transaction analysis. It uses XGBoost classification models to detect fraudulent transactions, mule accounts, and developing suspicious transaction chains.

The system analyzes transaction-level, historical, and chain-level features to identify potentially suspicious activities. It also incorporates data validation, leakage checks, model evaluation, and SHAP-based explainability.

**Note:** The current implementation uses synthetic data and represents a machine learning prototype. The results should not be interpreted as real-world banking fraud detection performance.

## 2. Project Objectives

- Detect potentially fraudulent financial transactions.
- Identify sender and receiver mule accounts.
- Detect suspicious transaction chains as they develop.
- Generate transaction-level and historical features.
- Analyze relationships and patterns across transaction chains.
- Validate features and check for potential data leakage.
- Evaluate model performance using standard classification metrics.
- Interpret model predictions using SHAP explainability.

## 3. Machine Learning Models

Four separate XGBoost classification models have been implemented.

| Model | Purpose |
|---|---|
| Transaction Fraud | Identifies potentially fraudulent transactions. |
| Sender Mule | Predicts whether the sender account is a mule account. |
| Receiver Mule | Predicts whether the receiver account is a mule account. |
| Developing Chain | Identifies suspicious patterns developing across transaction chains. |

Each model is trained and evaluated independently using its corresponding feature set and target label.

## 4. Technology Stack

- **Programming Language:** Python
- **Data Processing:** Pandas, NumPy
- **Machine Learning:** Scikit-learn, XGBoost
- **Model Serialization:** Joblib
- **Explainable AI:** SHAP
- **Visualization:** Matplotlib
- **Development Environment:** Visual Studio Code

## 5. Dataset and Feature Engineering

The project uses synthetic financial transaction data for model development and evaluation.

### Main Dataset Files

| Dataset | Description |
|---|---|
| `training_dataset_original.csv` | Original synthetic transaction dataset. |
| `features_txn.csv` | Processed transaction-level feature dataset. |
| `features_chain_snapshots.csv` | Chain-level snapshot dataset used for developing-chain detection. |

### Feature Engineering

The feature engineering pipeline prepares different types of information:

- Transaction-level features.
- Historical transaction features.
- Chain-level snapshot features.
- Transaction amount and frequency patterns.
- Account activity and connectivity patterns.
- Time intervals and transaction sequence information.

These features provide the input required by the different classification models.

## 6. Data Validation and Auditing

Several validation scripts are included to check the quality and reliability of the generated datasets and features.

| Script | Purpose |
|---|---|
| `audit_features.py` | Audits generated features. |
| `check_components.py` | Checks project components. |
| `check_features.py` | Checks feature data and consistency. |
| `check_leakage.py` | Checks for potential data leakage. |
| `check_overlap_results.py` | Checks overlap between dataset splits or records. |
| `check_timestamps.py` | Checks timestamp consistency. |
| `inspect_data.py` | Inspects the input dataset. |
| `inspect_dates.py` | Inspects date and timestamp information. |
| `verify_features.py` | Verifies generated features. |
| `verify_historical.py` | Verifies historical feature generation. |

These scripts support dataset inspection, feature validation, and checks intended to reduce errors during model development.

## 7. Model Training and Evaluation

The training pipeline performs the following steps:

1. Loads the prepared feature datasets.
2. Creates training, validation, and testing splits.
3. Handles missing receiver information where required.
4. Trains four separate XGBoost classification models.
5. Selects classification thresholds using validation data.
6. Evaluates the models on the test data.
7. Saves trained model bundles and evaluation reports.

### Evaluation Metrics

The models are evaluated using:

- **Precision:** Measures how many predicted positive cases are actually positive.
- **Recall:** Measures how many actual positive cases are identified.
- **F1-score:** Provides a balance between precision and recall.
- **PR-AUC:** Measures precision-recall performance across different classification thresholds.

### Test Results

| Model | Precision | Recall | F1-score | PR-AUC |
|---|---:|---:|---:|---:|
| Transaction Fraud | 78.3% | 49.7% | 60.8% | 69.5% |
| Sender Mule | 89.6% | 76.4% | 82.5% | 87.6% |
| Receiver Mule | 62.2% | 30.1% | 40.6% | 44.0% |
| Developing Chain | 70.7% | 76.5% | 73.5% | 83.3% |

*All results are based on synthetic test data.*

## 8. Developing Chain Detection

The developing-chain model analyzes transaction chains through sequential snapshots.

It uses features such as:

- `hop_index`
- `unique_accounts_so_far`
- `total_amount_so_far`
- `mean_amount_so_far`
- `max_amount_so_far`
- `first_amount`
- `last_amount`
- `last_to_first_amount_ratio`
- `duration_sec_so_far`
- `mean_gap_sec`
- `last_gap_sec`
- `max_fan_out_so_far`
- `max_fan_in_so_far`
- `has_cycle_so_far`

These features represent transaction progression, amount variation, time intervals, account connectivity, and chain structure.

The model attempts to identify suspicious patterns before a transaction chain is fully developed.

## 9. Explainability Using SHAP

SHAP (SHapley Additive exPlanations) is used to understand the contribution of input features to the developing-chain model's predictions.

The explainability pipeline:

1. Loads the trained developing-chain model.
2. Loads the chain snapshot test data.
3. Applies the model's preprocessing pipeline.
4. Computes SHAP values using TreeExplainer.
5. Generates feature importance and visualization outputs.

### Top Influential Features

Based on mean absolute SHAP values:

| Feature | Mean Absolute SHAP |
|---|---:|
| `last_to_first_amount_ratio` | 0.715161 |
| `mean_gap_sec` | 0.349168 |
| `max_amount_so_far` | 0.287453 |
| `last_gap_sec` | 0.131515 |
| `mean_amount_so_far` | 0.122355 |
| `unique_accounts_so_far` | 0.120086 |
| `last_amount` | 0.118968 |
| `first_amount` | 0.068796 |
| `duration_sec_so_far` | 0.068538 |
| `hop_index` | 0.061428 |

The results indicate that transaction amount ratios, time gaps, and transaction amounts contribute strongly to the developing-chain model's predictions.

Mean absolute SHAP values represent the magnitude of feature contributions, not their direction or causality.

## 10. Prediction and Graph Evaluation

The project also includes supporting scripts:

| Script | Purpose |
|---|---|
| `predict.py` | Runs predictions using trained models. |
| `evaluate_graphs.py` | Evaluates graph-related results. |
| `configure.py` | Configuration-related utility. |
| `config.py` | Stores project configuration, dataset paths, model directories, report directories, and feature settings. |

These scripts support prediction, graph-related evaluation, and project configuration.

## 11. Project Structure

```text
Ml training-github/
│
├── data/
│   ├── training_dataset_original.csv
│   ├── features_txn.csv
│   └── features_chain_snapshots.csv
│
├── models/
│   ├── transaction_fraud.joblib
│   ├── sender_mule.joblib
│   ├── receiver_mule.joblib
│   └── developing_chain.joblib
│
├── reports/
│   ├── metrics.json
│   ├── model_comparison.csv
│   ├── chain_shap_importance.csv
│   │
│   ├── chain_shap_summary.png
│   ├── chain_shap_importance.png
│   └── chain_shap_individual.png
│
├── scripts/
│   └── make_sample_data.py
│
├── audit_features.py
├── build_chain_snapshots.py
├── build_features.py
├── build_historical_features.py
├── check_components.py
├── check_features.py
├── check_leakage.py
├── check_overlap_results.py
├── check_timestamps.py
├── configure.py
├── config.py
├── evaluate_graphs.py
├── explain_models.py
├── inspect_data.py
├── inspect_dates.py
├── predict.py
├── train_models.py
├── verify_features.py
├── verify_historical.py
│
├── README.md
├── requirements.txt
└── .gitignore
```

*The structure represents the intended organization. Actual file and folder locations should match the repository. Additional generated images can be included in the reports directory.*

## 12. Generated Outputs

### Trained Models

The trained model bundles are saved in the `models/` directory:

- `transaction_fraud.joblib`
- `sender_mule.joblib`
- `receiver_mule.joblib`
- `developing_chain.joblib`

Each saved model bundle contains the trained model, feature configuration, and selected classification thresholds.

### Evaluation Reports

The `reports/` directory contains:

- `metrics.json` — Model evaluation metrics.
- `model_comparison.csv` — Comparison of model performance.
- `chain_shap_importance.csv` — SHAP feature importance values.

### SHAP Visualizations

The following visualizations are generated:

- `chain_shap_summary.png` — SHAP summary plot showing feature contributions.
- `chain_shap_importance.png` — Feature importance visualization.
- `chain_shap_individual.png` — Individual prediction explanation.

## 13. Installation and Execution

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd <project-folder>
```

### Step 2: Create a Virtual Environment

```bash
python -m venv .venv
```

### Step 3: Activate the Environment

For Windows using Git Bash:

```bash
source .venv/Scripts/activate
```

### Step 4: Install Dependencies

```bash
pip install pandas numpy scikit-learn xgboost joblib shap matplotlib
```

### Step 5: Prepare the Dataset

Ensure the required CSV files are available at the paths specified in `config.py`.

### Step 6: Generate Features

Run the relevant feature-generation scripts if the processed feature files need to be created:

```bash
python build_features.py
python build_historical_features.py
python build_chain_snapshots.py
```

### Step 7: Train the Models

```bash
python train_models.py
```

### Step 8: Generate SHAP Explanations

After successful model training:

```bash
python explain_models.py
```

### Step 9: Run Predictions

```bash
python predict.py
```

Additional auditing, verification, and graph evaluation scripts can be executed independently when required.

## 14. Limitations

- The current implementation uses synthetic data.
- Model performance may differ significantly on real banking datasets.
- Receiver mule detection currently has comparatively lower recall.
- SHAP explanations describe model behavior and do not establish causation.
- Model predictions indicate suspicious patterns and should not be treated as confirmed fraud.
- Real-world deployment would require validation on representative, securely handled financial data.

## 15. Glossary and Acronyms

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
## 16. Conclusion

The project demonstrates a multi-model machine learning approach to suspicious transaction detection. It combines transaction-level fraud classification, sender and receiver mule identification, developing-chain detection, feature engineering, data validation, model evaluation, and SHAP-based explainability.
By integrating these components, the prototype provides a foundation for analyzing suspicious financial transaction patterns and further experimentation with validated real-world datasets.
