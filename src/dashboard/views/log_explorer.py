"""Log Explorer View: Interactive search, filtering, and template inspection."""

import pandas as pd
import streamlit as st

from src.dashboard.api_client import DashboardAPIClient


def render_log_explorer_view(client: DashboardAPIClient):
    """Render interactive log explorer with multi-parameter filtering."""
    st.header("Infrastructure Log Explorer")
    st.markdown("Search, filter, and inspect structured log events and Drain3 template extractions.")

    # 1. Filter Controls
    with st.expander("Filter Controls", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            service_filter = st.text_input("Service", placeholder="e.g. hadoop-hdfs")
        with f_col2:
            host_filter = st.text_input("Host", placeholder="e.g. hdfs-cluster")
        with f_col3:
            severity_filter = st.selectbox(
                "Severity",
                options=["ALL", "INFO", "WARN", "WARNING", "ERROR", "FATAL"],
                index=0,
            )
        with f_col4:
            limit_val = st.slider("Result Limit", min_value=10, max_value=500, value=50, step=10)

    # 2. Fetch Logs
    sev_param = None if severity_filter == "ALL" else severity_filter
    try:
        logs_resp = client.query_logs(
            service=service_filter if service_filter else None,
            host=host_filter if host_filter else None,
            severity=sev_param,
            limit=limit_val,
        )
    except Exception as exc:
        st.error(f"Error querying logs: {exc}")
        return

    items = logs_resp.get("items", [])
    total = logs_resp.get("total", 0)

    st.write(f"Showing **{len(items)}** of **{total}** matched log events.")

    if not items:
        st.info("No log events found matching the specified filter criteria.")
        return

    # 3. Formatted Table View
    df = pd.DataFrame(items)
    display_cols = ["timestamp", "severity", "host", "service", "template_id", "message"]
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        column_config={
            "timestamp": st.column_config.DatetimeColumn("Timestamp", format="YYYY-MM-DD HH:mm:ss"),
            "severity": st.column_config.TextColumn("Severity"),
            "message": st.column_config.TextColumn("Parsed Log Message", width="large"),
        },
    )

    # 4. Detail Inspector for Single Event
    st.subheader("Event Deep Inspector")
    selected_idx = st.selectbox(
        "Select Log Record to Inspect",
        options=range(len(items)),
        format_func=lambda i: f"[{items[i]['severity']}] {items[i]['timestamp']} - {items[i]['message'][:80]}...",
    )

    if selected_idx is not None:
        selected_log = items[selected_idx]
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            st.markdown(f"**Log ID:** `{selected_log['id']}`")
            st.markdown(f"**Template ID:** `{selected_log['template_id']}`")
            st.markdown(f"**Host / Service:** `{selected_log['host']}` / `{selected_log['service']}`")
        with d_col2:
            st.markdown(f"**Component:** `{selected_log['component']}`")
            st.markdown(f"**Extracted Parameters:** `{selected_log['parameters']}`")

        st.text_area("Raw Original Log String", selected_log["raw_log"], height=80)

    # 5. Export Button
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Filtered Logs (CSV)",
        data=csv_bytes,
        file_name="logpulse_filtered_logs.csv",
        mime="text/csv",
    )

