import argparse
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd


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
            "label": "Billing Achievement",
            "value": pct(actual_billing / plan_billing) if plan_billing else 0,
            "format": "percent",
            "status": "good" if actual_billing >= plan_billing else "bad",
            "note": "Actual billing / planned billing",
        },
        {
            "label": "Billing Variance",
            "value": round(actual_billing - plan_billing, 2),
            "format": "currency",
            "status": "good" if actual_billing >= plan_billing else "bad",
            "note": "Actual minus plan",
        },
        {
            "label": "Progress Gap",
            "value": round(actual_progress - plan_progress, 4),
            "format": "percent_delta",
            "status": "good" if actual_progress >= plan_progress else "bad",
            "note": "Actual progress minus planned",
        },
        {
            "label": "Budget Headroom",
            "value": round(contract_value - current_budget, 2),
            "format": "currency",
            "status": "good" if contract_value >= current_budget else "bad",
            "note": "Contract value minus current budget",
        },
        {
            "label": "PBT Gap",
            "value": round(current_pbt - target_pbt, 4),
            "format": "percent_delta",
            "status": "good" if current_pbt >= target_pbt else "bad",
            "note": "Current PBT minus target PBT",
        },
        {
            "label": "Delayed Items",
            "value": int(delayed_items),
            "format": "number",
            "status": "bad" if delayed_items else "good",
            "note": "Design, procurement, execution",
        },
        {
            "label": "Late Commissioning",
            "value": late_commissioning,
            "format": "number",
            "status": "bad" if late_commissioning else "good",
            "note": "Internal date after contract",
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

    data = {
        "summary": {
            "project_count": len(project_names),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source_file": Path(args.input).name,
        },
        "project_names": project_names,
        "portfolio": build_view(project_names, sheets),
        "projects": {project: build_view(project_names, sheets, project) for project in project_names},
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
