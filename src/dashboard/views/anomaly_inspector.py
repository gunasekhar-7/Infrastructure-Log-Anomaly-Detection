"""Anomaly Inspector View: Granular inspection, score breakdown, and factual evidence."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.api_client import DashboardAPIClient


def render_anomaly_inspector_view(client: DashboardAPIClient):
    """Render comprehensive anomaly investigation workspace."""
    st.header("Operational Anomaly Deep Dive")
    st.markdown("Inspect algorithmic anomaly detections, confidence scores, and factual supporting evidence.")

    # 1. Fetch Anomalies
    sev_filter = st.selectbox(
        "Filter by Severity",
        options=["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
        index=0,
    )
    sev_param = None if sev_filter == "ALL" else sev_filter

    try:
        resp = client.query_anomalies(severity=sev_param, limit=100)
    except Exception as exc:
        st.error(f"Failed to fetch anomalies: {exc}")
        return

    items = resp.get("items", [])
    if not items:
        st.info("No anomalies recorded matching this filter.")
        return

    # 2. Select Anomaly
    st.subheader(f"Flagged Anomalies ({len(items)} found)")
    selected_idx = st.selectbox(
        "Choose Anomaly for Investigation",
        options=range(len(items)),
        format_func=lambda i: f"[{items[i]['severity']}] (Score: {items[i]['anomaly_score']:.2f}) {items[i]['service']} - {items[i]['explanation'][:90]}...",
    )

    chosen_summary = items[selected_idx]
    anomaly_id = chosen_summary["id"]

    # 3. Retrieve Full Detail with Supporting Evidence
    try:
        detail = client.get_anomaly_detail(anomaly_id)
    except Exception as exc:
        st.error(f"Failed to fetch detail for anomaly '{anomaly_id}': {exc}")
        return

    st.divider()

    # 4. Score Gauge and Metadata
    col_gauge, col_meta = st.columns([1, 2])

    with col_gauge:
        score_val = detail["anomaly_score"]
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=score_val,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": f"Anomaly Risk Score ({detail['severity']})"},
                gauge={
                    "axis": {"range": [0, 1]},
                    "bar": {"color": "#DC2626" if score_val > 0.7 else "#F59E0B"},
                    "steps": [
                        {"range": [0, 0.4], "color": "#E5E7EB"},
                        {"range": [0.4, 0.7], "color": "#FED7AA"},
                        {"range": [0.7, 1.0], "color": "#FECACA"},
                    ],
                    "threshold": {
                        "line": {"color": "black", "width": 4},
                        "thickness": 0.75,
                        "value": 0.65,
                    },
                },
            )
        )
        fig.update_layout(height=260, margin=dict(t=30, b=10, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_meta:
        st.markdown(f"### Anomaly ID: `{detail['id']}`")
        m_c1, m_c2 = st.columns(2)
        with m_c1:
            st.markdown(f"**Target Host:** `{detail['host']}`")
            st.markdown(f"**Target Service:** `{detail['service']}`")
            st.markdown(f"**Detection Category:** `{detail['category']}`")
        with m_c2:
            st.markdown(f"**Detector Algorithm:** `{detail['algorithm']}`")
            st.markdown(f"**Timestamp:** `{detail['timestamp']}`")
            st.markdown(f"**Investigation Status:** `{detail['investigation_status']}`")

        st.info(f"**Factual Explanation:** {detail['explanation']}")

    # 5. Supporting Evidence Inspector
    st.subheader("Supporting Log Evidence Isolation")
    st.markdown("Chronological sequence of log events that caused or accompanied this anomaly:")

    evidence = detail.get("supporting_evidence", [])
    if evidence:
        df_ev = pd.DataFrame(evidence)
        # Highlight trigger events
        df_ev["is_trigger_str"] = df_ev["is_trigger"].apply(lambda t: "TRIGGER" if t else "Context")
        display_ev = df_ev[["timestamp", "severity", "is_trigger_str", "template_id", "raw_message", "reason"]]
        st.dataframe(
            display_ev,
            use_container_width=True,
            column_config={
                "is_trigger_str": st.column_config.TextColumn("Role"),
                "raw_message": st.column_config.TextColumn("Raw Log Line", width="large"),
                "reason": st.column_config.TextColumn("Evidence Justification"),
            },
        )
    else:
        st.write("No individual log evidence records attached to this anomaly.")

