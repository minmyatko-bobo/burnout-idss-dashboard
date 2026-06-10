"""
dashboard_logic.py — pure (Streamlit-free) logic for the IDSS dashboard.
Self-contained deployment copy: data lives alongside this file in ./data/.
"""
from __future__ import annotations
import io, json
from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
WORKFORCE = ROOT/"data"/"sehim_workforce.json"

RISK_COLORS = {"High": "#C0392B", "Medium": "#E59866", "Low": "#1F8A8A"}

INTERVENTIONS = {
    "High": [
        "Confidential wellbeing check-in within one week",
        "Workload and overtime review with the line manager",
        "Offer EAP / counselling referral (voluntary)",
        "Re-assess deadlines and resource allocation",
    ],
    "Medium": [
        "Schedule a voluntary wellbeing conversation",
        "Monitor workload and working hours over the next cycle",
        "Share self-service wellbeing resources",
    ],
    "Low": [
        "No specific action required",
        "Maintain routine 1:1s and standard support",
    ],
}

DISCLAIMER = ("Decision-support only. Risk scores are generated to support early, "
              "voluntary wellbeing intervention — never for punitive action, ranking, "
              "or automated decisions. An HR professional reviews every case (human-in-the-loop). "
              "All data shown is public, anonymised, or synthetic — no real employees.")


def load_workforce(path: Path = WORKFORCE) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    return json.loads(path.read_text())


def filter_by_role(emps, role, department):
    if role == "HR_Admin":
        return emps
    if role == "HR_Manager":
        return [e for e in emps if e["department"] == department] if department else []
    return []


def to_frame(emps) -> pd.DataFrame:
    if not emps:
        return pd.DataFrame(columns=["employeeId","department","jobTitle","cbri","riskLevel"])
    return pd.DataFrame([{
        "employeeId": e["employeeId"], "department": e["department"], "jobTitle": e["jobTitle"],
        "burnout": e["riskScores"]["burnout"], "mentalHealth": e["riskScores"]["mentalHealth"],
        "attrition": e["riskScores"]["attrition"], "cbri": e["cbri"], "riskLevel": e["riskLevel"],
    } for e in emps])


def exec_summary(emps) -> dict:
    df = to_frame(emps)
    vc = df["riskLevel"].value_counts().to_dict() if len(df) else {}
    return {"headcount": int(len(df)), "high": int(vc.get("High", 0)),
            "medium": int(vc.get("Medium", 0)), "low": int(vc.get("Low", 0)),
            "mean_cbri": round(float(df["cbri"].mean()), 3) if len(df) else 0.0,
            "pct_high": round(100*vc.get("High", 0)/len(df), 1) if len(df) else 0.0}


def dept_summary(emps) -> pd.DataFrame:
    df = to_frame(emps)
    if not len(df):
        return pd.DataFrame(columns=["department","headcount","meanCBRI","high","medium","low"])
    rows = []
    for dep, g in df.groupby("department"):
        vc = g["riskLevel"].value_counts().to_dict()
        rows.append({"department": dep, "headcount": int(len(g)),
                     "meanCBRI": round(float(g["cbri"].mean()), 3),
                     "high": int(vc.get("High", 0)), "medium": int(vc.get("Medium", 0)),
                     "low": int(vc.get("Low", 0))})
    return pd.DataFrame(rows).sort_values("meanCBRI", ascending=False).reset_index(drop=True)


def interventions_for(level): return INTERVENTIONS.get(level, [])


def build_employee_pdf(emp: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18*mm, bottomMargin=16*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Title"], fontSize=16, textColor=colors.HexColor("#2E5FA3"))
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=9, textColor=colors.grey)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10, leading=15)
    badge = {"High": colors.HexColor("#C0392B"), "Medium": colors.HexColor("#E59866"),
             "Low": colors.HexColor("#1F8A8A")}.get(emp["riskLevel"], colors.grey)
    el = [Paragraph("Employee Burnout Risk Report", h),
          Paragraph(f"Generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC · Explainable Burnout IDSS", sub),
          Spacer(1, 8)]
    info = Table([["Employee ID", emp["employeeId"], "Risk level", emp["riskLevel"]],
                 ["Department", emp["department"], "CBRI score", f"{emp['cbri']:.3f}"],
                 ["Job title", emp["jobTitle"], "", ""]], colWidths=[70,150,70,110])
    info.setStyle(TableStyle([("FONTSIZE",(0,0),(-1,-1),9),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TEXTCOLOR",(0,0),(0,-1),colors.grey),("TEXTCOLOR",(2,0),(2,-1),colors.grey),
        ("BACKGROUND",(3,0),(3,0),badge),("TEXTCOLOR",(3,0),(3,0),colors.white),
        ("FONTNAME",(3,0),(3,0),"Helvetica-Bold"),("LINEBELOW",(0,0),(-1,-1),0.3,colors.HexColor("#DDDDDD"))]))
    el += [info, Spacer(1, 10)]
    rs = emp["riskScores"]
    scores = Table([["Burnout","Mental health","Attrition"],
                    [f"{rs['burnout']:.0%}", f"{rs['mentalHealth']:.0%}", f"{rs['attrition']:.0%}"]],
                   colWidths=[140,140,140])
    scores.setStyle(TableStyle([("FONTSIZE",(0,0),(-1,0),9),("TEXTCOLOR",(0,0),(-1,0),colors.grey),
        ("FONTSIZE",(0,1),(-1,1),14),("FONTNAME",(0,1),(-1,1),"Helvetica-Bold"),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("BOX",(0,0),(-1,-1),0.4,colors.HexColor("#DDDDDD")),
        ("INNERGRID",(0,0),(-1,-1),0.4,colors.HexColor("#EEEEEE")),("TOPPADDING",(0,1),(-1,1),4)]))
    el += [Paragraph("Risk lenses", body), scores, Spacer(1, 10),
           Paragraph("Why this employee is flagged", body)]
    for f in emp["topFactors"]:
        el.append(Paragraph(f"&bull; {f['factor']} ({f['direction']} risk)", body))
    el += [Spacer(1, 8), Paragraph("Explanation", body), Paragraph(emp["explanationNarrative"], body),
           Spacer(1, 8), Paragraph("Suggested intervention actions", body)]
    for a in interventions_for(emp["riskLevel"]):
        el.append(Paragraph(f"&bull; {a}", body))
    el += [Spacer(1, 14), Paragraph(DISCLAIMER, sub)]
    doc.build(el)
    return buf.getvalue()
