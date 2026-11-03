"""LogPulse AnomalyGuard: Real-Time Intelligent Log Anomaly Monitoring Dashboard."""

import streamlit as st

from config.settings import settings
from src.dashboard.api_client import DashboardAPIClient
from src.dashboard.views import (
    render_anomaly_inspector_view,
    render_log_explorer_view,
    render_model_benchmarks_view,
    render_overview_view,
    render_traffic_simulator_view,
    render_triage_board_view,
)

# 1. Page Configuration
st.set_page_config(
    page_title=f"{settings.APP_NAME} | Incident Monitoring",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Modern UI Styles
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #1E293B;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        border: 1px solid #334155;
    }
    .badge-critical { background-color: #DC2626; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
    .badge-high { background-color: #EA580C; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
    .badge-medium { background-color: #D97706; color: white; padding: 2px 8px; border-radius: 4px; }
    .badge-info { background-color: #2563EB; color: white; padding: 2px 8px; border-radius: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def main():
    """Main dashboard entrypoint."""
    # Initialize API Client singleton in session state
    if "api_client" not in st.session_state:
        st.session_state.api_client = DashboardAPIClient()
    client: DashboardAPIClient = st.session_state.api_client

    # 3. Sidebar Navigation & Branding
    st.sidebar.title("🛡️ LogPulse AnomalyGuard")
    st.sidebar.caption(f"Intelligent Incident Platform v{settings.APP_VERSION}")

    # Connectivity Check
    try:
        health = client.get_health()
        st.sidebar.success(f"● Connected ({health.get('status', 'UP')})")
    except Exception:
        st.sidebar.warning("○ Standalone App Mode")

    st.sidebar.divider()

    nav_selection = st.sidebar.radio(
        "Navigation",
        options=[
            "📊 System Overview",
            "🔍 Log Explorer",
            "🚨 Anomaly Deep Dive",
            "🛡️ Alert & Incident Triage",
            "🧠 Model Registry & Benchmarks",
            "⚡ Traffic Simulator",
        ],
        index=0,
    )

    st.sidebar.divider()
    st.sidebar.markdown(
        """
        **System Specs:**
        - **Pipeline:** Drain3 + Dynamic Regex
        - **Model:** Hybrid Ensemble (IF + DeepLog)
        - **DB Engine:** Async SQLAlchemy 2.0
        - **API:** FastAPI REST & Prometheus
        """
    )

    # 4. View Router
    if nav_selection == "📊 System Overview":
        render_overview_view(client)
    elif nav_selection == "🔍 Log Explorer":
        render_log_explorer_view(client)
    elif nav_selection == "🚨 Anomaly Deep Dive":
        render_anomaly_inspector_view(client)
    elif nav_selection == "🛡️ Alert & Incident Triage":
        render_triage_board_view(client)
    elif nav_selection == "🧠 Model Registry & Benchmarks":
        render_model_benchmarks_view(client)
    elif nav_selection == "⚡ Traffic Simulator":
        render_traffic_simulator_view(client)


if __name__ == "__main__":
    main()

