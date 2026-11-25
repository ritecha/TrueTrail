# TrueTrail — AI-Powered Cyber Investigation & Digital Forensics

**Problem Statement:** PS03 — Digital Evidence Correlation and Crime Reconstruction Engine  
**Team:** TrueTrail

---

## 1. Overview

TrueTrail is an AI-powered cyber-investigation and digital-forensics prototype designed to correlate heterogeneous financial and digital evidence, reconstruct fraud incidents, detect suspicious mule accounts and transaction chains, and provide investigators with an evidence-linked visual investigation workspace.

The system combines:

- Forensic evidence ingestion
- SHA-256 evidence integrity
- Multi-format extraction
- OCR processing
- Data normalization
- Entity mapping and disambiguation
- Cross-source correlation
- Temporal and spatial analysis
- Machine-learning based risk detection
- SHAP explainability
- Graph/network reconstruction
- Fund-flow and transaction-chain analysis
- Investigator dashboard and visualization
- AI-assisted interpretation with human review

### Core Pipeline

```text
Evidence Upload
      ↓
SHA-256 + Custody Logging
      ↓
Extraction + OCR + Validation
      ↓
Normalization + Field Mapping
      ↓
Canonical Evidence Store
      ↓
Cross-Source Correlation
      ↓
Timeline / Spatial / Graph Analysis
      ↓
XGBoost + SHAP Detection
      ↓
Fund-Flow / Chain Reconstruction
      ↓
FastAPI Services
      ↓
React/Vite Investigation Workspace
      ↓
Graph + Timeline + Map + Ledger
      ↓
Evidence-Linked Findings
```

---

# 2. Problem Statement

Digital-payment fraud investigations often require evidence from multiple independent sources such as banks, UPI systems, telecom records, IP addresses, devices and transaction records.

The major challenge is that this evidence is heterogeneous and investigators may have to manually correlate:

- Bank accounts
- Transactions
- UPI identifiers
- Phone numbers
- Devices
- IP addresses
- Calls
- Locations
- Multiple transaction chains

TrueTrail attempts to convert these disconnected evidence sources into a unified investigation view.

The platform is designed to help investigators move from:

```text
Individual Evidence
        ↓
Connected Entities
        ↓
Suspicious Relationships
        ↓
Timeline
        ↓
Money Trail
        ↓
Network Reconstruction
        ↓
Investigation Findings
```

---

# 3. Objectives

The major objectives of TrueTrail are:

1. Automate heterogeneous evidence ingestion.
2. Preserve original evidence and maintain traceability.
3. Generate SHA-256 integrity hashes.
4. Normalize inconsistent source formats.
5. Map different source fields into canonical fields.
6. Correlate accounts, transactions, phones, devices and IP addresses.
7. Detect suspicious transactions.
8. Identify potential mule accounts.
9. Detect developing transaction chains.
10. Reconstruct money movement.
11. Generate entity and transaction graphs.
12. Generate chronological investigation timelines.
13. Perform spatial correlation where geographic evidence exists.
14. Explain ML predictions using SHAP.
15. Provide investigators with an interactive workspace.
16. Keep AI-generated interpretation separate from raw evidence.
17. Provide human review for ambiguous or high-impact findings.

---

# 4. System Architecture

```text
                    ┌─────────────────────────┐
                    │      Evidence Sources   │
                    │ CSV XLSX PDF JSON OCR   │
                    │ Bank UPI Telecom Device │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Evidence Preservation   │
                    │ SHA-256 + Custody Log   │
                    │ Write-once Evidence     │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Extraction & Normalizing │
                    │ OCR / Parsing / Mapping │
                    │ Validation / Provenance │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Canonical Evidence Store│
                    │ SQLite / JSON / Records │
                    └────────────┬────────────┘
                                 │
                                 ▼
              ┌──────────────────┴──────────────────┐
              │                                     │
              ▼                                     ▼
     ┌───────────────────┐              ┌────────────────────┐
     │ Correlation Engine│              │ Temporal / Spatial │
     │ Entity Linking    │              │ Analysis            │
     │ Shared IDs        │              │ Timeline / Location │
     └─────────┬─────────┘              └──────────┬─────────┘
               │                                   │
               └────────────────┬──────────────────┘
                                ▼
                    ┌─────────────────────────┐
                    │ ML + Graph Analysis     │
                    │ XGBoost + SHAP          │
                    │ NetworkX + Chain Engine │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ FastAPI Investigation   │
                    │ Services / APIs         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ React/Vite Investigator │
                    │ Graph / Timeline / Map   │
                    │ Ledger / Chat / Reports  │
                    └─────────────────────────┘
```

---

# 5. Technology Stack

## Backend

- Python
- FastAPI
- Uvicorn
- Pydantic
- HTTPX
- python-multipart

## Data Extraction

- Pandas
- OpenPyXL
- PDFPlumber
- PyPDFium2
- CSV
- JSON
- NDJSON

## OCR and Image Processing

- Tesseract OCR
- Pytesseract
- OpenCV
- Pillow

## Data Processing and Normalization

- NumPy
- RapidFuzz
- difflib
- Regex
- Decimal
- datetime
- ipaddress

## Storage and Integrity

- SQLite
- JSON/JSONL
- SHA-256
- hashlib
- Filesystem-based evidence storage
- Custody/audit logs

## Machine Learning

- XGBoost
- scikit-learn
- Joblib

## Explainability

- SHAP

## Graph and Spatial Analysis

- NetworkX
- GeoPandas
- Shapely
- PyProj
- GeoIP2

## Visualization

- Streamlit
- Plotly
- PyVis
- Leaflet

## Frontend

- React
- Vite
- JavaScript/JSX
- React Force Graph
- React Leaflet
- Framer Motion
- GSAP
- Lenis

## AI Integration

The project contains integration points for:

- Ollama
- OpenAI
- Google Gemini
- Groq

---

# 6. Data Flow

## Step 1 — Evidence Upload

The investigator uploads evidence files such as:

```text
CSV
XLSX
JSON
PDF
TXT
Images
Scanned Documents
```

The system determines the appropriate extraction method.

---

## Step 2 — Evidence Preservation

Before analysis, the system can calculate a SHA-256 hash and preserve the original evidence.

```text
Original Evidence
       ↓
SHA-256 Hash
       ↓
Evidence Vault
       ↓
Custody / Audit Log
```

The original evidence is separated from derived/processed data.

---

## Step 3 — Evidence Extraction

Different extraction pipelines are used for different formats.

Examples:

```text
CSV / TXT
   ↓
Pandas / Parser

XLSX
   ↓
OpenPyXL

PDF
   ↓
PDFPlumber / PyPDFium2

Scanned PDF / Image
   ↓
OCR
   ↓
Tesseract / OpenCV / Pillow

JSON / NDJSON
   ↓
JSON Parser
```

---

# 7. Normalization and Mapping

Different banks, telecom providers and evidence sources may use different column names for the same concept.

The mapping layer uses techniques such as:

- Exact aliases
- Fuzzy matching
- Content-based matching
- Context/statistical matching
- Saved mapping templates
- Optional AI suggestions
- Human review

Example:

```text
"Acct No."
"Account Number"
"A/C Number"
"Beneficiary Account"
        ↓
Canonical Field
        ↓
account_id
```

The system is designed to preserve ambiguous mappings instead of silently guessing.

---

# 8. Canonical Evidence Store

After extraction and normalization, evidence is converted into canonical records.

Examples include:

- Transactions
- Calls
- IP sessions
- Device records
- Account records
- Extended evidence
- Rejected rows
- Provenance information
- Validation flags

Conceptually:

```text
Raw Evidence
     ↓
Extracted Records
     ↓
Normalized Records
     ↓
Canonical Records
     ↓
Correlation
```

---

# 9. Cross-Source Correlation

TrueTrail connects entities using shared identifiers and relationships.

Example:

```text
                 ┌─────────────┐
                 │   Account   │
                 └──────┬──────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   Transaction        Phone          Device
        │               │               │
        ▼               ▼               ▼
      UPI/RRN         Call Log        IP Address
                        │               │
                        └───────┬───────┘
                                ▼
                           Investigation
```

Correlation can include:

- Shared account identifiers
- Shared phone numbers
- Shared devices
- Shared IP addresses
- Transaction relationships
- UPI/RRN relationships
- Communication relationships
- Corroborated evidence

---

# 10. Temporal Analysis

Events are aligned using normalized timestamps.

The system can investigate relationships such as:

```text
Phone Call
      ↓
Short Time Interval
      ↓
UPI / Bank Transfer
```

A call followed by a transaction can become a confidence-bearing correlation.

It should not automatically be interpreted as proof of criminal intent.

---

# 11. Spatial Analysis

Where geographic information exists, TrueTrail can correlate:

- IP geolocation
- Device/location information
- Transaction locations
- Other available geographic evidence

This allows investigators to explore whether multiple events have meaningful spatial relationships.

---

# 12. Graph Analysis

NetworkX is used to represent connected entities and relationships.

Typical graph nodes can represent:

- Accounts
- Transactions
- Phone numbers
- Devices
- IP addresses

Edges can represent:

- Money transfers
- Shared identifiers
- Communication
- Device relationships
- IP relationships
- Corroborated transaction relationships

Example:

```text
Victim
  │
  ▼
Mule Account A
  │
  ▼
Mule Account B
  │
  ▼
Cash-out / Destination
```

Graph analysis supports:

- Community detection
- Controller/handler analysis
- Circular fund flows
- Priority money paths
- Multi-hop relationships
- Suspicious transaction chains

---

# 13. Machine Learning

The supplied ML component contains four major XGBoost models:

### 1. Transaction Fraud

Identifies suspicious or potentially fraudulent transactions.

### 2. Sender Mule

Estimates whether a sending account exhibits mule-like behavior.

### 3. Receiver Mule

Estimates whether a receiving account exhibits mule-like behavior.

### 4. Developing Chain

Identifies suspicious developing transaction chains.

---

# 14. ML Pipeline

```text
Dataset
   ↓
Feature Engineering
   ↓
Train / Validation / Test Split
   ↓
XGBoost Training
   ↓
Threshold Selection
   ↓
Test Evaluation
   ↓
Model Serialization
   ↓
SHAP Explanation
   ↓
Inference
```

The supplied implementation also includes feature validation, leakage checks, overlap checks and model-evaluation utilities.

---

# 15. ML Test Results

The supplied test reports contain:

| Model             | Test Rows | Precision | Recall |    F1 | PR-AUC | ROC-AUC |
| ----------------- | --------: | --------: | -----: | ----: | -----: | ------: |
| Transaction Fraud |    35,859 |     78.3% |  49.7% | 60.8% |  69.5% |   95.5% |
| Sender Mule       |    35,859 |     89.6% |  76.4% | 82.5% |  87.6% |   97.6% |
| Receiver Mule     |    35,859 |     62.2% |  30.1% | 40.6% |  44.0% |   82.1% |
| Developing Chain  |     2,879 |     70.7% |  76.5% | 73.5% |  83.3% |   78.7% |

### Important

The supplied ML documentation identifies the data as **synthetic**.

Therefore, these results demonstrate prototype/model behavior and must not be presented as validated real-world banking-fraud performance.

---

# 16. SHAP Explainability

SHAP is used to identify the contribution of features to ML predictions.

Instead of only showing:

```text
Risk = HIGH
```

the system can provide feature-level explanation such as:

```text
High Risk

Contributing factors:
+ High transaction amount
+ High transaction velocity
+ Short transaction interval
+ Suspicious historical behavior
```

SHAP explains model behavior; it does not independently establish causation or criminal intent.

---

# 17. Integrated System Results

The supplied integrated artifacts contain the following outputs:

| Artifact                       | Result |
| ------------------------------ | -----: |
| Canonical transactions         |    108 |
| Canonical calls                |  1,176 |
| Evidence items                 |      4 |
| Rejected rows                  |      8 |
| Network nodes                  |    185 |
| Network edges                  |    592 |
| Communities                    |      7 |
| Isolated accounts              |      0 |
| Circular fund-flow paths       |     10 |
| Priority/trace fund-flow paths |     10 |
| Spatial correlations           |  1,588 |
| Temporal correlations          |      0 |

These values represent outputs from the supplied prototype artifacts.

---

# 18. Investigation Workspace

The frontend provides an investigator-oriented workspace containing functionality around:

- Evidence upload
- Graph visualization
- Timeline analysis
- Maps
- Transaction ledger
- Investigation workspace
- Group/agent chat
- AI-assisted investigation
- Evidence-linked results

The frontend uses React/Vite and includes graph and mapping components.

---

# 19. AI Investigation Layer

TrueTrail contains integration points for local and external AI models.

The intended workflow is:

```text
Evidence
   ↓
Deterministic Processing
   ↓
AI Interpretation
   ↓
Rule Verification
   ↓
Human Investigator
   ↓
Final Finding
```

The design principle is:

> **AI proposes, rules verify, human approves.**

AI output should not silently modify or replace raw forensic evidence.

---

# 20. Forensic Integrity

The system maintains a separation between evidence and interpretation.

```text
RAW EVIDENCE
      ↓
HASH + PRESERVE
      ↓
EXTRACT
      ↓
NORMALIZE
      ↓
ANALYZE
      ↓
INTERPRET
      ↓
INVESTIGATOR REVIEW
```

Important integrity mechanisms include:

- SHA-256 hashing
- Evidence vault
- Custody/audit logging
- Provenance
- Source references
- Raw-value preservation
- Review queues
- Validation flags

---

# 21. Human Review

Human review is particularly important for:

- Ambiguous field mappings
- OCR uncertainty
- Conflicting identifiers
- Multiple possible entity matches
- AI-generated interpretations
- Suspicious findings requiring approval

The system is designed so that uncertainty can remain visible instead of being silently converted into certainty.

---

# 22. Project Structure

The supplied project consists of multiple components.

```text
TrueTrail/
│
├── Forensic Backend
│   ├── routes
│   ├── extraction
│   ├── classification
│   ├── mapping
│   ├── disambiguation
│   ├── normalization
│   ├── validation
│   ├── correlation
│   ├── storage
│   └── audit
│
├── Fraud Link Integrated
│   ├── multi-format ingestion
│   ├── network correlation
│   ├── temporal/spatial analysis
│   ├── ML inference
│   ├── chain inference
│   ├── canonical data
│   └── outputs
│
├── Machine Learning
│   ├── feature engineering
│   ├── model training
│   ├── evaluation
│   ├── model artifacts
│   └── SHAP reports
│
└── Frontend
    ├── React/Vite
    ├── investigation workspace
    ├── graph
    ├── timeline/map
    ├── ledger
    └── chat/agent
```

---

# 23. Testing and Validation

The supplied source includes testing and validation utilities for areas such as:

- Pipeline testing
- Integrated pipeline testing
- Agent testing
- Feature verification
- Feature auditing
- Leakage checking
- Dataset overlap checking
- Timestamp validation
- Historical feature verification
- Graph evaluation
- SHAP/model explanation

This supports validation of the processing and ML pipeline beyond simple manual testing.

---

# 24. Running the Project

Because the supplied project contains multiple components, commands should be executed from the relevant component directory.

## Python Dependencies

```bash
pip install -r requirements.txt
```

## FastAPI

Use the configured application entry point:

```bash
uvicorn <app_module>:app --reload
```

## React/Vite Frontend

```bash
npm install
npm run dev
```

## Machine Learning

The ML component contains scripts for:

- Feature generation
- Model training
- Evaluation
- Threshold selection
- Model serialization
- SHAP analysis

Run the supplied scripts from the ML project directory.

---

# 25. Deployment

The supplied project references deployment/testing through technologies and services including:

- GitHub
- Render
- Pytest
- unittest

A production deployment would additionally require:

- Secure secret management
- Authentication and authorization
- Database security
- Evidence retention policy
- Encryption
- Access logging
- Secure network configuration
- Model monitoring
- Data validation
- Formal forensic workflow controls

---

# 26. Limitations

### Synthetic ML Dataset

The ML results are based on supplied synthetic data and require validation against representative real-world datasets.

### Receiver Mule Detection

The receiver-mule model has comparatively low recall in the supplied test results and requires improvement before high-recall operational deployment.

### Temporal Correlation

The supplied integrated artifact reports zero temporal correlations. This should be investigated against the available evidence and timestamps rather than artificially creating relationships.

### OCR

OCR is not perfectly accurate. OCR-derived evidence requires confidence-aware processing and human verification.

### AI

AI-generated interpretations must be verified and should not automatically become authoritative forensic findings.

### Production Security

The prototype requires further security, authentication, access-control, retention and forensic-policy hardening before use with sensitive real-world evidence.

---

# 27. Future Enhancements

1. Validate models using representative real-world datasets.
2. Improve receiver-mule recall.
3. Expand temporal correlation rules.
4. Improve OCR confidence handling.
5. Add additional evidence-source adapters.
6. Expand investigator review workflows.
7. Improve graph ranking and controller/mastermind analysis.
8. Expand case-management capabilities.
9. Harden authentication and authorization.
10. Implement production-grade encryption and key management.
11. Add model monitoring and drift detection.
12. Formalize forensic/legal evidence procedures.
13. Improve reporting and export capabilities.
14. Add richer investigator collaboration features.

---

# 28. References

The supplied `TrueTrail_SUTRAM_2026_PPT.pdf` contains the project's reference list, including:

- Preetha P. — _Toward an Integrated Digital-Age Framework for Forensic Accounting and Fraud Detection_
- KPMG India & FICCI — _Next-gen forensic: The new age of fraud investigation_
- Ministry of Finance, Department of Financial Services, Government of India
- Misra, G. — _Permeance of ICT in crime in India_
- Thakkar & Datta — _Red flags and hidden trails_
- Reserve Bank of India
- CyberPeace resources on Operation Mule Hunt

The complete citations and URLs should be taken from the supplied SUTRAM presentation.

---

# 29. Team

**Team Name:** TrueTrail

The supplied SUTRAM presentation lists:

- **Dhruvika Verma** — Team Leader
- **Manya Mehta** — Member
- **Jaya** — Member
- **Ritika** — Member

---

# 30. Conclusion

TrueTrail combines digital-forensics evidence preservation, multi-source normalization, entity correlation, machine learning, explainability, graph analysis, timeline reconstruction and investigator visualization into a single prototype workflow.

The overall investigation pipeline is:

```text
UPLOAD
  ↓
SHA-256 + CUSTODY
  ↓
EXTRACT
  ↓
NORMALIZE
  ↓
CORRELATE
  ↓
DETECT
  ↓
EXPLAIN
  ↓
RECONSTRUCT
  ↓
VISUALIZE
  ↓
INVESTIGATOR REVIEW
```

The central design principle is to make complex digital-fraud investigations faster while maintaining evidence traceability, explainability and human control over ambiguous and AI-assisted findings.

---

## Deliverables

The project documentation package contains:

- `TrueTrail_Technical_Documentation.docx`
- `truetrail_architecture.png`
- `truetrail_data_flow.png`
- `TrueTrail_Editable_Diagrams.pptx`
- `README.md` — this document
