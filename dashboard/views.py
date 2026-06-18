import json
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import render


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "dashboard_data.json"


def _load_dashboard_data():
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def index(request):
    data = _load_dashboard_data()
    return render(
        request,
        "dashboard/index.html",
        {
            "project_count": data["summary"]["project_count"],
            "last_updated": data["summary"]["last_updated"],
        },
    )


def dashboard_data(request):
    return JsonResponse(_load_dashboard_data())
