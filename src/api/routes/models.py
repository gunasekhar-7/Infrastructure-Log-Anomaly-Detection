"""Model Registry and Benchmark Telemetry API Endpoints."""

from fastapi import APIRouter

from src.api.schemas import BenchmarkMetricItem, ModelBenchmarkResponse, ModelInfoResponse

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("", response_model=list[ModelInfoResponse])
async def list_models() -> list[ModelInfoResponse]:
    """List all registered anomaly detection models and their operational status."""
    return [
        ModelInfoResponse(
            name="Modified Z-Score (MAD)",
            algorithm="ModifiedZScoreDetector",
            category="STATISTICAL",
            status="READY",
            is_active=True,
            description="Statistical baseline using Median Absolute Deviation for error count surges.",
            parameters={"threshold": 3.5, "metric": "error_count"},
        ),
        ModelInfoResponse(
            name="Isolation Forest",
            algorithm="IsolationForestDetector",
            category="UNSUPERVISED_TABULAR",
            status="READY",
            is_active=True,
            description="Multivariate isolation tree ensemble on extracted frequency & entropy profiles.",
            parameters={"n_estimators": 100, "contamination": 0.05, "random_state": 42},
        ),
        ModelInfoResponse(
            name="DeepLog Sequential LSTM",
            algorithm="DeepLogLSTM",
            category="DEEP_LEARNING_SEQUENTIAL",
            status="READY",
            is_active=True,
            description="PyTorch LSTM modeling execution order and next-template probability distribution.",
            parameters={"embedding_dim": 32, "hidden_dim": 64, "num_layers": 2, "top_k": 3},
        ),
        ModelInfoResponse(
            name="LSTM Autoencoder",
            algorithm="LSTMAutoencoder",
            category="DEEP_LEARNING_RECONSTRUCTION",
            status="READY",
            is_active=False,
            description="Sequence reconstruction autoencoder detecting abnormal template trajectories.",
            parameters={"hidden_dim": 64, "latent_dim": 32},
        ),
        ModelInfoResponse(
            name="Hybrid Ensemble",
            algorithm="HybridEnsembleDetector",
            category="HYBRID_ENSEMBLE",
            status="ACTIVE",
            is_active=True,
            description="Unified ensemble combining Tabular Isolation Forest with Sequential DeepLog LSTM.",
            parameters={"tabular_weight": 0.4, "sequential_weight": 0.6, "ensemble_threshold": 0.65},
        ),
    ]


@router.get("/benchmark", response_model=ModelBenchmarkResponse)
async def get_model_benchmarks() -> ModelBenchmarkResponse:
    """Retrieve evaluated benchmark performance metrics across models on HDFS Loghub."""
    return ModelBenchmarkResponse(
        dataset="HDFS Loghub Benchmark (2,000 blocks)",
        split_info="Train: 1,540 blocks, Val: 226 blocks, Test: 228 blocks (Zero Leakage)",
        metrics=[
            BenchmarkMetricItem(
                model_name="Modified Z-Score (MAD)",
                algorithm="Statistical Outlier",
                threshold=1.0000,
                precision=0.1491,
                recall=1.0000,
                f1_score=0.2595,
                roc_auc=0.5000,
                training_time_sec=0.0036,
                inference_latency_ms=0.108,
            ),
            BenchmarkMetricItem(
                model_name="Isolation Forest",
                algorithm="Multivariate Trees",
                threshold=0.3342,
                precision=0.1510,
                recall=0.8529,
                f1_score=0.2566,
                roc_auc=0.5414,
                training_time_sec=0.2740,
                inference_latency_ms=0.405,
            ),
            BenchmarkMetricItem(
                model_name="LSTM Autoencoder",
                algorithm="Sequence Reconstruction",
                threshold=0.6587,
                precision=0.1491,
                recall=1.0000,
                f1_score=0.2595,
                roc_auc=0.5147,
                training_time_sec=14.1696,
                inference_latency_ms=0.215,
            ),
            BenchmarkMetricItem(
                model_name="DeepLog Sequential LSTM",
                algorithm="Next-Token Prediction",
                threshold=0.7423,
                precision=0.1452,
                recall=0.5294,
                f1_score=0.2278,
                roc_auc=0.4995,
                training_time_sec=11.0878,
                inference_latency_ms=0.519,
            ),
        ],
    )

