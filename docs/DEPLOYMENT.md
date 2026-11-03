# Production Deployment & Orchestration Guide

*LogPulse AnomalyGuard* is engineered for containerized multi-service deployment with Docker Compose, Kubernetes, or standalone Python environments.

---

## 1. Container Topology Architecture

```mermaid
flowchart TD
    subgraph Host ["Host Networking / Reverse Proxy"]
        Client["Browser / SRE Client"]
        Forwarder["Log Collectors (FluentBit / Vector)"]
    end

    subgraph Docker ["Docker Compose Network (logpulse-net)"]
        Nginx["Reverse Proxy / SSL (Optional)"]
        
        subgraph AppTier ["Application Services"]
            API["FastAPI Backend (logpulse-api:8000)"]
            Dash["Streamlit Dashboard (logpulse-dashboard:8501)"]
            Sim["Traffic Simulator (logpulse-simulator)"]
        end
        
        subgraph DataTier ["Persistence & Telemetry"]
            DB[("PostgreSQL 16 (logpulse-postgres:5432)")]
            Prom["Prometheus v2 (logpulse-prometheus:9090)"]
            VolDB[("Volume: postgres_data")]
            VolProm[("Volume: prometheus_data")]
        end
    end

    Client -->|HTTP 8501| Dash
    Forwarder -->|HTTP 8000| API
    Dash -->|Internal HTTP| API
    API -->|Async SQLAlchemy / asyncpg| DB
    DB --> VolDB
    Prom -->|Scrape /metrics| API
    Prom --> VolProm
    Sim -.->|Inject Logs (Profile: simulation)| API
```

---

## 2. Quickstart with Docker Compose

### Prerequisites
- Docker Engine $\ge 24.0.0$
- Docker Compose v2 $\ge 2.20.0$
- Minimum 4 GB RAM, 2 CPU cores

### Step 1: Clone and Configure Environment
```bash
git clone https://github.com/placeholder/logpulse-anomalyguard.git
cd "Infrastructure Log Anomaly Detection"

# Copy environment configuration
cp .env.example .env
```

### Step 2: Build and Launch Multi-Container Stack
```bash
# Build and run in detached mode
docker compose up -d --build

# Verify healthy startup of all services
docker compose ps
```

Expected output:
```text
NAME                   IMAGE                         STATUS                    PORTS
logpulse-postgres      postgres:16-alpine            Up (healthy)              0.0.0.0:5432->5432/tcp
logpulse-api           infrastructure-api:latest     Up (healthy)              0.0.0.0:8000->8000/tcp
logpulse-dashboard     infrastructure-dash:latest    Up (healthy)              0.0.0.0:8501->8501/tcp
logpulse-prometheus    prom/prometheus:v2.50.1       Up (healthy)              0.0.0.0:9090->9090/tcp
```

### Step 3: Access Platform Endpoints
- **Streamlit Interactive Dashboard:** [http://localhost:8501](http://localhost:8501)
- **FastAPI OpenAPI Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **FastAPI Health & Readiness Probe:** [http://localhost:8000/healthz](http://localhost:8000/healthz)
- **Prometheus Telemetry Scrape:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Prometheus UI & Graphing:** [http://localhost:9090](http://localhost:9090)

### Step 4: Run Continuous Traffic Simulation (Optional)
To run the automated synthetic background traffic generator inside Docker:
```bash
docker compose --profile simulation up -d simulator
```

---

## 3. Zero-Docker Standalone Execution Mode

For local development or testing without Docker, *LogPulse AnomalyGuard* automatically activates its SQLite asynchronous fallback (`sqlite+aiosqlite:///./data/logpulse.db`):

```bash
# 1. Activate Virtual Environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # (Windows)
# source venv/bin/activate    # (Linux/macOS)

# 2. Install Dependencies
pip install -r requirements.txt

# 3. Terminal 1: Launch FastAPI Backend
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Terminal 2: Launch Streamlit Dashboard
streamlit run src/dashboard/app.py --server.port 8501

# 5. Terminal 3: Run Traffic Simulator
python scripts/generate_traffic.py --rate 50 --duration 60 --profile mixed
```

---

## 4. Environment Variables Reference

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `production` | Deployment environment (`development`, `staging`, `production`, `testing`) |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Connection URL for PostgreSQL or SQLite fallback |
| `API_PORT` | `8000` | Port for FastAPI REST backend |
| `DASHBOARD_PORT` | `8501` | Port for Streamlit Web UI |
| `RATE_LIMIT_ENABLED` | `true` | Sliding-window IP rate limiting toggle |
| `RATE_LIMIT_PER_MINUTE` | `120` | Maximum requests permitted per IP per minute |
| `MAX_INGEST_BATCH_SIZE` | `5000` | Maximum lines permitted per ingestion batch |
| `SECURITY_HEADERS_ENABLED` | `true` | Injects HSTS, CSP, and X-Frame-Options headers |
| `DRAIN3_SIM_TH` | `0.5` | Drain3 similarity clustering threshold |
| `DRAIN3_DEPTH` | `4` | Drain3 parse tree depth |
| `DEFAULT_DETECTOR` | `ensemble` | Active model (`statistical`, `isolation_forest`, `deeplog_lstm`, `ensemble`) |
| `DEEPLOG_TOP_K` | `3` | DeepLog next-token candidate tolerance count |
| `ALERT_COOLDOWN_SECONDS` | `300` | Alert fatigue cooldown suppression window (seconds) |
| `INCIDENT_CORRELATION_WINDOW_SECONDS` | `600` | Spatio-temporal incident clustering window (seconds) |

---

## 5. Production Hardening & Operations

### Database Backups & Volume Persistence
PostgreSQL state and Drain3 online states are mounted to persistent named volumes:
```bash
# Backup PostgreSQL database
docker exec -t logpulse-postgres pg_dump -U logpulse_user logpulse_db > backup_$(date +%F).sql

# Restore PostgreSQL database
cat backup.sql | docker exec -i logpulse-postgres psql -U logpulse_user -d logpulse_db
```

### Scaling & High Availability
- **API Stateless Scaling:** `logpulse-api` is completely stateless. You can scale horizontally (`docker compose up --scale api=3`) behind an Nginx or AWS ALB round-robin load balancer.
- **Worker Concurrency:** In high-volume production, launch uvicorn with multi-worker support:
  ```bash
  uvicorn src.api.main:app --workers 4 --host 0.0.0.0 --port 8000
  ```
- **Graceful Shutdown:** The FastAPI lifespan manager safely rolls back unfinished transactions and closes connection pools upon receiving `SIGTERM` / `SIGINT`.

