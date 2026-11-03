"""Model Registry & Benchmarks View: Comparison matrices, metrics, and latency trade-offs."""

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.api_client import DashboardAPIClient


def render_model_benchmarks_view(client: DashboardAPIClient):
    """Render machine learning model registry and empirical benchmark analytics."""
    st.header("Anomaly Detection Model Registry & Benchmarks")
    st.markdown("Inspect registered statistical, unsupervised tree, and deep sequential neural models with empirical benchmark evaluations.")

    # 1. Fetch Model Metadata & Benchmarks
    try:
        models = client.get_models()
        benchmarks = client.get_benchmarks()
    except Exception as exc:
        st.error(f"Failed to fetch model registry: {exc}")
        return

    tab_bench, tab_registry = st.tabs(["📊 Benchmark Comparison", "🧠 Model Architecture Catalog"])

    # =========================================================================
    # TAB 1: EMPIRICAL BENCHMARKS
    # =========================================================================
    with tab_bench:
        st.markdown(f"**Benchmark Dataset:** `{benchmarks.get('dataset', 'HDFS')}`")
        st.caption(f"Validation Strategy: {benchmarks.get('split_info', 'Zero-leakage split')}")

        metrics = benchmarks.get("metrics", [])
        if metrics:
            df_m = pd.DataFrame(metrics)

            # 1. Comparison Table
            st.dataframe(
                df_m[[
                    "model_name",
                    "algorithm",
                    "precision",
                    "recall",
                    "f1_score",
                    "roc_auc",
                    "inference_latency_ms",
                    "training_time_sec",
                ]],
                use_container_width=True,
                column_config={
                    "precision": st.column_config.NumberColumn("Precision", format="%.3f"),
                    "recall": st.column_config.NumberColumn("Recall", format="%.3f"),
                    "f1_score": st.column_config.NumberColumn("F1 Score", format="%.3f"),
                    "roc_auc": st.column_config.NumberColumn("ROC-AUC", format="%.3f"),
                    "inference_latency_ms": st.column_config.NumberColumn("Latency (ms)", format="%.2f ms"),
                    "training_time_sec": st.column_config.NumberColumn("Train (s)", format="%.2f s"),
                },
            )

            # 2. Charts
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                fig_f1 = px.bar(
                    df_m,
                    x="model_name",
                    y=["precision", "recall", "f1_score"],
                    barmode="group",
                    title="Detection Accuracy Metrics Comparison",
                    labels={"value": "Score (0-1)", "model_name": "Model", "variable": "Metric"},
                    color_discrete_sequence=["#3B82F6", "#10B981", "#8B5CF6"],
                )
                fig_f1.update_layout(height=320, margin=dict(t=30, b=10, l=10, r=10))
                st.plotly_chart(fig_f1, use_container_width=True)

            with b_col2:
                fig_lat = px.bar(
                    df_m,
                    x="model_name",
                    y="inference_latency_ms",
                    title="Per-Sample Inference Latency (ms)",
                    labels={"inference_latency_ms": "Latency (ms)", "model_name": "Model"},
                    color="inference_latency_ms",
                    color_continuous_scale="Viridis",
                )
                fig_lat.update_layout(height=320, margin=dict(t=30, b=10, l=10, r=10))
                st.plotly_chart(fig_lat, use_container_width=True)

        st.info(
            "**Operational Trade-Off Rationale:**\n"
            "- **Volumetric Detectors (Modified Z-Score & Isolation Forest):** High recall for error bursts and capacity spikes, but trigger false positives on legitimate bulk transfers.\n"
            "- **DeepLog Sequential LSTM:** Captures broken execution order P(e_t | e_{t-1}, ...), detecting subtle state corruption that volume-based detectors miss.\n"
            "- **Hybrid Ensemble:** Weighted combination dynamically balances volumetric sensitivity with sequential fidelity."
        )

    # =========================================================================
    # TAB 2: MODEL CATALOG
    # =========================================================================
    with tab_registry:
        for m in models:
            with st.container():
                st.markdown(f"### {m['name']} `{m['algorithm']}`")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Category:** `{m['category']}`")
                with c2:
                    st.markdown(f"**Status:** `{m['status']}` ({'ACTIVE' if m['is_active'] else 'STANDBY'})")
                with c3:
                    st.markdown(f"**Hyperparameters:** `{m['parameters']}`")
                st.markdown(f"*{m['description']}*")
                st.divider()

