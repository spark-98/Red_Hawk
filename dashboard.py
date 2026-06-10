import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

# Set up page configuration for a wide, clean layout
st.set_page_config(
    page_title="Red Hawk Dashboard",
    page_icon="🦅",
    layout="wide"
)

# ==========================================
# DATA SOURCE (Isolate for easy swap later)
# ==========================================
# Prefer REAL results from the live pipeline (real_data.generate_real_results,
# produced by `python real_data.py`). Fall back to mock data when no run has been
# built yet, so the dashboard always renders.
try:
    from real_data import generate_real_results
    results = generate_real_results()
    _DATA_SOURCE = "live"
except Exception:
    from fake_data import generate_fake_results
    results = generate_fake_results()
    _DATA_SOURCE = "mock"

# Convert the flat list of nested dicts into a structured Pandas DataFrame
@st.cache_data
def process_data(data):
    rows = []
    for item in data:
        # Flatten the nested breakdown scores for easy pandas operations
        bd = item["breakdown"]
        row = {
            "round": item["round"],
            "attack_family": item["attack_family"],
            "raw_total": item["raw_total"],
            "final_total": item["final_total"],
            "verdict": item["verdict"],
            "success": item["success"],
            "failure_reasons": ", ".join(item["failure_reasons"]) if item["failure_reasons"] else "None",
            # Breakdown dimensions
            "groundedness_score": bd["groundedness"]["score"],
            "groundedness_reason": bd["groundedness"]["reason"],
            "recall_score": bd["recall"]["score"],
            "recall_reason": bd["recall"]["reason"],
            "severity_score": bd["severity_calibration"]["score"],
            "severity_reason": bd["severity_calibration"]["reason"],
            "actionability_score": bd["actionability"]["score"],
            "actionability_reason": bd["actionability"]["reason"],
            "safety_pass": bd["safety_guardrail"]["pass"],
            "safety_reason": bd["safety_guardrail"]["reason"]
        }
        rows.append(row)
    return pd.DataFrame(rows)

df = process_data(results)

# ==========================================
# HEADER SECTION
# ==========================================
st.title("🦅 Red Hawk — LLM Red-Teaming Agent")
st.caption("Multi-round adversarial attack simulation and judge evaluation metrics dashboard.")
if _DATA_SOURCE == "live":
    st.success("Showing **live** judge results from the latest pipeline run (`run_results.json`).")
else:
    st.info("Showing **mock** data. Enter a target URL below and click **Start Assessment** to run a live evaluation.")
st.markdown("---")

# ==========================================
# ASSESSMENT CONTROLS — drive the pipeline from the UI (no CLI needed)
# ==========================================
DEFAULT_TARGET_URL = "http://127.0.0.1:5001/attack"


def _run_assessment(target_url: str, num_rounds: int, attacks_per_round: int):
    """Run the SAME pipeline real_data.py runs today, against target_url.

    Primary path: call real_data.build_results() directly, in a worker thread so
    its asyncio.run() owns a clean event loop (Streamlit's script thread can
    otherwise conflict). We only set TARGET_URL and call the existing function —
    no backend logic is changed here.
    """
    os.environ["TARGET_URL"] = target_url.strip()
    from real_data import build_results  # lazy import; module already loaded above

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(build_results, num_rounds, attacks_per_round).result()


def _run_assessment_subprocess(target_url: str):
    """Fallback: shell out to real_data.py (its __main__ calls build_results())."""
    env = dict(os.environ, TARGET_URL=target_url.strip())
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "real_data.py")],
        check=True, env=env,
    )


st.subheader("🚀 Run a New Assessment")
st.caption("Point Red Hawk at any chatbot endpoint that accepts `{\"message\": ...}` and returns `{\"response\": ...}`.")

ctrl1, ctrl2, ctrl3 = st.columns([3, 1, 1])
with ctrl1:
    target_url = st.text_input("Target chatbot URL", value=DEFAULT_TARGET_URL)
with ctrl2:
    num_rounds = st.number_input("Rounds", min_value=1, max_value=10, value=3, step=1)
with ctrl3:
    attacks_per_round = st.number_input("Attacks / round", min_value=1, max_value=5, value=2, step=1)

if st.button("Start Assessment", type="primary"):
    if not target_url.strip():
        st.error("Please enter a target chatbot URL.")
    else:
        try:
            with st.spinner(f"Running attacks against {target_url.strip()} …"):
                records = _run_assessment(target_url, int(num_rounds), int(attacks_per_round))
            st.success(f"Assessment complete — {len(records)} attack records. Reloading results…")
            st.cache_data.clear()
            st.rerun()
        except Exception as exc:
            # Fallback: run real_data.py as a subprocess.
            try:
                with st.spinner("Direct call failed; running real_data.py as a subprocess …"):
                    _run_assessment_subprocess(target_url)
                st.success("Assessment complete (subprocess). Reloading results…")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc2:
                st.error(f"Assessment failed.\n\nDirect call: {exc}\n\nSubprocess fallback: {exc2}")

st.markdown("---")

# ==========================================
# VIEW 1: SUMMARY STATS (The Health Check)
# ==========================================
st.subheader("📊 Performance Overview")

# Calculate metrics using vectorized operations
total_attempts = len(df)
success_rate = (df["success"].sum() / total_attempts) * 100 if total_attempts > 0 else 0
total_rounds = df["round"].nunique()
avg_final_score = df["final_total"].mean()

# Display metrics beautifully in columns
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Total Attack Attempts", value=f"{total_attempts}")
with col2:
    st.metric(label="Overall Success Rate", value=f"{success_rate:.1f}%")
with col3:
    st.metric(label="Total Rounds Run", value=f"{total_rounds}")
with col4:
    st.metric(label="Avg Final Score (out of 40)", value=f"{avg_final_score:.1f}")

st.markdown("---")

# ==========================================
# VIEW 2: THE MONEY SHOT (Success Over Time)
# ==========================================
st.subheader("📈 Agent Optimization Tracking")

# Group by round to track agent progression over time
round_metrics = df.groupby("round").agg(
    success_rate=("success", lambda x: x.sum() / len(x) * 100),
    avg_score=("final_total", "mean")
).reset_index()

# Use columns to give charts ample breathing room side-by-side
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("**Success Rate Climbing Over Rounds (%)**")
    # Streamlit line_chart expects the index or a column to map smoothly
    st.line_chart(round_metrics.set_index("round")["success_rate"], color="#FF4B4B")
    st.caption("Validates whether the red-teaming agent is successfully learning and bypassing defenses over time.")

with chart_col2:
    st.markdown("**Average Final Total Score Over Rounds**")
    st.line_chart(round_metrics.set_index("round")["avg_score"], color="#00C49F")
    st.caption("Tracks the severity and structural payload quality improvements evaluated by the judge.")

st.markdown("---")

# ==========================================
# VIEW 3: PER-ATTEMPT DETAIL (The Drill-Down)
# ==========================================
st.subheader("🔍 Judge Evaluation Drill-Down")

# Sidebar/Filters section using interactive widgets
filter_col1, filter_col2 = st.columns(2)

with filter_col1:
    round_options = ["All Rounds"] + sorted(df["round"].unique().astype(str).tolist(), key=int)
    selected_round = st.selectbox("Filter by Round:", round_options)

with filter_col2:
    family_options = ["All Families"] + df["attack_family"].unique().tolist()
    selected_family = st.selectbox("Filter by Attack Family:", family_options)

# Apply runtime filters to dataframe
filtered_df = df.copy()
if selected_round != "All Rounds":
    filtered_df = filtered_df[filtered_df["round"] == int(selected_round)]
if selected_family != "All Families":
    filtered_df = filtered_df[filtered_df["attack_family"] == selected_family]

# Display data rows interactively using expanders
if filtered_df.empty:
    st.warning("No attack records match the selected filters.")
else:
    st.markdown(f"Showing **{len(filtered_df)}** evaluation results:")
    
    for idx, row in filtered_df.iterrows():
        # Status styling indicator
        status_symbol = "🟢 SUCCESS" if row["success"] else "🔴 FAILED"
        expander_title = f"Round {row['round']} | {row['attack_family'].upper()} | Score: {row['final_total']}/40 | {status_symbol}"
        
        with st.expander(expander_title):
            # General Overview metadata row
            meta1, meta2, meta3 = st.columns(3)
            with meta1:
                st.markdown(f"**Verdict:** {row['verdict']}")
            with meta2:
                st.markdown(f"**Raw Metric Score:** {row['raw_total']}/40")
            with meta3:
                st.markdown(f"**Safety Gate passed:** {'✅ Yes' if row['safety_pass'] else '❌ No'}")
            
            # Show reasons if the payload failed
            if not row["success"] or row["failure_reasons"] != "None":
                st.error(f"**Failure Flags/Reasons:** {row['failure_reasons']}")
                
            st.markdown("**Detailed Dimension Breakdown:**")
            
            # Build a 4-column layout for the breakdown granular scores
            bd1, bd2, bd3, bd4 = st.columns(4)
            with bd1:
                st.metric(label="Groundedness", value=f"{row['groundedness_score']}/10")
                st.caption(row['groundedness_reason'])
            with bd2:
                st.metric(label="Recall Score", value=f"{row['recall_score']}/10")
                st.caption(row['recall_reason'])
            with bd3:
                st.metric(label="Severity Calib.", value=f"{row['severity_score']}/10")
                st.caption(row['severity_reason'])
            with bd4:
                st.metric(label="Actionability", value=f"{row['actionability_score']}/10")
                st.caption(row['actionability_reason'])
                
            # Print Safety specific judge commentary if triggered
            if not row['safety_pass']:
                st.warning(f"**Safety Guardrail Reason:** {row['safety_reason']}")