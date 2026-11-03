"""Traffic Simulator View: Live traffic simulation, error injection, and interactive demonstration."""

import streamlit as st

from src.dashboard.api_client import DashboardAPIClient


PRESET_BENIGN_HDFS = [
    "081109 203518 143 INFO dfs.DataNode$DataXceiver: Receiving block blk_-1608999614823707180 src: /10.250.19.102:54106 dest: /10.250.19.102:50010",
    "081109 203519 145 INFO dfs.DataNode$PacketResponder: PacketResponder 1 for block blk_-1608999614823707180 terminating",
    "081109 203519 145 INFO dfs.DataNode$DataXceiver: Received block blk_-1608999614823707180 of size 91178 from /10.250.19.102",
    "081109 203520 147 INFO dfs.DataNode$DataXceiver: Receiving block blk_7128391209384729182 src: /10.250.19.103:54108 dest: /10.250.19.103:50010",
    "081109 203521 148 INFO dfs.DataNode$PacketResponder: PacketResponder 2 for block blk_7128391209384729182 terminating",
    "081109 203521 149 INFO dfs.DataNode$DataXceiver: Received block blk_7128391209384729182 of size 67108864 from /10.250.19.103",
]

PRESET_ANOMALOUS_HDFS = [
    "081109 204001 201 INFO dfs.DataNode$DataXceiver: Receiving block blk_9988776655443322110 src: /10.250.21.11:51234 dest: /10.250.21.11:50010",
    "081109 204002 205 ERROR dfs.DataNode$DataXceiver: Verification failed for block blk_9988776655443322110 checksum mismatch on replica 1",
    "081109 204003 210 ERROR dfs.DataNode$DataXceiver: Block blk_9988776655443322110 is corrupted. Exceeded max block read retries.",
    "081109 204004 212 WARN dfs.DataNode$BlockScanner: Corrupted block blk_9988776655443322110 moved to bad_blocks quarantine.",
]

PRESET_BGL_PANIC = [
    "- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO generating core.1245",
    "- 1117838571 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.51.102384 R02-M1-N0-C:J12-U11 RAS KERNEL FATAL data storage interrupt",
    "- 1117838572 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.52.482019 R02-M1-N0-C:J12-U11 RAS KERNEL FATAL machine check interrupt: L2 cache parity error",
    "- 1117838573 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.53.882910 R02-M1-N0-C:J12-U11 RAS HARDWARE ERROR card unresponsive",
]


def render_traffic_simulator_view(client: DashboardAPIClient):
    """Render interactive traffic generator for pipeline demonstration and live testing."""
    st.header("Real-Time Traffic Simulator & Log Injector")
    st.markdown("Inject realistic log patterns directly into the live ingestion and anomaly detection pipeline.")

    preset_choice = st.radio(
        "Choose Workload Simulation Scenario",
        options=[
            "1. Benign Normal HDFS File Replication (6 events)",
            "2. Cascading HDFS Data Corruption & Verification Failure (4 events)",
            "3. BGL Supercomputer Kernel Panic & Hardware Crash (4 events)",
            "4. Custom Raw Log Lines Input",
        ],
        index=0,
    )

    if "Benign" in preset_choice:
        chosen_lines = PRESET_BENIGN_HDFS
        src_tag = "hdfs_benign_simulation"
    elif "Corruption" in preset_choice:
        chosen_lines = PRESET_ANOMALOUS_HDFS
        src_tag = "hdfs_corruption_incident"
    elif "Kernel" in preset_choice:
        chosen_lines = PRESET_BGL_PANIC
        src_tag = "bgl_kernel_panic"
    else:
        src_tag = "custom_user_stream"
        raw_text = st.text_area(
            "Enter Raw Log Lines (one per line):",
            value="081109 203518 143 INFO dfs.DataNode$DataXceiver: Test log event from interactive dashboard",
            height=120,
        )
        chosen_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    st.subheader("Payload Preview")
    st.code("\n".join(chosen_lines), language="text")

    if st.button("🚀 Stream Payload to Pipeline", type="primary", use_container_width=True):
        if not chosen_lines:
            st.warning("No log lines to inject.")
            return

        with st.spinner("Processing through Drain3 -> Feature Pipeline -> ML Ensemble -> Alert Manager..."):
            try:
                res = client.ingest_stream(chosen_lines, source_id=src_tag)
                st.success("Batch successfully ingested and evaluated!")

                r1, r2, r3, r4 = st.columns(4)
                with r1:
                    st.metric("Total Logs", res.get("total_records", 0))
                with r2:
                    st.metric("Valid Ingested", res.get("valid_records", 0))
                with r3:
                    st.metric("Processing Time", f"{res.get('duration_ms', 0):.2f} ms")
                with r4:
                    st.metric("Throughput", f"{res.get('throughput_eps', 0):,.0f} EPS")

            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")

