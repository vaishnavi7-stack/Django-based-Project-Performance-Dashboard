Rays Power Infra Project Dashboard
=================================

A Django-based project performance dashboard built from an Excel workbook.
The dashboard is inspired by Looker Studio and provides financial, progress, delay, budget, issue, and hindrance views for project monitoring.

Features
--------

- Portfolio and project-wise dashboard views
- Project filter
- Financial KPI cards
- KPI trend indicators
- Dark mode toggle
- Export buttons for CSV, Excel, and PDF
- Last refresh timestamp
- Loading skeletons while data loads
- Billing plan vs actual trend
- Project progress comparison
- MFC delay summary and detail list
- Budget summary with PBT and variance fields
- Critical issue register
- Delay activity list with aging buckets
- Hindrance report with cause mix and detailed records

Tech Stack
----------

- Python
- Django
- HTML
- CSS
- JavaScript
- Chart.js
- Pandas

Project Structure
-----------------

.
|-- manage.py
|-- requirements.txt
|-- data/
|   `-- dashboard_data.json
|-- dashboard/
|   |-- __init__.py
|   |-- apps.py
|   |-- urls.py
|   `-- views.py
|-- scripts/
|   `-- build_dashboard_data.py
|-- solar_dashboard/
|   |-- __init__.py
|   |-- asgi.py
|   |-- settings.py
|   |-- urls.py
|   `-- wsgi.py
|-- static/
|   `-- dashboard/
|       |-- dashboard.js
|       `-- styles.css
`-- templates/
    `-- dashboard/
        `-- index.html

Local Setup
-----------

Clone the repository:

git clone <your-repo-url>
cd <your-repo-folder>

Create a virtual environment:

python -m venv work/.venv

Activate the virtual environment.

On Windows:

work\.venv\Scripts\activate

On macOS/Linux:

source work/.venv/bin/activate

Install dependencies:

pip install -r requirements.txt

Run the Django server:

python manage.py runserver

Open the dashboard:

http://127.0.0.1:8000/

Rebuilding Dashboard Data
-------------------------

The dashboard uses this generated data file:

data/dashboard_data.json

To rebuild the data from the Excel workbook:

python scripts/build_dashboard_data.py --input "path/to/Demo (2).xlsx" --output data/dashboard_data.json

Example on Windows:

python scripts\build_dashboard_data.py --input "C:\Users\YourName\Downloads\Demo (2).xlsx" --output data\dashboard_data.json

After rebuilding the data, restart or refresh the Django app.

Deployment On Render
--------------------

This project can be deployed as a Django web service on Render.

1. Push Code To GitHub

Push the full project folder to a GitHub repository.
The repository can be public or private.

2. Create A Render Web Service

Go to:

https://dashboard.render.com

Click:

New + > Web Service

Connect your GitHub repository.

3. Render Settings

Use these settings:

Environment: Python
Branch: main

Build command:

pip install -r requirements.txt && python manage.py collectstatic --noinput

Start command:

gunicorn solar_dashboard.wsgi:application

4. Environment Variables

Add these environment variables in Render:

SECRET_KEY=your-long-random-secret-key
DEBUG=False
ALLOWED_HOSTS=.onrender.com

If you have a custom domain later, add it to ALLOWED_HOSTS.

Production Requirements
-----------------------

For deployment, requirements.txt should include:

Django>=5.0,<6.0
gunicorn
whitenoise
pandas
openpyxl

Notes
-----

- The Excel file is used only to generate data/dashboard_data.json.
- The deployed dashboard can run without the Excel file if dashboard_data.json is already included.
- To update dashboard numbers, rebuild dashboard_data.json and redeploy.
- A private GitHub repo keeps the code private.
- A public Render URL can still be viewed by anyone with the link unless authentication is added.

Future Improvements
-------------------

- User login and password protection
- Auto-refresh from Google Sheets or a database
- Downloadable filtered reports
- More detailed project drill-down pages
- Role-based access for different teams
- Scheduled data refresh pipeline
