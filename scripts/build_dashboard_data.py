import argparse
import json
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


def clean(value):
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timedelta, timedelta)):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 4)
    return str(value).strip() if isinstance(value, str) else value


def as_number(value):
    if pd.isna(value):
        return 0
    return float(value)


def pct(value):
    if pd.isna(value):
        return 0
    return round(float(value), 4)


def date_label(value):
    if pd.isna(value):
        return ""
    return pd.to_datetime(value).strftime("%b %Y")


def project_filter(df, column, project):
    if project is None or df.empty or column not in df.columns:
        return df
    return df[df[column].astype(str).str.strip() == project]


def hinderance_filter(df, project):
    if project is None or df.empty or "Project name" not in df.columns:
        return df
    return df[df["Project name"].astype(str).str.strip() == project]


def billing_trend(month_billing, project=None):
    df = project_filter(month_billing, "Project Name", project)
    if df.empty:
        return {"labels": [], "plan": [], "actual": []}
    grouped = (
        df.dropna(subset=["Month"])
        .assign(Month=lambda x: pd.to_datetime(x["Month"]))
        .groupby("Month", as_index=False)[["Plan (Cr.)", "Actual (Cr.)"]]
        .sum()
        .sort_values("Month")
        .tail(24)
    )
    return {
        "labels": [date_label(value) for value in grouped["Month"]],
        "plan": [round(as_number(value), 2) for value in grouped["Plan (Cr.)"]],
        "actual": [round(as_number(value), 2) for value in grouped["Actual (Cr.)"]],
    }


def progress_summary(progress, project=None):
    df = project_filter(progress, "Project Name", project)
    if df.empty:
        return {"labels": [], "plan": [], "actual": []}
    overall = df["Type of work"].astype(str).str.contains(r"over\s*all", case=False, na=False, regex=True)
    df = df[~overall]
    if df.empty:
        return {"labels": [], "plan": [], "actual": []}
    grouped = (
        df.groupby("Type of work", as_index=False)[
            ["Cumulative Planned Till Date (%)", "Cumulative Actual Till Date (%)"]
        ]
        .mean()
        .sort_values("Cumulative Actual Till Date (%)")
    )
    return {
        "labels": [clean(value) for value in grouped["Type of work"]],
        "plan": [round(as_number(value), 3) for value in grouped["Cumulative Planned Till Date (%)"]],
        "actual": [round(as_number(value), 3) for value in grouped["Cumulative Actual Till Date (%)"]],
    }


def project_progress_bars(progress, project=None):
    df = project_filter(progress, "Project Name", project).copy()
    if df.empty:
        return []
    overall = df["Type of work"].astype(str).str.contains(r"over\s*all", case=False, na=False, regex=True)
    df = df[overall].copy()
    if df.empty:
        return []
    rows = []
    for _, row in df.iterrows():
        planned = min(max(as_number(row.get("Cumulative Planned Till Date (%)")), 0), 1)
        actual = min(max(as_number(row.get("Cumulative Actual Till Date (%)")), 0), 1)
        completed = actual
        overdue = max(planned - actual, 0)
        pending = max(1 - max(planned, actual), 0)
        total = completed + overdue + pending
        if total and abs(total - 1) > 0.001:
            completed = completed / total
            overdue = overdue / total
            pending = pending / total
        rows.append(
            {
                "project": clean(row.get("Project Name")),
                "revision": clean(row.get("Revision Count")),
                "internal_comm": clean(row.get("Commissioning (Internal Schedule)")),
                "contract_comm": clean(row.get("Commissioning (Contract)")),
                "completed": round(completed, 4),
                "overdue": round(overdue, 4),
                "pending": round(pending, 4),
                "planned": round(planned, 4),
                "actual": round(actual, 4),
            }
        )
    rows.sort(key=lambda item: (item["completed"], -item["overdue"]), reverse=True)
    return rows[:24] if project is None else rows


def issues_summary(issues, project=None):
    df = project_filter(issues, "Project Name", project)
    if df.empty or "Criticality" not in df.columns:
        return {"labels": [], "values": []}
    counts = (
        df["Criticality"]
        .fillna("Unspecified")
        .astype(str)
        .str.strip()
        .replace("", "Unspecified")
        .value_counts()
    )
    return {"labels": list(counts.index), "values": [int(value) for value in counts.values]}


def budget_summary(budget, billing, project=None):
    bdf = project_filter(budget, "Project Name", project)
    if bdf.empty:
        return {"labels": [], "contract_value": [], "current_budget": [], "actual_billing": []}
    actuals = (
        billing.groupby("Project Name", as_index=False)["Actual Billing"].sum()
        if not billing.empty and "Actual Billing" in billing.columns
        else pd.DataFrame(columns=["Project Name", "Actual Billing"])
    )
    merged = bdf.merge(actuals, on="Project Name", how="left")
    merged = merged.sort_values("Contract value", ascending=False).head(10)
    return {
        "labels": [clean(value) for value in merged["Project Name"]],
        "contract_value": [round(as_number(value), 2) for value in merged["Contract value"]],
        "current_budget": [round(as_number(value), 2) for value in merged["Current Budget"]],
        "actual_billing": [round(as_number(value), 2) for value in merged["Actual Billing"]],
    }


def delay_summary(design, procurement, execution, project=None):
    return {
        "labels": ["Design", "Procurement", "Execution"],
        "values": [
            int(len(project_filter(design, "Project Name", project))),
            int(len(project_filter(procurement, "Project Name", project))),
            int(len(project_filter(execution, "Project Name", project))),
        ],
    }


def mfc_delay_summary(po_mfc, project=None):
    df = project_filter(po_mfc, "Project Name", project)
    if df.empty:
        return {"labels": [], "values": []}
    counts = (
        df["Status"]
        .fillna("Blank")
        .astype(str)
        .str.strip()
        .replace("", "Blank")
        .value_counts()
    )
    order = ["MFC was Delayed", "MFC is Overdue", "PO is Overdue", "MFC on Time", "PO not due yet", "MFC not due yet", "Blank"]
    labels = [label for label in order if label in counts.index] + [label for label in counts.index if label not in order]
    return {"labels": labels, "values": [int(counts[label]) for label in labels]}


def aging_bucket(days):
    days = as_number(days)
    if days >= 180:
        return "180+"
    if days >= 60:
        return "60-179"
    if days >= 31:
        return "31-59"
    if days > 0:
        return "0-30"
    return "Not aged"


def variance_cards(budget, billing, progress, commissioning, design, procurement, execution, project=None):
    bdf = project_filter(budget, "Project Name", project)
    bill_df = project_filter(billing, "Project Name", project)
    progress_df = project_filter(progress, "Project Name", project)
    commissioning_df = project_filter(commissioning, "Project Name", project).dropna(
        subset=["Commissioning (Internal Schedule)", "Commissioning (Contract)"]
    )
    overall = progress_df["Type of work"].astype(str).str.contains(
        r"over\s*all", case=False, na=False, regex=True
    )
    overall_df = progress_df[overall]
    plan_billing = as_number(bill_df["Plan Billing"].sum()) if "Plan Billing" in bill_df.columns else 0
    actual_billing = as_number(bill_df["Actual Billing"].sum()) if "Actual Billing" in bill_df.columns else 0
    plan_progress = as_number(overall_df["Cumulative Planned Till Date (%)"].mean())
    actual_progress = as_number(overall_df["Cumulative Actual Till Date (%)"].mean())
    current_budget = as_number(bdf["Current Budget"].sum()) if "Current Budget" in bdf.columns else 0
    contract_value = as_number(bdf["Contract value"].sum()) if "Contract value" in bdf.columns else 0
    target_pbt = as_number(bdf["Target PBT"].mean()) if "Target PBT" in bdf.columns else 0
    current_pbt = as_number(bdf["Current PBT"].mean()) if "Current PBT" in bdf.columns else 0
    late_commissioning = 0
    if not commissioning_df.empty:
        late_commissioning = int(
            (
                pd.to_datetime(commissioning_df["Commissioning (Internal Schedule)"])
                > pd.to_datetime(commissioning_df["Commissioning (Contract)"])
            ).sum()
        )
    delayed_items = sum(
        len(project_filter(df, "Project Name", project)) for df in [design, procurement, execution]
    )
    cards = [
        {
            "label": "FY Billing Achievement",
            "value": pct(actual_billing / plan_billing) if plan_billing else 0,
            "format": "percent",
            "status": "good" if actual_billing >= plan_billing else "bad",
            "note": "Actual billing as a percentage of FY planned billing",
        },
        {
            "label": "Billing Variance vs Plan",
            "value": round(actual_billing - plan_billing, 2),
            "format": "currency_delta",
            "status": "good" if actual_billing >= plan_billing else "bad",
            "note": "Actual billing minus FY planned billing",
        },
        {
            "label": "Project Progress Gap",
            "value": round(actual_progress - plan_progress, 4),
            "format": "percentage_point",
            "status": "good" if actual_progress >= plan_progress else "bad",
            "note": "Actual progress minus planned progress, in percentage points",
        },
        {
            "label": "Budget Headroom",
            "value": round(contract_value - current_budget, 2),
            "format": "currency",
            "status": "good" if contract_value >= current_budget else "bad",
            "note": "Contract value minus current budget; positive means room remains",
        },
        {
            "label": "PBT Gap",
            "value": round(current_pbt - target_pbt, 4),
            "format": "percentage_point",
            "status": "good" if current_pbt >= target_pbt else "bad",
            "note": "Current PBT minus target PBT, in percentage points",
        },
        {
            "label": "Delayed Action Items",
            "value": int(delayed_items),
            "format": "number",
            "status": "bad" if delayed_items else "good",
            "note": "Open design, procurement, and construction action items",
        },
        {
            "label": "Late Commissioning Projects",
            "value": late_commissioning,
            "format": "number",
            "status": "bad" if late_commissioning else "good",
            "note": "Projects where internal commissioning is after contract date",
        },
    ]
    return cards


def risk_rankings(budget, billing, progress, design, procurement, execution, project=None):
    project_scope = None if project is None else {project}
    progress_df = progress.copy()
    overall = progress_df["Type of work"].astype(str).str.contains(
        r"over\s*all", case=False, na=False, regex=True
    )
    progress_df = progress_df[overall]
    if project_scope:
        progress_df = progress_df[progress_df["Project Name"].isin(project_scope)]
    progress_df = progress_df.assign(
        gap=progress_df["Cumulative Actual Till Date (%)"] - progress_df["Cumulative Planned Till Date (%)"]
    )
    lowest_progress = [
        {
            "project": clean(row["Project Name"]),
            "actual": pct(row["Cumulative Actual Till Date (%)"]),
            "gap": pct(row["gap"]),
        }
        for _, row in progress_df.sort_values("Cumulative Actual Till Date (%)").head(6).iterrows()
    ]

    bill_df = project_filter(billing, "Project Name", project)
    billing_gap_df = (
        bill_df.groupby("Project Name", as_index=False)[["Plan Billing", "Actual Billing"]].sum()
        if not bill_df.empty
        else pd.DataFrame(columns=["Project Name", "Plan Billing", "Actual Billing"])
    )
    billing_gap_df["gap"] = billing_gap_df["Actual Billing"] - billing_gap_df["Plan Billing"]
    billing_gap = [
        {
            "project": clean(row["Project Name"]),
            "gap": round(as_number(row["gap"]), 2),
            "plan": round(as_number(row["Plan Billing"]), 2),
            "actual": round(as_number(row["Actual Billing"]), 2),
        }
        for _, row in billing_gap_df.sort_values("gap").head(6).iterrows()
    ]

    bdf = project_filter(budget, "Project Name", project).copy()
    bdf["overrun"] = bdf["Current Budget"] - bdf["Contract value"]
    budget_overrun = [
        {
            "project": clean(row["Project Name"]),
            "overrun": round(as_number(row["overrun"]), 2),
            "contract": round(as_number(row["Contract value"]), 2),
            "budget": round(as_number(row["Current Budget"]), 2),
        }
        for _, row in bdf.sort_values("overrun", ascending=False).head(6).iterrows()
        if as_number(row["overrun"]) > 0
    ]

    delay_frames = []
    for area, df in [("Design", design), ("Procurement", procurement), ("Execution", execution)]:
        dfx = project_filter(df, "Project Name", project).copy()
        if dfx.empty:
            continue
        dfx["area"] = area
        dfx["delay_days"] = dfx["Due Since (Days)"] if "Due Since (Days)" in dfx.columns else 0
        delay_frames.append(dfx[["Project Name", "area", "delay_days"]])
    if delay_frames:
        delay_df = pd.concat(delay_frames, ignore_index=True)
        top_delays_df = (
            delay_df.groupby("Project Name", as_index=False)
            .agg(items=("area", "count"), max_days=("delay_days", "max"))
            .sort_values(["max_days", "items"], ascending=False)
            .head(6)
        )
    else:
        top_delays_df = pd.DataFrame(columns=["Project Name", "items", "max_days"])
    top_delays = [
        {
            "project": clean(row["Project Name"]),
            "items": int(row["items"]),
            "max_days": int(as_number(row["max_days"])),
        }
        for _, row in top_delays_df.iterrows()
    ]

    return {
        "lowest_progress": lowest_progress,
        "billing_gap": billing_gap,
        "budget_overrun": budget_overrun,
        "top_delays": top_delays,
    }


def mfc_details(po_mfc, project=None):
    df = project_filter(po_mfc, "Project Name", project).copy()
    if df.empty:
        return []
    df["mfc_delay_days"] = (
        pd.to_datetime(df["MFC Actual"], errors="coerce") - pd.to_datetime(df["MFC Plan"], errors="coerce")
    ).dt.days
    status_sort = df["Status"].astype(str).str.contains("delay", case=False, na=False)
    df = df.assign(status_sort=status_sort).sort_values(["status_sort", "mfc_delay_days"], ascending=False).head(40)
    return [
        {
            "project": clean(row["Project Name"]),
            "item": clean(row["Item Name"]),
            "po_plan": clean(row["PO Plan"]),
            "po_actual": clean(row["PO Actual"]),
            "mfc_plan": clean(row["MFC Plan"]),
            "mfc_actual": clean(row["MFC Actual"]),
            "delay_days": int(as_number(row["mfc_delay_days"])),
            "status": clean(row["Status"]),
        }
        for _, row in df.iterrows()
    ]


def mfc_top_delays(po_mfc, project=None):
    df = project_filter(po_mfc, "Project Name", project).copy()
    if df.empty:
        return []
    df["mfc_delay_days"] = (
        pd.to_datetime(df["MFC Actual"], errors="coerce") - pd.to_datetime(df["MFC Plan"], errors="coerce")
    ).dt.days
    delayed = df[df["Status"].astype(str).str.contains("delay|overdue", case=False, na=False)]
    if delayed.empty:
        return []
    grouped = (
        delayed.groupby("Project Name", as_index=False)
        .agg(items=("Item Name", "count"), max_days=("mfc_delay_days", "max"))
        .sort_values(["max_days", "items"], ascending=False)
        .head(6)
    )
    return [
        {
            "project": clean(row["Project Name"]),
            "items": int(row["items"]),
            "max_days": int(as_number(row["max_days"])),
        }
        for _, row in grouped.iterrows()
    ]


def critical_issue_details(issues, project=None):
    df = project_filter(issues, "Project Name", project).copy()
    if df.empty:
        return []
    df = df.sort_values("Timestamp", ascending=False).head(40)
    return [
        {
            "timestamp": clean(row["Timestamp"]),
            "project": clean(row["Project Name"]),
            "issue": clean(row["Issues as on date"]),
            "criticality": clean(row["Criticality"]),
            "responsibility": clean(row["Responsibilities"]),
            "remarks": clean(row["Remarks"]),
            "status": clean(row["Status"]),
        }
        for _, row in df.iterrows()
    ]


def budget_details(budget, project=None):
    df = project_filter(budget, "Project Name", project).copy()
    if df.empty:
        return []
    df["budget_variance"] = df["Contract value"] - df["Current Budget"]
    df["pbt_gap"] = df["Current PBT"] - df["Target PBT"]
    df = df.sort_values("Contract value", ascending=False).head(40)
    return [
        {
            "project": clean(row["Project Name"]),
            "contract_value": round(as_number(row["Contract value"]), 2),
            "initial_budget": round(as_number(row["Initial Pre-Bid Budget"]), 2),
            "current_budget": round(as_number(row["Current Budget"]), 2),
            "final_cost": round(as_number(row["Final Cost"]), 2) if not pd.isna(row["Final Cost"]) else None,
            "target_pbt": pct(row["Target PBT"]),
            "current_pbt": pct(row["Current PBT"]),
            "budget_variance": round(as_number(row["budget_variance"]), 2),
            "pbt_gap": pct(row["pbt_gap"]),
        }
        for _, row in df.iterrows()
    ]


def hinderance_summary(hinderance, project=None):
    df = hinderance_filter(hinderance, project)
    if df.empty:
        return {"labels": [], "values": []}
    counts = (
        df["Hinderance"]
        .fillna("Unspecified")
        .astype(str)
        .str.strip()
        .replace("", "Unspecified")
        .value_counts()
        .head(8)
    )
    return {"labels": list(counts.index), "values": [int(value) for value in counts.values]}


def hinderance_details(hinderance, project=None):
    df = hinderance_filter(hinderance, project).copy()
    if df.empty:
        return []
    df = df.sort_values("Date", ascending=False).head(40)
    return [
        {
            "date": clean(row["Date"]),
            "project": clean(row["Project name"]),
            "block": clean(row["Block"]),
            "hinderance": clean(row["Hinderance"]),
            "start": clean(row["Hinderance Start Time"]),
            "end": clean(row["Hinderance End Time"]),
            "duration": clean(row["Duration"]),
            "remarks": clean(row["Remarks"]),
        }
        for _, row in df.iterrows()
    ]


def commissioning_summary(commissioning, project=None):
    df = project_filter(commissioning, "Project Name", project).dropna(
        subset=["Commissioning (Internal Schedule)", "Commissioning (Contract)"]
    )
    if df.empty:
        return []
    df = df.assign(
        internal=pd.to_datetime(df["Commissioning (Internal Schedule)"]),
        contract=pd.to_datetime(df["Commissioning (Contract)"]),
    )
    df["days_delta"] = (df["internal"] - df["contract"]).dt.days
    if project is None:
        df = df.reindex(df["days_delta"].abs().sort_values(ascending=False).index).head(6)
    return [
        {
            "project": clean(row["Project Name"]),
            "internal_date": clean(row["internal"]),
            "contract_date": clean(row["contract"]),
            "days_delta": int(row["days_delta"]),
        }
        for _, row in df.iterrows()
    ]


def attention_rows(design, procurement, execution, project=None):
    rows = []
    for area, df, fields in [
        (
            "Design",
            project_filter(design, "Project Name", project),
            ("DOCUMENT TITLE", "Priority", "Responsibility", "Target Date"),
        ),
        (
            "Procurement",
            project_filter(procurement, "Project Name", project),
            ("Task Description", "Priority", "Responsibility", "Target Dates of Pendency"),
        ),
        (
            "Construction",
            project_filter(execution, "Project Name", project),
            ("Activity", "Reason of Delay", "Project Name", "Plan Finish Date"),
        ),
    ]:
        if df.empty:
            continue
        sort_col = "Due Since (Days)" if "Due Since (Days)" in df.columns else fields[3]
        subset = df.sort_values(sort_col, ascending=False).head(50)
        for _, row in subset.iterrows():
            rows.append(
                {
                    "area": area,
                    "team": area,
                    "project": clean(row.get("Project Name")),
                    "priority": clean(row.get(fields[1])),
                    "item": clean(row.get(fields[0])),
                    "owner": clean(row.get(fields[2])),
                    "status": "",
                    "due": clean(row.get(fields[3])),
                    "delay_days": int(as_number(row.get("Due Since (Days)", 0))),
                    "aging": aging_bucket(row.get("Due Since (Days)", 0)),
                }
            )
    return rows


def kpis(projects, budget, billing, issues, progress, project=None):
    project_names = [project] if project else projects
    bdf = project_filter(budget, "Project Name", project)
    bill_df = project_filter(billing, "Project Name", project)
    issue_df = project_filter(issues, "Project Name", project)
    progress_df = project_filter(progress, "Project Name", project)
    overall = progress_df["Type of work"].astype(str).str.contains(
        r"over\s*all", case=False, na=False, regex=True
    )
    actual_progress = progress_df.loc[overall, "Cumulative Actual Till Date (%)"]
    open_issues = issue_df["Status"].astype(str).str.contains("open", case=False, na=False).sum()

    return {
        "project_count": len(project_names),
        "order_book": round(as_number(bill_df["Order Book"].dropna().sum()), 2)
        if "Order Book" in bill_df.columns
        else 0,
        "plan_billing": round(as_number(bill_df["Plan Billing"].sum()), 2)
        if "Plan Billing" in bill_df.columns
        else 0,
        "plan_td": round(as_number(bill_df["Plan TD"].dropna().sum()), 2)
        if "Plan TD" in bill_df.columns
        else 0,
        "billing_projection": round(as_number(bill_df["Billing Projection"].dropna().sum()), 2)
        if "Billing Projection" in bill_df.columns
        else 0,
        "contract_value": round(as_number(bdf["Contract value"].sum()), 2),
        "actual_billing": round(as_number(bill_df["Actual Billing"].sum()), 2),
        "open_issues": int(open_issues),
        "avg_actual_progress": round(as_number(actual_progress.mean()), 4),
    }


def numeric_series(df, column, default=0):
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def merge_project_features(base, features):
    if features.empty:
        return base
    return base.merge(features, on="Project Name", how="left")


def delay_features(df, prefix):
    if df.empty or "Project Name" not in df.columns:
        return pd.DataFrame(columns=["Project Name", f"{prefix}_Delay_Count", f"Avg_{prefix}_Delay", f"Max_{prefix}_Delay"])
    work = df.copy()
    work["delay_days"] = numeric_series(work, "Due Since (Days)")
    return (
        work.groupby("Project Name", as_index=False)
        .agg(
            **{
                f"{prefix}_Delay_Count": ("Project Name", "size"),
                f"Avg_{prefix}_Delay": ("delay_days", "mean"),
                f"Max_{prefix}_Delay": ("delay_days", "max"),
            }
        )
    )


def risk_reasons(row):
    reasons = []
    drivers = []

    def add(reason, driver):
        if reason not in reasons:
            reasons.append(reason)
        if driver not in drivers:
            drivers.append(driver)

    if row["Avg_Procurement_Delay"] >= 60 or row["Max_Procurement_Delay"] >= 180:
        add("Severe procurement delay", "Procurement Delay")
    elif row["Avg_Procurement_Delay"] >= 20 or row["Procurement_Delay_Count"] >= 5:
        add("Procurement delay", "Procurement Delay")

    if row["Avg_Design_Delay"] >= 60 or row["Max_Design_Delay"] >= 180:
        add("Severe design delay", "Design Delay")
    elif row["Avg_Design_Delay"] >= 20 or row["Design_Delay_Count"] >= 5:
        add("Design delay", "Design Delay")

    if row["Execution_Gap"] <= -10 or row["Execution_Delay_Count"] >= 5:
        add("Execution lag", "Execution Lag")
    elif row["Execution_Gap"] <= -5:
        add("Execution behind plan", "Execution Lag")

    if row["Progress_Difference"] <= -10:
        add("Progress lag", "Progress Lag")
    elif row["Progress_Difference"] <= -5:
        add("Progress behind plan", "Progress Lag")

    if row["Issue_Count"] >= 5 or row["High_Issue_Count"] >= 1:
        add("Critical issue load", "Critical Issues")

    if row["Billing_Has_Plan"] and row["Billing_Achievement"] < 0.7:
        add("Low billing achievement", "Billing Gap")
    elif row["Billing_Has_Plan"] and row["Billing_Achievement"] < 0.9:
        add("Billing behind plan", "Billing Gap")

    if row["PBT_Gap"] <= -0.05:
        add("PBT below target", "PBT Gap")
    elif row["Current_PBT"] < 0:
        add("Negative current PBT", "PBT Gap")

    if row["Hinderance_Count"] >= 10:
        add("High site hindrance count", "Site Hindrance")

    return reasons, drivers


def ai_project_intelligence(projects, sheets):
    features = pd.DataFrame({"Project Name": projects})

    progress = sheets["Project Progress"].copy()
    if not progress.empty and "Type of work" in progress.columns:
        overall = progress["Type of work"].astype(str).str.contains(r"over\s*all", case=False, na=False, regex=True)
        progress = progress[overall].copy()
        progress["Progress_Difference"] = (
            numeric_series(progress, "Cumulative Actual Till Date (%)")
            - numeric_series(progress, "Cumulative Planned Till Date (%)")
        ) * 100
        progress["Balance_Percent"] = numeric_series(progress, "Balance (%)") * 100
        progress_features = progress.groupby("Project Name", as_index=False).agg(
            Progress_Difference=("Progress_Difference", "mean"),
            Balance_Percent=("Balance_Percent", "mean"),
        )
        features = merge_project_features(features, progress_features)

    issues = sheets["Critical Issues"].copy()
    if not issues.empty and "Project Name" in issues.columns:
        issues["high_issue"] = issues["Criticality"].astype(str).str.contains(
            "high|critical|severe", case=False, na=False
        )
        issue_features = issues.groupby("Project Name", as_index=False).agg(
            Issue_Count=("Project Name", "size"),
            High_Issue_Count=("high_issue", "sum"),
        )
        features = merge_project_features(features, issue_features)

    for prefix, sheet_name in [
        ("Design", "Design Delay and Action Plan"),
        ("Procurement", "Procurement Delay and Action Pl"),
    ]:
        features = merge_project_features(features, delay_features(sheets[sheet_name], prefix))

    execution_delay = sheets["Execution Delay and Action Plan"].copy()
    if not execution_delay.empty and "Project Name" in execution_delay.columns:
        execution_delay["execution_delay_gap"] = (
            numeric_series(execution_delay, "Cumulative Actual(%) Till Date")
            - numeric_series(execution_delay, "Cumulative Planned(%) Till Date")
        ) * 100
        execution_delay_features = execution_delay.groupby("Project Name", as_index=False).agg(
            Execution_Delay_Count=("Project Name", "size"),
            Execution_Delay_Gap=("execution_delay_gap", "mean"),
        )
        features = merge_project_features(features, execution_delay_features)

    execution_comparison = sheets["Execution Comparison"].copy()
    if not execution_comparison.empty and "Project Name" in execution_comparison.columns:
        execution_comparison["Execution_Gap"] = (
            numeric_series(execution_comparison, "Cumulative Actual(%) Till Date")
            - numeric_series(execution_comparison, "Cumulative Planned(%) Till Date")
        ) * 100
        execution_features = execution_comparison.groupby("Project Name", as_index=False).agg(
            Execution_Gap=("Execution_Gap", "mean")
        )
        features = merge_project_features(features, execution_features)

    billing = sheets["Project Billing"].copy()
    if not billing.empty and "Project Name" in billing.columns:
        billing_features = billing.groupby("Project Name", as_index=False).agg(
            Plan_Billing=("Plan Billing", "sum"),
            Actual_Billing=("Actual Billing", "sum"),
            Billing_Projection=("Billing Projection", "sum"),
        )
        billing_features["Billing_Achievement"] = np.where(
            billing_features["Plan_Billing"] > 0,
            billing_features["Actual_Billing"] / billing_features["Plan_Billing"],
            0,
        )
        billing_features["Billing_Has_Plan"] = billing_features["Plan_Billing"] > 0
        billing_features["Billing_Projection_Gap"] = np.where(
            billing_features["Plan_Billing"] > 0,
            (billing_features["Billing_Projection"] - billing_features["Plan_Billing"])
            / billing_features["Plan_Billing"],
            0,
        )
        features = merge_project_features(features, billing_features)

    budget = sheets["Budget"].copy()
    if not budget.empty and "Project Name" in budget.columns:
        budget_features = budget.groupby("Project Name", as_index=False).agg(
            Contract_Value=("Contract value", "sum"),
            Current_Budget=("Current Budget", "sum"),
            Target_PBT=("Target PBT", "mean"),
            Current_PBT=("Current PBT", "mean"),
        )
        budget_features["Budget_Headroom"] = budget_features["Contract_Value"] - budget_features["Current_Budget"]
        budget_features["PBT_Gap"] = budget_features["Current_PBT"] - budget_features["Target_PBT"]
        features = merge_project_features(features, budget_features)

    hinderance = sheets["Hinderance"].copy()
    if not hinderance.empty and "Project name" in hinderance.columns:
        hinderance_features = (
            hinderance.groupby("Project name", as_index=False)
            .size()
            .rename(columns={"Project name": "Project Name", "size": "Hinderance_Count"})
        )
        features = merge_project_features(features, hinderance_features)

    feature_defaults = {
        "Progress_Difference": 0,
        "Balance_Percent": 0,
        "Issue_Count": 0,
        "High_Issue_Count": 0,
        "Design_Delay_Count": 0,
        "Avg_Design_Delay": 0,
        "Max_Design_Delay": 0,
        "Procurement_Delay_Count": 0,
        "Avg_Procurement_Delay": 0,
        "Max_Procurement_Delay": 0,
        "Execution_Delay_Count": 0,
        "Execution_Delay_Gap": 0,
        "Execution_Gap": 0,
        "Plan_Billing": 0,
        "Actual_Billing": 0,
        "Billing_Projection": 0,
        "Billing_Achievement": 0,
        "Billing_Has_Plan": False,
        "Billing_Projection_Gap": 0,
        "Contract_Value": 0,
        "Current_Budget": 0,
        "Target_PBT": 0,
        "Current_PBT": 0,
        "Budget_Headroom": 0,
        "PBT_Gap": 0,
        "Hinderance_Count": 0,
    }
    for column, default in feature_defaults.items():
        if column not in features.columns:
            features[column] = default
    features = features.fillna(feature_defaults)

    features["Progress_Lag_Risk"] = (-features["Progress_Difference"]).clip(lower=0)
    features["Execution_Lag_Risk"] = (-features["Execution_Gap"]).clip(lower=0)
    features["Billing_Shortfall_Risk"] = np.where(
        features["Billing_Has_Plan"],
        (1 - features["Billing_Achievement"]).clip(lower=0),
        0,
    )
    features["PBT_Shortfall_Risk"] = (-features["PBT_Gap"]).clip(lower=0)
    model_columns = [
        "Progress_Lag_Risk",
        "Issue_Count",
        "Avg_Design_Delay",
        "Avg_Procurement_Delay",
        "Execution_Lag_Risk",
        "Billing_Shortfall_Risk",
        "PBT_Shortfall_Risk",
        "Hinderance_Count",
    ]

    matrix = features[model_columns].to_numpy(dtype=float)
    if len(features) >= 3:
        scaled = StandardScaler().fit_transform(matrix)
        contamination = min(0.25, max(0.08, 4 / len(features)))
        model = IsolationForest(n_estimators=300, contamination=contamination, random_state=42)
        predictions = model.fit_predict(scaled)
        raw_risk = -model.decision_function(scaled)
    else:
        predictions = np.ones(len(features))
        raw_risk = np.zeros(len(features))

    spread = float(np.max(raw_risk) - np.min(raw_risk)) if len(raw_risk) else 0
    if spread > 0:
        risk_index = ((raw_risk - np.min(raw_risk)) / spread) * 100
    else:
        risk_index = np.zeros(len(features))

    high_threshold = max(70.0, float(np.quantile(risk_index, 0.85))) if len(features) else 70.0
    medium_threshold = max(45.0, float(np.quantile(risk_index, 0.60))) if len(features) else 45.0

    rows = []
    for index, row in features.iterrows():
        score = round(float(risk_index[index]), 1)
        if predictions[index] == -1 or score >= high_threshold:
            status = "High Risk"
            priority = "Immediate Review"
        elif score >= medium_threshold:
            status = "Medium Risk"
            priority = "Watchlist"
        else:
            status = "Normal"
            priority = "Stable"

        reasons, drivers = risk_reasons(row)
        if not reasons and status != "Normal":
            reasons = ["Abnormal combined project pattern"]
            drivers = ["Portfolio Anomaly"]
        reason_text = ", ".join(reasons) if reasons else "No dominant abnormal driver"
        rows.append(
            {
                "project": clean(row["Project Name"]),
                "risk_status": status,
                "priority": priority,
                "risk_score": score,
                "anomaly_score": round(float(raw_risk[index]), 4),
                "risk_reason": reason_text,
                "drivers": drivers,
                "progress_difference": round(float(row["Progress_Difference"]), 1),
                "issue_count": int(row["Issue_Count"]),
                "design_delay_count": int(row["Design_Delay_Count"]),
                "avg_design_delay": round(float(row["Avg_Design_Delay"]), 1),
                "procurement_delay_count": int(row["Procurement_Delay_Count"]),
                "avg_procurement_delay": round(float(row["Avg_Procurement_Delay"]), 1),
                "execution_gap": round(float(row["Execution_Gap"]), 1),
                "execution_delay_count": int(row["Execution_Delay_Count"]),
                "billing_achievement": round(float(row["Billing_Achievement"]), 4)
                if row["Billing_Has_Plan"]
                else None,
                "current_pbt": round(float(row["Current_PBT"]), 4),
                "pbt_gap": round(float(row["PBT_Gap"]), 4),
                "hinderance_count": int(row["Hinderance_Count"]),
            }
        )

    rows.sort(key=lambda item: item["risk_score"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    high = sum(1 for row in rows if row["risk_status"] == "High Risk")
    medium = sum(1 for row in rows if row["risk_status"] == "Medium Risk")
    normal = sum(1 for row in rows if row["risk_status"] == "Normal")
    flagged = [row for row in rows if row["risk_status"] != "Normal"]
    driver_counter = Counter(driver for row in flagged for driver in row["drivers"])
    driver_counts = [
        {"driver": driver, "projects": count}
        for driver, count in driver_counter.most_common()
    ]
    top_project = rows[0] if rows else None
    dominant_driver = driver_counts[0]["driver"] if driver_counts else "No single dominant driver"
    insight = (
        f"{len(flagged)} projects show elevated AI risk. "
        f"{dominant_driver} is the most common driver across flagged projects. "
        f"The highest-risk project is {top_project['project']} due to {top_project['risk_reason']}."
        if top_project
        else "No project risk records were generated."
    )

    return {
        "model": "Isolation Forest",
        "features_used": model_columns,
        "summary": {
            "projects_analysed": len(rows),
            "high_risk": high,
            "medium_risk": medium,
            "normal": normal,
            "average_risk_score": round(float(np.mean(risk_index)), 1) if len(risk_index) else 0,
        },
        "cards": [
            {"label": "Projects Analysed", "value": len(rows), "note": "Project-level rows used by the AI model"},
            {"label": "High Risk Projects", "value": high, "note": "Projects needing immediate management review"},
            {"label": "Medium Risk Projects", "value": medium, "note": "Projects on the watchlist"},
            {"label": "Normal Projects", "value": normal, "note": "Projects without abnormal risk signals"},
            {
                "label": "Average Risk Index",
                "value": round(float(np.mean(risk_index)), 1) if len(risk_index) else 0,
                "note": "0 to 100 score, higher means more abnormal risk",
            },
        ],
        "driver_counts": driver_counts,
        "top_projects": rows[:8],
        "risks": rows,
        "insight": insight,
    }


def build_view(projects, sheets, project=None):
    return {
        "kpis": kpis(
            projects,
            sheets["Budget"],
            sheets["Project Billing"],
            sheets["Critical Issues"],
            sheets["Project Progress"],
            project,
        ),
        "billing_trend": billing_trend(sheets["Month-wise Billing"], project),
        "progress": progress_summary(sheets["Project Progress"], project),
        "project_progress_bars": project_progress_bars(sheets["Project Progress"], project),
        "issues": issues_summary(sheets["Critical Issues"], project),
        "budget": budget_summary(sheets["Budget"], sheets["Project Billing"], project),
        "delays": mfc_delay_summary(sheets["PO MFC"], project),
        "variance_cards": variance_cards(
            sheets["Budget"],
            sheets["Project Billing"],
            sheets["Project Progress"],
            sheets["Commissioning"],
            sheets["Design Delay and Action Plan"],
            sheets["Procurement Delay and Action Pl"],
            sheets["Execution Delay and Action Plan"],
            project,
        ),
        "rankings": risk_rankings(
            sheets["Budget"],
            sheets["Project Billing"],
            sheets["Project Progress"],
            sheets["Design Delay and Action Plan"],
            sheets["Procurement Delay and Action Pl"],
            sheets["Execution Delay and Action Plan"],
            project,
        ),
        "commissioning": commissioning_summary(sheets["Commissioning"], project),
        "mfc_details": mfc_details(sheets["PO MFC"], project),
        "mfc_top_delays": mfc_top_delays(sheets["PO MFC"], project),
        "critical_issue_details": critical_issue_details(sheets["Critical Issues"], project),
        "budget_details": budget_details(sheets["Budget"], project),
        "hinderance": hinderance_summary(sheets["Hinderance"], project),
        "hinderance_details": hinderance_details(sheets["Hinderance"], project),
        "attention": attention_rows(
            sheets["Design Delay and Action Plan"],
            sheets["Procurement Delay and Action Pl"],
            sheets["Execution Delay and Action Plan"],
            project,
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to the Excel workbook")
    parser.add_argument("--output", default="data/dashboard_data.json")
    args = parser.parse_args()

    workbook = pd.ExcelFile(args.input)
    sheets = {sheet: pd.read_excel(workbook, sheet_name=sheet) for sheet in workbook.sheet_names}
    project_names = sorted(
        {
            str(value).strip()
            for sheet in sheets.values()
            for column in ["Project Name", "Project name"]
            if column in sheet.columns
            for value in sheet[column].dropna().unique()
            if str(value).strip()
        }
    )

    ai_results = ai_project_intelligence(project_names, sheets)

    data = {
        "summary": {
            "project_count": len(project_names),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source_file": Path(args.input).name,
        },
        "project_names": project_names,
        "ai": ai_results,
        "portfolio": build_view(project_names, sheets),
        "projects": {project: build_view(project_names, sheets, project) for project in project_names},
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path.with_name("risk_results.json").write_text(
        json.dumps(ai_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
