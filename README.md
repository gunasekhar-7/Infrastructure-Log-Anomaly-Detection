# 🛡️ LogPulse AnomalyGuard: Infrastructure Log Anomaly Detection & Incident Monitoring Platform

A production-grade, end-to-end intelligent monitoring system that transforms heterogenous infrastructure logs into structured event templates, performs multi-model anomaly detection (Isolation Forest, Rolling Z-score/IQR, and DeepLog-style sequential LSTM), and correlates signals into prioritized operational incidents with actionable evidence.

---

## 🌟 Key Features

- **Online Log Template Mining:** High-throughput streaming log clustering and dynamic masking powered by **Drain3**.
- **Multi-Model Anomaly Detection Ensemble:**
  - *Statistical Detector:* Outlier identification across sliding-window event frequency and error spikes.
  - *Isolation Forest:* Multivariate feature space anomaly isolation.
  - *DeepLog Sequential LSTM:* Top-$K$ candidate prediction across event sequences for detecting broken execution paths and abnormal system state transitions.
- **Explainability & Attribution:** Pinpoints exact offending log lines, anomalous template IDs, and unexpected event transitions.
- **Intelligent Incident Correlation:** Cooldown-based alert deduplication and spatio-temporal clustering to combat alert fatigue.
- **Modern Full-Stack Architecture:**
  - Asynchronous **FastAPI** backend with OpenAPI specifications.
  - **PostgreSQL 16** (with SQLite zero-dependency local testing).
  - Multi-page **Streamlit** incident investigation workbench.
  - Native **Prometheus** metrics export.
  - Fully containerized with **Docker Compose**.

---

## 📁 Repository Structure

```text
infrastructure-log-anomaly-detection/
├── config/                 # Pydantic v2 BaseSettings, Drain3 configuration, and logging setup
├── docker/                 # Production Dockerfiles and Prometheus scraping config
├── data/                   # Raw, processed, and synthetic log storage (gitignored)
├── models/                 # Serialized model weights and checkpoints
├── src/
│   ├── ingestion/          # Multi-format log ingestion, validation, and normalization
│   ├── parsing/            # Drain3 template mining and masking rules
│   ├── features/           # Sliding-window frequency and sequence builders
│   ├── models/             # Statistical, Isolation Forest, and DeepLog LSTM detectors
│   ├── intelligence/       # Attribution, explainability, alert management, and incident correlation
│   ├── database/           # SQLAlchemy 2.0 ORM models and async connection management
│   ├── api/                # FastAPI application, routes, and schemas
│   └── dashboard/          # Streamlit monitoring and investigation UI
├── tests/                  # Pytest unit, integration, and E2E suites
├── pyproject.toml          # Package configuration and dependencies
└── docker-compose.yml      # Local multi-service orchestration
```

---

## 🚀 Quickstart

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/your-username/infrastructure-log-anomaly-detection.git
cd infrastructure-log-anomaly-detection

# Copy example environment configuration
cp .env.example .env

# Install dependencies
pip install -r requirements-dev.txt
```

### 2. Run Tests

```bash
pytest
```

### 3. Launch via Docker Compose

```bash
docker-compose up --build
```
- **FastAPI API & Docs:** `http://localhost:8000/docs`
- **Streamlit Dashboard:** `http://localhost:8501`
- **Prometheus Metrics:** `http://localhost:9090`
