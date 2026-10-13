from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import math

app = Flask(__name__)
app.secret_key = 'medcare-emergency-ht03-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medcare_emergency.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

TOTAL_AMBULANCES = 10

# ===================== MODELS =====================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, doctor, ambulance
    name = db.Column(db.String(120), nullable=False)
    specialty = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), default='Available')
    phone = db.Column(db.String(20), nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    vehicle_type = db.Column(db.String(20), nullable=True)  # ALS / BLS
    vehicle_id = db.Column(db.String(20), nullable=True)

class Bed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bed_code = db.Column(db.String(20), unique=True, nullable=False)
    bed_type = db.Column(db.String(30), nullable=False)  # ICU, Emergency, General, Isolation
    status = db.Column(db.String(20), default='Available')
    assigned_case_id = db.Column(db.Integer, db.ForeignKey('case.id'), nullable=True)

class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    case_code = db.Column(db.String(20), unique=True, nullable=False)
    patient_name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    priority = db.Column(db.String(20), nullable=False)  # Critical, High, Medium, Low
    condition = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Active')  # Active, Closed, Incoming, Dispatched
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    patient_lat = db.Column(db.Float, nullable=True)
    patient_lng = db.Column(db.Float, nullable=True)
    patient_address = db.Column(db.String(255), nullable=True)
    assigned_doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_bed_id = db.Column(db.Integer, db.ForeignKey('bed.id'), nullable=True)
    assigned_ambulance_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    hospital_name = db.Column(db.String(120), nullable=True)
    needs_ambulance = db.Column(db.Boolean, default=False)
    dispatched_at = db.Column(db.DateTime, nullable=True)

    doctor = db.relationship('User', foreign_keys=[assigned_doctor_id], backref='assigned_cases')
    ambulance = db.relationship('User', foreign_keys=[assigned_ambulance_id], backref='ambulance_cases')
    bed = db.relationship('Bed', foreign_keys=[assigned_bed_id], backref='case')

# ===================== HOSPITALS (simulated network) =====================
# All hospitals & ambulances are located in Khairpur, Sindh, Pakistan (approx 27.53N, 68.76E)
HOSPITALS = [
    {'code': 'H1', 'name': 'Khairpur Medical Complex (KMC)',     'lat': 27.5290, 'lng': 68.7580, 'phone': '+92 300 1234567', 'icu_beds': 4, 'er_beds': 6},
    {'code': 'H2', 'name': 'Civil Hospital Khairpur',           'lat': 27.5360, 'lng': 68.7720, 'phone': '+92 300 7654321', 'icu_beds': 2, 'er_beds': 5},
    {'code': 'H3', 'name': 'Pir Abdul Qadir Shah Jilani Institute', 'lat': 27.5450, 'lng': 68.7480, 'phone': '+92 300 2223334', 'icu_beds': 1, 'er_beds': 3},
    {'code': 'H4', 'name': 'Lady Dufferin Hospital Khairpur',    'lat': 27.5180, 'lng': 68.7650, 'phone': '+92 300 5556667', 'icu_beds': 3, 'er_beds': 4},
    {'code': 'H5', 'name': 'Khairpur Emergency Care Center',     'lat': 27.5240, 'lng': 68.7830, 'phone': '+92 300 8889990', 'icu_beds': 2, 'er_beds': 2},
]
MAX_AMBULANCE_RANGE_KM = 20
AMBULANCE_SPEED_KMH = 40.0

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ===================== AUTH HELPERS =====================

def login_required(role=None):
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login first.', 'warning')
                return redirect(url_for('login'))
            if role and session.get('role') != role and session.get('role') != 'admin':
                flash('Access denied for your role.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ===================== SMART ALLOCATION =====================

CONDITION_SPECIALTY_MAP = {
    'cardiac': 'Cardiology', 'chest': 'Cardiology', 'heart': 'Cardiology',
    'fracture': 'Orthopedics', 'bone': 'Orthopedics', 'accident': 'Orthopedics',
    'child': 'Pediatrics', 'baby': 'Pediatrics', 'kid': 'Pediatrics',
    'surgery': 'General Surgery', 'wound': 'General Surgery', 'bleed': 'General Surgery',
}

def guess_specialty(condition):
    text = (condition or '').lower()
    for keyword, spec in CONDITION_SPECIALTY_MAP.items():
        if keyword in text:
            return spec
    return 'Emergency Medicine'

def available_ambulances():
    return User.query.filter_by(role='ambulance', status='Available').all()

def nearest_ambulance(lat, lng):
    """Nearest available ambulance within 20 km, or (None, None)."""
    ambs = []
    for amb in available_ambulances():
        if amb.lat and amb.lng:
            d = haversine(lat, lng, amb.lat, amb.lng)
            if d <= MAX_AMBULANCE_RANGE_KM:
                ambs.append((d, amb))
    if not ambs:
        return None, None
    ambs.sort(key=lambda x: x[0])
    return ambs[0][1], ambs[0][0]

def auto_allocate(c, use_ambulance=True):
    """Assign bed + doctor + nearest ambulance (within 20 km). Returns summary dict."""
    summary = {'bed': None, 'doctor': None, 'ambulance': None,
               'hospital_name': c.hospital_name,
               'ambulance_eta_min': None, 'ambulances_available': len(available_ambulances())}

    # --- Bed by priority ---
    preferred = {
        'Critical': ['ICU', 'Emergency', 'Isolation', 'General'],
        'High': ['Emergency', 'ICU', 'General', 'Isolation'],
        'Medium': ['General', 'Emergency', 'Isolation', 'ICU'],
        'Low': ['General', 'Emergency', 'Isolation', 'ICU'],
    }
    chosen_bed = None
    for t in preferred.get(c.priority, ['General']):
        chosen_bed = Bed.query.filter_by(status='Available', bed_type=t).first()
        if chosen_bed:
            break
    if not chosen_bed:
        chosen_bed = Bed.query.filter_by(status='Available').first()

    # --- Doctor: match specialty to condition keywords ---
    spec = guess_specialty(c.condition)
    chosen_doc = User.query.filter(
        User.role == 'doctor', User.status == 'Available',
        User.specialty == spec).first()
    if not chosen_doc:
        chosen_doc = User.query.filter_by(role='doctor', status='Available').first()
    if not chosen_doc and c.priority == 'Critical':
        chosen_doc = User.query.filter_by(role='doctor', status='On-call').first()

    # --- Ambulance: nearest available unit within 20 km of patient ---
    chosen_amb, dist = None, None
    if use_ambulance and c.patient_lat is not None and c.patient_lng is not None:
        chosen_amb, dist = nearest_ambulance(c.patient_lat, c.patient_lng)

    # --- Apply (all statuses stay in sync) ---
    if chosen_bed:
        chosen_bed.status = 'Occupied'
        chosen_bed.assigned_case_id = c.id
        c.assigned_bed_id = chosen_bed.id
        summary['bed'] = chosen_bed.bed_code
    if chosen_doc:
        chosen_doc.status = 'Busy'
        c.assigned_doctor_id = chosen_doc.id
        summary['doctor'] = chosen_doc.name
    if chosen_amb:
        chosen_amb.status = 'On the way'
        c.assigned_ambulance_id = chosen_amb.id
        c.dispatched_at = datetime.utcnow()
        c.status = 'Dispatched'
        summary['ambulance'] = chosen_amb.vehicle_id or chosen_amb.name
        # ETA: ambulance departs from the chosen hospital -> patient
        h = next((x for x in HOSPITALS if x['name'] == c.hospital_name), None)
        if h is None and c.patient_lat is not None:
            h = min(HOSPITALS, key=lambda x: haversine(c.patient_lat, c.patient_lng, x['lat'], x['lng']))
        if h:
            d1 = haversine(h['lat'], h['lng'], c.patient_lat, c.patient_lng) if c.patient_lat is not None else None
            if d1 is not None:
                summary['ambulance_eta_min'] = max(round(d1 / AMBULANCE_SPEED_KMH * 60), 1)
    elif c.status == 'Incoming':
        c.status = 'Active'
    summary['ambulances_available'] = len(available_ambulances())
    return summary

# ---------- DISPATCH POSITION (shared by track + admin live map) ----------

def _interp(a, b, t):
    return a + (b - a) * t

def dispatch_state(c):
    """Live position/phase/eta of the ambulance assigned to case c, or None.

    The ambulance departs FROM the assigned hospital, drives to the
    patient's shared location, then brings the patient back to the
    same hospital.
    """
    if not c.assigned_ambulance_id or not c.dispatched_at:
        return None
    amb = User.query.get(c.assigned_ambulance_id)
    if not amb or c.patient_lat is None or c.patient_lng is None:
        return None

    # ---- departure point = the chosen hospital ----
    if c.hospital_name:
        h = next((x for x in HOSPITALS if x['name'] == c.hospital_name), None)
    else:
        h = None
    if h is None:
        # fallback: nearest hospital to the patient
        h = min(HOSPITALS, key=lambda x: haversine(c.patient_lat, c.patient_lng, x['lat'], x['lng']))

    start_lat, start_lng = h['lat'], h['lng']          # ambulance starts here
    pat_lat, pat_lng = c.patient_lat, c.patient_lng    # shared location
    hosp_lat, hosp_lng = h['lat'], h['lng']            # final destination (same hospital)

    d1 = haversine(start_lat, start_lng, pat_lat, pat_lng)   # hospital -> patient
    d2 = haversine(pat_lat, pat_lng, hosp_lat, hosp_lng)     # patient -> hospital
    total_km = d1 + d2

    elapsed_h = (datetime.utcnow() - c.dispatched_at).total_seconds() / 3600.0
    km_done = elapsed_h * AMBULANCE_SPEED_KMH

    pos = {'lat': start_lat, 'lng': start_lng}
    phase, eta_min, eta_to_patient = 'to_patient', None, None
    if km_done <= d1 and d1 > 0:
        t = km_done / d1
        pos = {'lat': _interp(start_lat, pat_lat, t), 'lng': _interp(start_lng, pat_lng, t)}
        eta_to_patient = max(round((d1 - km_done) / AMBULANCE_SPEED_KMH * 60), 1)
        eta_min = round((d1 - km_done + d2) / AMBULANCE_SPEED_KMH * 60)
    elif km_done <= total_km:
        t = (km_done - d1) / d2 if d2 > 0 else 1
        pos = {'lat': _interp(pat_lat, hosp_lat, t), 'lng': _interp(pat_lng, hosp_lng, t)}
        phase = 'to_hospital'
        eta_min = max(round((total_km - km_done) / AMBULANCE_SPEED_KMH * 60), 1)
    else:
        pos = {'lat': hosp_lat, 'lng': hosp_lng}
        phase = 'arrived'
        eta_min = 0
    return {
        'ambulance': amb.vehicle_id or amb.name,
        'position': pos,
        'phase': phase,
        'eta_min': eta_min,
        'eta_to_patient_min': eta_to_patient,
        'start': {'lat': start_lat, 'lng': start_lng, 'name': h['name']},
        'patient': {'lat': pat_lat, 'lng': pat_lng, 'address': c.patient_address},
        'hospital': {'lat': hosp_lat, 'lng': hosp_lng, 'name': h['name']},
    }

# ===================== ROUTES =====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['name'] = user.name
            session['role'] = user.role
            flash(f'Welcome back, {user.name}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            if user.role == 'doctor':
                return redirect(url_for('doctor_dashboard'))
            if user.role == 'ambulance':
                return redirect(url_for('ambulance_dashboard'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

# ---------- PUBLIC AI ASSISTANT APIs ----------

@app.route('/api/nearby-hospitals')
def nearby_hospitals():
    try:
        lat = float(request.args.get('lat', HOSPITALS[0]['lat']))
        lng = float(request.args.get('lng', HOSPITALS[0]['lng']))
    except ValueError:
        return jsonify({'error': 'invalid coordinates'}), 400
    ranked = sorted(
        (dict(h, distance_km=round(haversine(lat, lng, h['lat'], h['lng']), 1)) for h in HOSPITALS),
        key=lambda h: h['distance_km'])
    return jsonify({'hospitals': ranked[:3]})

@app.route('/api/ambulance-status')
def ambulance_status():
    """Live ambulance availability (for AI assistant)."""
    avail = available_ambulances()
    on_way = User.query.filter_by(role='ambulance', status='On the way').count()
    occupied = User.query.filter_by(role='ambulance', status='Occupied').count()
    return jsonify({'total': TOTAL_AMBULANCES, 'available': len(avail),
                    'on_the_way': on_way, 'occupied': occupied})

@app.route('/api/create-request', methods=['POST'])
def create_request():
    """Called by the AI assistant: creates case + auto-allocates resources."""
    data = request.get_json(silent=True) or request.form
    required = ['patient_name', 'age', 'condition', 'priority']
    if not all(data.get(k) for k in required):
        return jsonify({'error': 'missing fields'}), 400
    try:
        lat = float(data['lat']) if data.get('lat') else 27.5300
        lng = float(data['lng']) if data.get('lng') else 68.7600
        age = int(data['age'])
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid values'}), 400

    last = Case.query.order_by(Case.id.desc()).first()
    code = f'C{(last.id + 1) if last else 1:03d}'
    needs_amb = str(data.get('needs_ambulance', 'yes')).lower() in ('yes', 'true', '1')

    c = Case(
        case_code=code,
        patient_name=data['patient_name'].strip(),
        age=age,
        priority=data['priority'],
        condition=data['condition'],
        status='Incoming',
        patient_address=data.get('address'),
        patient_lat=lat, patient_lng=lng,
        hospital_name=data.get('hospital_name'),
        needs_ambulance=needs_amb,
    )
    db.session.add(c)
    db.session.flush()
    summary = auto_allocate(c, use_ambulance=needs_amb)
    db.session.commit()
    return jsonify({'case_code': code, 'allocation': summary,
                    'ambulance_found': bool(summary['ambulance']),
                    'track_url': url_for('track', case_code=code)})

# ---------- LIVE TRACKING (public, per case) ----------

@app.route('/track/<case_code>')
def track(case_code):
    c = Case.query.filter_by(case_code=case_code).first_or_404()
    return render_template('track.html', case=c)

@app.route('/api/track/<case_code>')
def track_api(case_code):
    c = Case.query.filter_by(case_code=case_code).first_or_404()
    state = dispatch_state(c)
    amb = c.ambulance
    result = {'dispatched': False, 'case': {
        'code': c.case_code, 'status': c.status, 'priority': c.priority,
        'patient_lat': c.patient_lat, 'patient_lng': c.patient_lng,
        'hospital': c.hospital_name,
        'doctor': c.doctor.name if c.doctor else None,
        'bed': c.bed.bed_code if c.bed else None,
        'ambulance': amb.vehicle_id if amb else None}}
    if state:
        result['dispatched'] = True
        result.update(state)
        if state['phase'] == 'arrived' and c.status != 'Active':
            c.status = 'Active'
            db.session.commit()
            result['case']['status'] = 'Active'
    return jsonify(result)

# ---------- ADMIN/STAFF LIVE FLEET MAP ----------

@app.route('/admin/track')
def admin_track():
    # admin AND staff (doctors) can watch the live fleet
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))
    if session.get('role') not in ('admin', 'doctor'):
        flash('Access denied for your role.', 'danger')
        return redirect(url_for('index'))
    return render_template('admin/track.html')

@app.route('/api/ambulances-live')
def ambulances_live():
    """All ambulances with live positions + assigned case info (admin/staff map)."""
    ambs = User.query.filter_by(role='ambulance').all()
    out = []
    for amb in ambs:
        item = {
            'id': amb.id, 'unit': amb.vehicle_id or amb.name,
            'type': amb.vehicle_type, 'status': amb.status,
            'position': {'lat': amb.lat, 'lng': amb.lng},
            'case': None, 'eta_min': None, 'phase': None,
        }
        c = Case.query.filter_by(assigned_ambulance_id=amb.id).filter(
            Case.status.in_(['Dispatched', 'Active'])).order_by(Case.id.desc()).first()
        if c:
            state = dispatch_state(c)
            item['case'] = {'code': c.case_code, 'patient': c.patient_name,
                            'priority': c.priority, 'hospital': c.hospital_name,
                            'doctor': c.doctor.name if c.doctor else None,
                            'bed': c.bed.bed_code if c.bed else None}
            if state:
                item['position'] = state['position']
                item['eta_min'] = state['eta_min']
                item['phase'] = state['phase']
                item['patient'] = state['patient']
                item['hospital_pos'] = state['hospital']
        out.append(item)
    return jsonify({'ambulances': out,
                    'counts': {'total': len(ambs),
                               'available': sum(1 for a in ambs if a.status == 'Available'),
                               'on_the_way': sum(1 for a in ambs if a.status == 'On the way'),
                               'occupied': sum(1 for a in ambs if a.status == 'Occupied')}})

# ---------- ADMIN / STAFF MODULE ----------

@app.route('/admin')
@login_required(role='admin')
def admin_dashboard():
    active_cases = Case.query.filter(Case.status.in_(['Active', 'Dispatched'])).count()
    incoming = Case.query.filter_by(status='Incoming').count()
    free_beds = Bed.query.filter_by(status='Available').count()
    free_doctors = User.query.filter_by(role='doctor', status='Available').count()
    free_amb = User.query.filter_by(role='ambulance', status='Available').count()
    on_way_amb = User.query.filter_by(role='ambulance', status='On the way').count()
    recent = Case.query.filter(Case.status.in_(['Active', 'Incoming', 'Dispatched'])).order_by(Case.registered_at.desc()).limit(8).all()
    return render_template('admin/dashboard.html', active_cases=active_cases, incoming=incoming,
                           free_beds=free_beds, free_doctors=free_doctors, free_amb=free_amb,
                           on_way_amb=on_way_amb, recent=recent)

@app.route('/admin/cases', methods=['GET', 'POST'])
@login_required(role='admin')
def admin_cases():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            last = Case.query.order_by(Case.id.desc()).first()
            code = f'C{(last.id + 1) if last else 1:03d}'
            new_case = Case(case_code=code, patient_name=request.form['patient_name'],
                age=int(request.form['age']), priority=request.form['priority'],
                condition=request.form['condition'], status=request.form.get('status', 'Active'),
                patient_address=request.form.get('address'),
                patient_lat=float(request.form['lat']) if request.form.get('lat') else None,
                patient_lng=float(request.form['lng']) if request.form.get('lng') else None)
            db.session.add(new_case)
            db.session.commit()
            flash(f'Case {code} registered.', 'success')
        elif action == 'close':
            c = Case.query.get(int(request.form['case_id']))
            if c:
                if c.assigned_bed_id:
                    bed = Bed.query.get(c.assigned_bed_id)
                    if bed:
                        bed.status = 'Available'; bed.assigned_case_id = None
                if c.assigned_doctor_id:
                    doc = User.query.get(c.assigned_doctor_id)
                    if doc: doc.status = 'Available'
                if c.assigned_ambulance_id:
                    amb = User.query.get(c.assigned_ambulance_id)
                    if amb: amb.status = 'Available'
                c.status = 'Closed'
                db.session.commit()
                flash('Case closed and resources freed.', 'success')
        return redirect(url_for('admin_cases'))
    priority_filter = request.args.get('priority', 'all')
    q = Case.query.order_by(Case.registered_at.desc())
    if priority_filter != 'all':
        q = q.filter_by(priority=priority_filter)
    return render_template('admin/cases.html', cases=q.all(), priority_filter=priority_filter)

@app.route('/admin/resources')
@login_required(role='admin')
def admin_resources():
    return render_template('admin/resources.html', beds=Bed.query.all(),
        doctors=User.query.filter_by(role='doctor').all(),
        ambulances=User.query.filter_by(role='ambulance').all())

@app.route('/admin/resource/update', methods=['POST'])
@login_required(role='admin')
def update_resource():
    rtype, rid, status = request.form.get('type'), int(request.form.get('id')), request.form.get('status')
    obj = Bed.query.get(rid) if rtype == 'bed' else User.query.get(rid)
    if obj:
        obj.status = status
        if rtype == 'bed' and status == 'Available':
            obj.assigned_case_id = None
        db.session.commit()
    flash('Status updated.', 'success')
    return redirect(url_for('admin_resources'))

@app.route('/admin/allocate', methods=['GET', 'POST'])
@login_required(role='admin')
def admin_allocate():
    if request.method == 'POST':
        c = Case.query.get(int(request.form['case_id']))
        if not c:
            flash('Case not found.', 'danger')
            return redirect(url_for('admin_allocate'))
        summary = auto_allocate(c)
        db.session.commit()
        msg = f'Allocation applied for {c.case_code}.'
        if not summary['bed']: msg += ' No free bed available!'
        if not summary['doctor']: msg += ' No free doctor available!'
        if not summary['ambulance']: msg += ' No ambulance available in 20 km range!'
        flash(msg, 'success')
        return redirect(url_for('admin_allocate'))
    active = Case.query.filter(Case.status.in_(['Active', 'Incoming', 'Dispatched'])).order_by(Case.registered_at.desc()).all()
    return render_template('admin/allocate.html', cases=active)

# ---------- DOCTOR MODULE ----------

@app.route('/doctor')
@login_required(role='doctor')
def doctor_dashboard():
    user = User.query.get(session['user_id'])
    my_cases = Case.query.filter_by(assigned_doctor_id=user.id, status='Active').order_by(Case.registered_at.desc()).all()
    return render_template('doctor/dashboard.html', user=user, my_cases=my_cases)

@app.route('/doctor/patients')
@login_required(role='doctor')
def doctor_patients():
    user = User.query.get(session['user_id'])
    my_cases = Case.query.filter_by(assigned_doctor_id=user.id).order_by(Case.registered_at.desc()).all()
    return render_template('doctor/patients.html', user=user, my_cases=my_cases)

@app.route('/doctor/update-status', methods=['POST'])
@login_required(role='doctor')
def doctor_update_status():
    user = User.query.get(session['user_id'])
    user.status = request.form.get('status', 'Available')
    db.session.commit()
    flash('Your status updated.', 'success')
    return redirect(url_for('doctor_dashboard'))

# ---------- AMBULANCE MODULE ----------

@app.route('/ambulance')
@login_required(role='ambulance')
def ambulance_dashboard():
    user = User.query.get(session['user_id'])
    my_cases = Case.query.filter_by(assigned_ambulance_id=user.id).filter(Case.status.in_(['Active', 'Incoming', 'Dispatched'])).all()
    for c in my_cases:
        c.distance_km = round(haversine(user.lat, user.lng, c.patient_lat, c.patient_lng), 1) if (c.patient_lat and user.lat) else None
    return render_template('ambulance/dashboard.html', user=user, my_cases=my_cases)

@app.route('/ambulance/update-status', methods=['POST'])
@login_required(role='ambulance')
def ambulance_update_status():
    user = User.query.get(session['user_id'])
    user.status = request.form.get('status', 'Available')
    if request.form.get('lat') and request.form.get('lng'):
        user.lat = float(request.form['lat']); user.lng = float(request.form['lng'])
    db.session.commit()
    flash('Status / location updated.', 'success')
    return redirect(url_for('ambulance_dashboard'))

# ---------- PUBLIC EMERGENCY FORM ----------

@app.route('/request-help', methods=['GET', 'POST'])
def request_help():
    if request.method == 'POST':
        last = Case.query.order_by(Case.id.desc()).first()
        code = f'C{(last.id + 1) if last else 1:03d}'
        new_case = Case(case_code=code, patient_name=request.form['patient_name'],
            age=int(request.form['age']), priority=request.form.get('priority', 'High'),
            condition=request.form['condition'], status='Incoming',
            patient_address=request.form.get('address'),
            patient_lat=float(request.form['lat']) if request.form.get('lat') else 27.5300,
            patient_lng=float(request.form['lng']) if request.form.get('lng') else 68.7600)
        db.session.add(new_case)
        db.session.flush()
        summary = auto_allocate(new_case)
        db.session.commit()
        if summary['ambulance']:
            flash(f'Request {code} submitted. Ambulance {summary["ambulance"]} dispatched from {summary["hospital_name"] or "hospital"}!', 'success')
        else:
            flash(f'Request {code} submitted. NOTE: no ambulance currently available!', 'warning')
        return redirect(url_for('track', case_code=code))
    return render_template('request_help.html')

# ===================== SEED DATA =====================

def seed_data():
    if User.query.first():
        return
    db.session.add(User(username='admin', password_hash=generate_password_hash('admin123'),
                        role='admin', name='Admin Desk', status='Available'))
    doctors = [
        ('drsara', 'Dr. Sara Ahmed', 'Emergency Medicine'),
        ('drbilal', 'Dr. Bilal Khan', 'Cardiology'),
        ('drfatima', 'Dr. Fatima Raza', 'General Surgery'),
        ('drusman', 'Dr. Usman Ali', 'Orthopedics'),
        ('drayesha', 'Dr. Ayesha Malik', 'Pediatrics'),
    ]
    for uname, name, spec in doctors:
        db.session.add(User(username=uname, password_hash=generate_password_hash('doctor123'),
                            role='doctor', name=name, specialty=spec, status='Available'))
    # 10 ambulances spread around the Khairpur coverage area
    ambs = [
        ('amb1',  'Unit A001', 'ALS', 27.5350, 68.7600),
        ('amb2',  'Unit A002', 'BLS', 27.5250, 68.7400),
        ('amb3',  'Unit A003', 'ALS', 27.5400, 68.7700),
        ('amb4',  'Unit A004', 'BLS', 27.5200, 68.7550),
        ('amb5',  'Unit A005', 'ALS', 27.5500, 68.7800),
        ('amb6',  'Unit A006', 'BLS', 27.5100, 68.7450),
        ('amb7',  'Unit A007', 'ALS', 27.5450, 68.7350),
        ('amb8',  'Unit A008', 'BLS', 27.5150, 68.7850),
        ('amb9',  'Unit A009', 'ALS', 27.5550, 68.7500),
        ('amb10', 'Unit A010', 'BLS', 27.5050, 68.7650),
    ]
    for uname, vid, vtype, lat, lng in ambs:
        db.session.add(User(username=uname, password_hash=generate_password_hash('amb123'),
            role='ambulance', name=vid, vehicle_id=vid, vehicle_type=vtype,
            status='Available', lat=lat, lng=lng))
    for code, btype in [('B001', 'ICU'), ('B002', 'ICU'), ('B003', 'Emergency'), ('B004', 'Emergency'),
                        ('B005', 'General'), ('B006', 'General'), ('B007', 'General'), ('B008', 'Isolation')]:
        db.session.add(Bed(bed_code=code, bed_type=btype, status='Available'))
    db.session.add(Case(case_code='C001', patient_name='Imran Siddiqui', age=54, priority='High',
        condition='Chest pain, suspected cardiac event', status='Active',
        patient_address='Sir Syed Town, Khairpur', patient_lat=27.5320, patient_lng=68.7590))
    db.session.add(Case(case_code='C002', patient_name='Zainab Fatima', age=28, priority='Medium',
        condition='High fever and dehydration', status='Active',
        patient_address='Faiz Ganj Road, Khairpur', patient_lat=27.5410, patient_lng=68.7710))
    db.session.commit()
    print(f'Database seeded successfully with {TOTAL_AMBULANCES} ambulances.')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True, host='0.0.0.0', port=5000)