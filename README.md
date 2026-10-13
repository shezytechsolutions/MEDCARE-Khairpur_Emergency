🏥 MedCare Emergency — Resource Manager

A Flask + SQLite web application for managing hospital emergency resources — smart auto-allocation of beds, doctors and ambulances, a guided AI chatbot assistant, and live ambulance tracking on a map.

OpenHack 2026 · Team HT-03 (Musafir Devs)

✨ Features

🤖 AI Assistant (Guided Emergency Intake)

Chat-style emergency registration in under a minute

Guided flow: Name → Age → Condition → Severity → Location (GPS or typed) → Hospital → Ambulance

Sits as a bottom bar on every page; slides up to full-screen chat on click (mobile & desktop)

🚑 Smart Auto-Allocation

Bed — assigned by priority (Critical → ICU/Emergency, Low → General)

Doctor — matched by specialty keywords in the condition description

Ambulance — nearest available unit within 20 km (10-unit fleet), ETA computed at 40 km/h

If no ambulance is free, the case is still registered and staff is notified

🗺️ Live Ambulance Tracking

Public tracking page (/track/<code>) — per-case Leaflet map, 🚑 marker moves in real time, ETA countdown

Admin fleet view (/admin/track) — all 10 ambulances on one live map + status table, auto-refresh every 2 s

Dispatch simulation: to_patient → to_hospital → arrived with interpolated positions

🏥 5 Simulated Hospitals (Khairpur, Sindh)

Khairpur Medical Complex (KMC), Civil Hospital Khairpur, Pir Abdul Qadir Shah Jilani Institute, Lady Dufferin Hospital Khairpur, Khairpur Emergency Care Center

👥 Portals

Role

Access

Features

Admin

/admin/dashboard

Live stats, case management, beds/doctors/ambulances tabs, live fleet map

Doctor

/doctor/...

Assigned patients list, availability, live tracking

Ambulance

/ambulance/...

Unit status, current assignment, position updates

Staff Login

/login

Local-only (no public button by design)

🛠️ Tech Stack

Backend: Python 3 · Flask · Flask-SQLAlchemy · SQLite · Werkzeug (password hashing)

Frontend: Bootstrap 5 · Bootstrap Icons · Leaflet.js (maps) · Vanilla JS · Poppins/Montserrat fonts

Styling: Custom theme (navy #1F3971 / red #e53935 / yellow #FFAE27), fully responsive (360 px → desktop)

📁 Project Structure

medcare-emergency/
├── app.py                      # Flask app: models, routes, APIs, allocation logic, seeding
├── instance/
│   └── medcare_emergency.db     # SQLite database (auto-created on first run)
├── static/
│   ├── css/style.css            # Full responsive theme
│   └── img/                     # logo101.png, doc101.png
├── templates/
│   ├── base.html                # Base layout (blocks: title, extra_css, body, extra_js)
│   ├── index.html               # Homepage: hero, AI assistant bottom bar + full-screen chat
│   ├── request_help.html        # Emergency request form
│   ├── track.html               # Per-case live ambulance tracking map
│   ├── login.html               # Staff login (direct URL only)
│   └── admin/
│       ├── _nav.html            # Admin navbar
│       ├── dashboard.html       # Stats & cases
│       ├── track.html           # Live fleet map (all ambulances)
│       └── resources.html       # Beds / doctors / ambulances management
└── README.md

⚡ Quick Start

# 1. Clone the repository
git clone https://github.com/<your-username>/medcare-emergency.git
cd medcare-emergency

# 2. Create & activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Install dependencies
pip install flask flask-sqlalchemy

# 4. Run the app (database is created & seeded automatically)
python app.py

# 5. Open in browser
# http://127.0.0.1:5000

The first run seeds: 1 admin, 5 doctors, 10 ambulances (Unit A001–A010), 8 beds, 5 hospitals and 2 demo cases — all located in Khairpur (27.53°N, 68.76°E).

🔑 Demo Credentials

Role

Username

Password

Admin

admin

admin123

Doctor

drsara (Dr. Sara Ahmed)

doctor123

Ambulance

amb1 (Unit A001)

amb123

(Other doctors: drbilal, drfatima, drusman, drayesha · other units: amb2–amb10)

🔌 API Endpoints

Method

Endpoint

Description

GET

/api/nearby-hospitals?lat=&lng=

3 nearest hospitals with distance, ICU/ER bed counts

GET

/api/ambulance-status

Fleet summary: available / on-the-way / occupied

POST

/api/create-request

JSON body → creates case + auto-allocates bed, doctor, ambulance; returns case code, ETA, track URL

GET

/api/track/<case_code>

Live position of assigned ambulance + ETA

GET

/api/ambulances-live

All ambulance positions (admin fleet map)

Example: create a request

curl -X POST http://127.0.0.1:5000/api/create-request \
  -H "Content-Type: application/json" \
  -d '{
    "patient_name": "Ahmed Raza",
    "age": 45,
    "condition": "Chest pain, possible heart attack",
    "priority": "Critical",
    "lat": 27.5320,
    "lng": 68.7590,
    "needs_ambulance": true
  }'

🧠 How Auto-Allocation Works

Bed — priority maps to an ordered bed-type preference (Critical: ICU → Emergency → Isolation → General, etc.); first free bed of the preferred type is reserved.

Doctor — the patient's condition text is keyword-matched against specialties (cardiology, orthopedics, pediatrics …); a matching available doctor is assigned.

Ambulance — Haversine distance from the patient to every available unit; the nearest one within 20 km is dispatched, with ETA = distance ÷ 40 km/h. The unit then simulates its journey (to_patient → to_hospital → arrived) with interpolated coordinates for live map tracking.

⚠️ Notes

This is a hackathon demo — all hospitals, staff and ambulance positions are simulated; not for clinical use.

To reset the database: stop the server, delete instance/medcare_emergency.db, and run python app.py again.

Staff login is intentionally hidden from public navigation — access it directly at /login.

📄 License

MIT — free to use and modify.

Powered by Musafir DevsOpenHack26 · Team HT-03
