"""Overview Dashboard View: High-level KPI metrics, operational status, and telemetry."""

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dashboard.api_client import DashboardAPIClient


def render_overview_view(client: DashboardAPIClient):
    """Render executive KPI cards and real-time operational status."""
    st.header("Platform System Overview")
    st.markdown("High-level operational health, ingestion throughput, and threat indicators.")

    # 1. Fetch current telemetry
    try:
        health = client.get_health()
        logs_data = client.query_logs(limit=100)
        anomalies_data = client.query_anomalies(limit=100)
        alerts_data = client.query_alerts(limit=100)
        incidents_data = client.query_incidents(limit=100)
    except Exception as exc:
        st.error(f"Failed to communicate with API service: {exc}")
        return

    # 2. Metric KPI Cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric(
            label="Total Logs Ingested",
            value=f"{logs_data.get('total', 0):,}",
            delta="Stored in DB",
        )
    with col2:
        st.metric(
            label="Anomalies Flagged",
            value=f"{anomalies_data.get('total', 0):,}",
            delta="Risk Evaluated",
            delta_color="inverse",
        )
    with col3:
        st.metric(
            label="Active Alerts",
            value=f"{alerts_data.get('total', 0):,}",
            delta="Deduplicated",
            delta_color="inverse",
        )
    with col4:
        st.metric(
            label="Correlated Incidents",
            value=f"{incidents_data.get('total', 0):,}",
            delta="Clustered",
            delta_color="inverse",
        )
    with col5:
        db_stat = health.get("database", "UNKNOWN")
        st.metric(
            label="System Health",
            value=health.get("status", "UNKNOWN"),
            delta=f"DB: {db_stat.split(':')[0]}",
        )

    st.divider()

    # 3. Visual Charts (Severity Breakdown and Service Activity)
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Log Volume by Severity")
        logs = logs_data.get("items", [])
        if logs:
            df_logs = pd.DataFrame(logs)
            sev_counts = df_logs["severity"].value_counts().reset_index()
            sev_counts.columns = ["Severity", "Count"]

            color_map = {
                "INFO": "#2563EB",
                "WARN": "#F59E0B",
                "WARNING": "#F59E0B",
                "ERROR": "#DC2626",
                "FATAL": "#991B1B",
            }
            fig_sev = px.pie(
                sev_counts,
                values="Count",
                names="Severity",
                hole=0.45,
                color="Severity",
                color_discrete_map=color_map,
            )
            fig_sev.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig_sev, use_container_width=True)
        else:
            st.info("No log events recorded yet. Ingest logs to generate charts.")

    with col_right:
        st.subheader("Anomalies by Service & Severity")
        anomalies = anomalies_data.get("items", [])
        if anomalies:
            df_anom = pd.DataFrame(anomalies)
            fig_bar = px.bar(
                df_anom,
                x="service",
                color="severity",
                title="Risk Distribution Across Services",
                color_discrete_map={
                    "INFO": "#3B82F6",
                    "LOW": "#10B981",
                    "MEDIUM": "#F59E0B",
                    "HIGH": "#EF4444",
                    "CRITICAL": "#7F1D1D",
                },
                barmode="stack",
            )
            fig_bar.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No anomalies detected in the current inspection window.")

    # 4. Recent Active Incidents Table
    st.subheader("Active Incidents Overview")
    incidents = incidents_data.get("items", [])
    if incidents:
        df_inc = pd.DataFrame(incidents)[
            ["incident_id", "severity", "status", "primary_service", "alert_count", "summary"]
        ]
        st.dataframe(df_inc, use_container_width=True)
    else:
        st.success("All systems nominal — No active correlated incidents.")

