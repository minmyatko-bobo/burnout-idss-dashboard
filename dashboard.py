"""
dashboard.py — Streamlit presentation layer for the Explainable Burnout IDSS.

Four pages: Executive Summary · Department Heatmap · Employee Risk Cards ·
Intervention Recommendations. Sidebar role selector enforces the same RBAC as
SEHIM. Reads data/sehim_workforce.json (regenerate with `python app/sehim_api.py`).

Run:  streamlit run app/dashboard.py
"""
import sys
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dashboard_logic as L

st.set_page_config(page_title="Burnout IDSS", page_icon="🔥", layout="wide")
RISK = L.RISK_COLORS

@st.cache_data
def _load():
    return L.load_workforce()

def gauge(value: float, level: str):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number={"valueformat": ".2f"},
        title={"text": f"CBRI — {level}"},
        gauge={"axis": {"range": [0, 1]}, "bar": {"color": RISK.get(level, "#888")},
               "steps": [{"range": [0, 0.35], "color": "#EAF6F1"},
                         {"range": [0.35, 0.60], "color": "#FBEFE3"},
                         {"range": [0.60, 1.0], "color": "#FAE8E6"}]}))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=50, b=10))
    return fig

def main():
    wf = _load()
    st.sidebar.title("🔥 Burnout IDSS")
    role = st.sidebar.radio("Role", ["HR_Admin", "HR_Manager"])
    department = None
    if role == "HR_Manager":
        department = st.sidebar.selectbox("Your department",
                                          sorted({e["department"] for e in wf}))
    emps = L.filter_by_role(wf, role, department)
    page = st.sidebar.radio("Page", ["Executive Summary", "Department Heatmap",
                                     "Employee Risk Cards", "Intervention Recommendations"])
    st.sidebar.caption(L.DISCLAIMER)

    if not emps:
        st.warning("No employees visible for this role/department.")
        return

    # ---------------- Executive Summary ----------------
    if page == "Executive Summary":
        st.title("Executive Summary")
        s = L.exec_summary(emps)
        c = st.columns(5)
        c[0].metric("Headcount", s["headcount"])
        c[1].metric("High risk", s["high"], f'{s["pct_high"]}%')
        c[2].metric("Medium risk", s["medium"])
        c[3].metric("Low risk", s["low"])
        c[4].metric("Mean CBRI", s["mean_cbri"])
        df = L.to_frame(emps)
        cc = st.columns(2)
        bar = px.bar(df["riskLevel"].value_counts().reindex(["High","Medium","Low"]).reset_index(),
                     x="riskLevel", y="count", color="riskLevel", color_discrete_map=RISK,
                     title="Risk-level distribution")
        cc[0].plotly_chart(bar, use_container_width=True)
        cc[1].markdown("#### Top at-risk employees")
        cc[1].dataframe(df.sort_values("cbri", ascending=False)
                        .head(10)[["employeeId","department","jobTitle","cbri","riskLevel"]],
                        hide_index=True, use_container_width=True)

    # ---------------- Department Heatmap ----------------
    elif page == "Department Heatmap":
        st.title("Department Risk Heatmap")
        ds = L.dept_summary(emps)
        heat = ds.set_index("department")[["high","medium","low"]]
        fig = px.imshow(heat, text_auto=True, color_continuous_scale="RdYlGn_r",
                        aspect="auto", labels=dict(color="employees"),
                        title="Employees by risk level and department")
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("#### Department roll-up (sorted by mean CBRI)")
        st.dataframe(ds, hide_index=True, use_container_width=True)
        dep = st.selectbox("Inspect a department", ds["department"])
        sub = [e for e in emps if e["department"] == dep]
        st.dataframe(L.to_frame(sub).sort_values("cbri", ascending=False)
                     [["employeeId","jobTitle","burnout","mentalHealth","attrition","cbri","riskLevel"]],
                     hide_index=True, use_container_width=True)

    # ---------------- Employee Risk Cards ----------------
    elif page == "Employee Risk Cards":
        st.title("Employee Risk Card")
        idx = {e["employeeId"]: e for e in emps}
        eid = st.selectbox("Select employee",
                           sorted(idx, key=lambda k: -idx[k]["cbri"]))
        e = idx[eid]
        left, right = st.columns([1, 1.3])
        with left:
            st.plotly_chart(gauge(e["cbri"], e["riskLevel"]), use_container_width=True)
            st.markdown(f"**{e['employeeId']}** · {e['jobTitle']} · {e['department']}")
            rs = e["riskScores"]; m = st.columns(3)
            m[0].metric("Burnout", f"{rs['burnout']:.0%}")
            m[1].metric("Mental health", f"{rs['mentalHealth']:.0%}")
            m[2].metric("Attrition", f"{rs['attrition']:.0%}")
        with right:
            st.markdown(f"### :red[{e['riskLevel']} risk]" if e["riskLevel"]=="High"
                        else f"### {e['riskLevel']} risk")
            st.markdown("**Why this employee is flagged**")
            for f in e["topFactors"]:
                st.markdown(f"- {f['factor']} ({f['direction']} risk)")
            st.info(e["explanationNarrative"])
            st.markdown("**Recommended action**")
            st.write(e["recommendedAction"])
            pdf = L.build_employee_pdf(e)
            st.download_button("⬇ Download PDF report", data=pdf,
                               file_name=f"risk_report_{eid}.pdf", mime="application/pdf")

    # ---------------- Intervention Recommendations ----------------
    else:
        st.title("Intervention Recommendations")
        st.caption("Pre-defined, non-punitive HR action sets per risk level. "
                   "Final action is always the HR professional's judgement.")
        for lvl in ["High", "Medium", "Low"]:
            n = sum(1 for e in emps if e["riskLevel"] == lvl)
            with st.expander(f"{lvl} risk — {n} employee(s)", expanded=(lvl == "High")):
                for a in L.interventions_for(lvl):
                    st.markdown(f"- {a}")
        ds = L.dept_summary(emps)
        st.markdown("#### Where to focus first (departments by mean CBRI)")
        st.dataframe(ds[["department","headcount","meanCBRI","high"]],
                     hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
