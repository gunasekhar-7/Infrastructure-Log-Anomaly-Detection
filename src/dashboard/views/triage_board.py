"""Alert & Incident Triage Board: Interactive operations, status actions, and incident clustering."""

import pandas as pd
import streamlit as st

from src.dashboard.api_client import DashboardAPIClient


def render_triage_board_view(client: DashboardAPIClient):
    """Render operational alert triage and incident correlation control center."""
    st.header("Alert Management & Incident Triage Board")
    st.markdown("Perform on-call triage, alert acknowledgement, cooldown suppression inspection, and incident resolution.")

    tab_alerts, tab_incidents = st.tabs(["🚨 Operational Alerts", "🛡️ Correlated Incidents"])

    # =========================================================================
    # TAB 1: OPERATIONAL ALERTS
    # =========================================================================
    with tab_alerts:
        a_col1, a_col2 = st.columns([1, 3])
        with a_col1:
            status_filter = st.selectbox(
                "Filter Alert Status",
                options=["ALL", "NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"],
                index=0,
            )
        status_param = None if status_filter == "ALL" else status_filter

        try:
            alerts_data = client.query_alerts(status=status_param, limit=100)
            alerts = alerts_data.get("items", [])
        except Exception as exc:
            st.error(f"Failed to fetch alerts: {exc}")
            alerts = []

        if not alerts:
            st.info("No alerts match the chosen criteria.")
        else:
            df_alerts = pd.DataFrame(alerts)
            st.dataframe(
                df_alerts[[
                    "alert_id",
                    "severity",
                    "status",
                    "host",
                    "service",
                    "title",
                    "repeat_count",
                    "triggered_at",
                ]],
                use_container_width=True,
            )

            st.divider()
            st.subheader("Execute Alert Action")

            act_col1, act_col2, act_col3 = st.columns([2, 1, 1])
            with act_col1:
                selected_alert_id = st.selectbox(
                    "Target Alert",
                    options=[a["alert_id"] for a in alerts],
                    format_func=lambda aid: f"{aid} - {[a['title'] for a in alerts if a['alert_id'] == aid][0]}",
                )
                actor_name = st.text_input("Operator Name / ID", value="oncall_sre")
                action_note = st.text_input("Operational Note / Reason", placeholder="e.g. Restarted flaky node")

            with act_col2:
                st.write("")
                st.write("")
                if st.button("Acknowledge", use_container_width=True):
                    try:
                        client.post_alert_action(selected_alert_id, "ACKNOWLEDGE", actor_name, action_note)
                        st.success(f"Alert {selected_alert_id[:8]} acknowledged.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Action failed: {e}")

                if st.button("Investigate", use_container_width=True):
                    try:
                        client.post_alert_action(selected_alert_id, "INVESTIGATE", actor_name, action_note)
                        st.success(f"Alert {selected_alert_id[:8]} marked under investigation.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Action failed: {e}")

            with act_col3:
                st.write("")
                st.write("")
                if st.button("Resolve", use_container_width=True):
                    try:
                        client.post_alert_action(selected_alert_id, "RESOLVE", actor_name, action_note)
                        st.success(f"Alert {selected_alert_id[:8]} resolved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Action failed: {e}")

                if st.button("False Positive", use_container_width=True):
                    try:
                        client.post_alert_action(selected_alert_id, "FALSE_POSITIVE", actor_name, action_note)
                        st.warning(f"Alert {selected_alert_id[:8]} classified as false positive.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Action failed: {e}")

    # =========================================================================
    # TAB 2: CORRELATED INCIDENTS
    # =========================================================================
    with tab_incidents:
        try:
            incidents_data = client.query_incidents(limit=50)
            incidents = incidents_data.get("items", [])
        except Exception as exc:
            st.error(f"Failed to fetch incidents: {exc}")
            incidents = []

        if not incidents:
            st.info("No active or historical incidents recorded.")
        else:
            df_inc = pd.DataFrame(incidents)
            st.dataframe(
                df_inc[[
                    "incident_id",
                    "severity",
                    "status",
                    "primary_service",
                    "affected_hosts",
                    "alert_count",
                    "started_at",
                    "summary",
                ]],
                use_container_width=True,
            )

            st.divider()
            st.subheader("Manage Incident Status")
            i_col1, i_col2 = st.columns([2, 1])

            with i_col1:
                target_inc_id = st.selectbox(
                    "Select Incident",
                    options=[inc["incident_id"] for inc in incidents],
                    format_func=lambda iid: f"{iid} - {[inc['title'] for inc in incidents if inc['incident_id'] == iid][0]}",
                )
                inc_actor = st.text_input("Incident Commander", value="incident_lead")
                inc_summary = st.text_area("Resolution Summary Findings", placeholder="Identified corrupted disk block and triggered re-replication.")

            with i_col2:
                st.write("")
                st.write("")
                if st.button("Mitigate Incident", use_container_width=True):
                    try:
                        client.post_incident_action(target_inc_id, "MITIGATE", inc_actor, inc_summary)
                        st.success(f"Incident {target_inc_id[:8]} marked MITIGATED.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update incident: {e}")

                if st.button("Resolve Incident", use_container_width=True):
                    try:
                        client.post_incident_action(target_inc_id, "RESOLVE", inc_actor, inc_summary)
                        st.success(f"Incident {target_inc_id[:8]} marked RESOLVED.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to resolve incident: {e}")

