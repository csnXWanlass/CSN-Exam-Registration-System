
# libraries
from flask import render_template, request, jsonify, session, redirect, url_for
# CHANGED: removed "from flask_login import current_user". Nothing used it (login runs on Flask's session).
from pydantic import ValidationError
from functools import wraps # adds a wrapper so we can redirect if not logged in
from sqlalchemy import func, and_
from sqlalchemy.exc import SQLAlchemyError
from datetime import date   # used to hide sessions whose date has already passed
# import secrets -- UNUSED
 
# project files
from project import create_app, db  # call create_app funct and db obj from project/__init__.py
# CHANGED: added RegistrationActivity (the history log used by the faculty Activity panel)
from project.models import Campus, Rooms, Users, Exams, Sessions, Registrations, RegistrationActivity
from schemas_auth import UserRegister, UserLogin, TokenResponse
 
from helpers import get_current_user, parse_date, login_required, role_required
 
 
app = create_app()
 
# A context processor runs before every template is rendered. Whatever dictionary it
# returns becomes available as variables in ALL templates (base.html, exams.html, etc.),
# so we don't have to pass the user into each page by hand.
@app.context_processor
def inject_nav_user():
    # get_current_user() (from helpers.py) reads the user_id from the session cookie and
    # loads that user's row from the database. It returns None if nobody is logged in.
    # In templates this is available as `nav_user`, e.g. {{ nav_user.role }}.
    return {'nav_user': get_current_user()}
 
 
# flask.route: connects url to a function that will handle requests to that url
@app.route('/', methods=['GET'])
def Index():
    # CHANGED: removed the two debug print() lines (SELECT DATABASE() and DESCRIBE exam_sessions).
    # They ran a database query on every home page load, and the page crashed if MySQL was down.
    return render_template('index.html')
 
@app.route('/about', methods=['GET'])
def about_page():
    return jsonify({'message': 'About!'})
 
@app.route('/contact', methods=['GET'])
def contact_page():
    return jsonify({'message': 'Contact!'})
 
 
 
# THIS LOGIN/REGISTRATION PAGES & FUNCTIONS ARE VERY VIBE-CODED, VALIDATE US!!!!
# Login page is a GET request, so it will return the login.html template
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')
 
 
#Login page is a POST request, so it will validate the data and log the user in.
@app.route('/login', methods=['POST'])
def login():
    try:
        # makes sure email and password are valid, returns a 400 error if not
        data = UserLogin.model_validate(request.get_json())
    except ValidationError as e:
        return jsonify(e.errors(include_context=False)), 400
 
    # searches for user in the database
    user = db.session.scalar(db.select(Users).filter_by(email=data.email))
    # if the user is not found or the password is incorrect, return a 401 error
    if not user or user.password != data.password:
        return jsonify(error="Incorrect email or password"), 401
 
    session['user_id'] = user.user_id  # stores the user_id in the session cookie, which is used to track the logged-in user
    return jsonify(message="Logged in"), 200
 
 
 
 
@app.route('/logout')
def logout():
    session.clear()  # Clear session cookie
    return redirect(url_for('Index'))  # redirect to the index page after logout
 
 
 
 
@app.route('/register', methods=['GET'])
def register_page():
    return render_template('register.html')
 
 
@app.route("/register", methods=['POST'])
def register():
    try:
        data = UserRegister.model_validate(request.get_json())
    # pydantic: ValidationError is raised when the data does not match the model's schema
    except ValidationError as e:
        return jsonify(e.errors(include_context=False)), 400
 
    if db.session.scalar(db.select(Users).filter_by(email=data.email)):
        return jsonify(error="That email is already registered"), 409
 
 
    # unused variable
    # student_id = data.email.split("@")[0]           # the 10 digits before @student.csn.edu
 
    # CHANGED: pass the role worked out from the email (data.role in schemas_auth.py).
    # Before, role was never set, so every new account got the database default, "Student",
    # even with a @csn.edu faculty address.
    # NOTE: this lets anyone with an @csn.edu address sign up as Faculty. If you'd rather create
    # faculty accounts yourself in MySQL, use role='Student' here instead of data.role.
    user = Users(first_name=data.first_name, last_name=data.last_name, email=data.email, 
                 password=data.password, role=data.role)
    db.session.add(user)
    db.session.commit()
    return jsonify(message="Account created"), 201
 
 
 
# Exam Registration pages
@app.route('/exams', methods=['GET'])
@login_required  # redirect to home page to login and register
def exam_selection():
    # CHECK SITE SESSION #
    user = get_current_user()
    if user is None:
        session.clear()
        return redirect(url_for('Index'))
 
    # `user` was loaded above by get_current_user(). Hiding the nav link only hides the
    # button; anyone can still type /exams into the address bar. This check runs on the
    # server, so it actually keeps faculty out of the student registration page.
    if user.role != 'Student':
        # send non-students to the home page instead of showing the exam list
        return redirect(url_for('Index'))
 
    user_id = user.user_id
 
    # passes whatever active registrations the user has on to the site
    # enables "You're already registered" button.
    registered_ids = set(db.session.scalars(
        db.select(Registrations.session_id).where(
            Registrations.student_id == user_id,
            Registrations.status != 'Cancelled',
        )
    ).all())
 
    # creates an query to be executed below
    query = (
        db.select(
            # select session, exam, room, campus, proctor objects & seat count
            Sessions,
            Exams,
            Rooms,
            Campus,
            Users,
            func.count(Registrations.session_id).label('taken'),
        )
        .select_from(Sessions)
        .join(Exams, Exams.exam_id == Sessions.exam_id)
        .join(Rooms, Rooms.room_id == Sessions.room_id)
        .join(Campus, Campus.campus_id == Rooms.campus_id)
        .join(Users, Users.user_id == Sessions.proctor_id)
        .outerjoin(
            Registrations,
            and_(
                Registrations.session_id == Sessions.session_id,
                Registrations.status == 'Active',
            ),
        )
        # NEW: only list sessions students can still register for: today or later, and not
        # cancelled or completed. Before, past and cancelled sessions were listed too.
        .where(
            Sessions.session_date >= date.today(),
            Sessions.status == 'Active',
        )
        .group_by(Sessions.session_id)
        .order_by(Sessions.session_date, Sessions.session_time)   # NEW: soonest first
    )
    # returns a 6-element list of tuples with full rows as object elements, count at the end.
    # objects can be unpacked in html thx to flask integrating with Jinja2
    rows = db.session.execute(query).all()
    return render_template('exams.html', rows=rows, registered_ids=registered_ids)
 
    
@app.route('/exams', methods=['POST'])
@login_required  # redirect to home page to login and register
def exam_registration():
    # IMPORTANT: all SQL Alchemy queries begin a transaction, which must be later committed
    
    max_exams = 3  # max number of exams a student can register for
 
    # helper: rollback table updates then build a json error response.
    def fail(message, error_code):
        db.session.rollback()  # End the transaction and release row lock
        return jsonify(error=message), error_code
 
    # flask: get user selection from browser, return data as a py dictionary
    data = request.get_json(silent=True) or {}
    try:
        # Try and extract exam_sessions.session_id from the dictionary
        session_id = int(data.get('session_id'))
    except (TypeError, ValueError):
        # Catch error if data is not an integer or is None.
        return fail('Invalid exam session.', 400)
 
    ## BEGIN TRANSACTION ##
 
    # CHECK IF SESSION EXISTS #
    # Lock the session row so two students can't take the last seat at the same time
    exam_session = db.session.execute(  # Lock lasts until commit() or rollback()
        db.select(Sessions)
        .where(Sessions.session_id == session_id)
        .with_for_update()  # MySQL's FOR UPDATE record lock.
    ).scalar_one_or_none()  # return a single Sessions object as exam_session if found
    if exam_session is None:
        return fail('Session not found.', 404)
 
    # NEW: CHECK THE SESSION IS STILL OPEN #
    # The exam list hides past and cancelled sessions, but someone could still send the
    # request directly, so the server checks too.
    if exam_session.status != 'Active' or exam_session.session_date < date.today():
        return fail('This session is no longer open for registration.', 409)
 
    # CHECK SITE SESSION #
    user = get_current_user()
    if user is None:
        session.clear()
        return fail('Your session expired. Please log in again.', 401)
    
    # CHECK IF STUDENT #
    # grab user_id from flask's session cookie & matches it w/database
    user = db.session.get(Users, int(session['user_id']))
    if user.role != 'Student':  # block faculty registration
        return fail('Only students can register for exams.', 403)
 
 
    # CHECK IF ALREADY REGISTERED #
    # Return a Registrations obj or None if nothing matches
    existing = db.session.execute(
        db.select(Registrations).where(
            Registrations.student_id == user.user_id,
            Registrations.session_id == session_id,
        )
    ).scalar_one_or_none()
    # checks if existing registration exists and is not cancelled.
    if existing and existing.status != 'Cancelled':
        return fail('You are already registered for this session.', 409)
 
    # 3-EXAM LIMIT #
    # return number of user's active registrations
    active_count = db.session.scalar(
        db.select(func.count()).select_from(Registrations).where(
            Registrations.student_id == user.user_id,
            Registrations.status == 'Active',
        )
    )
    # check against max_exams constant
    if active_count >= max_exams:
        return fail(f'You can register for at most {max_exams} exams.', 409)
 
    # CHECK CAPACITY #
    # return number of total active registrations for session
    taken = db.session.scalar(
        db.select(func.count()).select_from(Registrations).where(
            Registrations.session_id == session_id,
            Registrations.status == 'Active',
        )
    )
    # check result against capacity
    if taken >= exam_session.capacity:
        return fail('This session is full.', 409)   # CHANGED: added "return". Without it the error was thrown away and a full session still accepted the registration.
 
    # ADD/REACTIVATE REGISTRATION #
    if existing:
        # SQL Alchemy will automatically apply this change to all records in existing variable
        existing.status = 'Active'
    else:
        db.session.add(Registrations(student_id=user.user_id, session_id=session_id))
 
    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        # CHANGED: only show the message when it comes from one of your database rules (MySQL
        # error 1644, raised by the validate_registration procedure). Any other database error
        # gets a generic message so internal details aren't sent to the browser. getattr also
        # stops a crash when the error has no .orig.
        orig = getattr(e, 'orig', None)
        if orig is not None and len(orig.args) > 1 and orig.args[0] == 1644:
            return jsonify(error=orig.args[1]), 409
        return jsonify(error='Could not complete the registration. Please try again.'), 500
 
    ## END TRANSACION ##
    
    return jsonify(message='Registered!'), 201
 
 
# Reservation history page. The page's JavaScript fills itself in
# from the /api/registrations route in project/api.py.
@app.route('/history', methods=['GET'])
@role_required('Student', page=True)   # CHANGED: page=True (before, the True was read as a role name)
def history_page():
    return render_template('history.html')
 
 
 
# Faculty Reports page: the UPCOMING exam sessions the logged-in faculty member is
# proctoring, laid out like the student exams page but with no Register button.
# Each session has an Activity panel listing who registered, who cancelled, and the
# full history of register and cancel events.
@app.route('/reports', methods=['GET'])
@role_required('Faculty', page=True)   # students are sent back to the home page
def reports_page():
    user = get_current_user()   # the logged-in faculty member (role_required already checked the login)
 
    query = (
        db.select(
            # session, exam, room and campus objects, plus the number of seats taken
            Sessions, Exams, Rooms, Campus,
            func.count(Registrations.session_id).label('taken'),
        )
        .select_from(Sessions)
        .join(Exams, Exams.exam_id == Sessions.exam_id)
        .join(Rooms, Rooms.room_id == Sessions.room_id)
        .join(Campus, Campus.campus_id == Rooms.campus_id)
        .outerjoin(
            Registrations,
            and_(
                Registrations.session_id == Sessions.session_id,
                Registrations.status == 'Active',   # only active registrations count as taken seats
            ),
        )
        .where(
            Sessions.proctor_id == user.user_id,           # only sessions this faculty member proctors
            Sessions.session_date >= date.today(),         # upcoming only: today or later
        )
        .group_by(Sessions.session_id)
        .order_by(Sessions.session_date, Sessions.session_time)   # soonest first
    )
    rows = db.session.execute(query).all()
 
    # ACTIVITY #
    # Build {session_id: {'active': [...], 'cancelled': [...], 'history': [...]}} for this
    # proctor's sessions only. Each list holds (student, record) pairs that the template
    # turns into table rows.
    session_ids = [row[0].session_id for row in rows]   # row[0] is the Sessions object
    activity = {sid: {'active': [], 'cancelled': [], 'history': []} for sid in session_ids}
 
    if session_ids:   # skip the queries if the proctor has no sessions
        # Current status lists, from the registrations table
        activity_rows = db.session.execute(
            db.select(Registrations, Users)
            .select_from(Registrations)
            .join(Users, Users.user_id == Registrations.student_id)   # Users here is the student
            .where(Registrations.session_id.in_(session_ids))
            # most recently cancelled first; active rows (no cancelled_at) then sort by when they registered
            .order_by(Registrations.cancelled_at.desc(), Registrations.registered_at)
        ).all()
 
        for registration, student in activity_rows:
            if registration.status == 'Active':
                activity[registration.session_id]['active'].append((student, registration))
            elif registration.status == 'Cancelled':
                activity[registration.session_id]['cancelled'].append((student, registration))
            # 'Complete' registrations are not shown in either list
 
        # Full history, from the registration_activity log table: every register and
        # cancel event, newest first
        history_rows = db.session.execute(
            db.select(RegistrationActivity, Users)
            .select_from(RegistrationActivity)
            .join(Users, Users.user_id == RegistrationActivity.student_id)
            .where(RegistrationActivity.session_id.in_(session_ids))
            .order_by(RegistrationActivity.occurred_at.desc(), RegistrationActivity.activity_id.desc())
        ).all()
 
        for event, student in history_rows:
            activity[event.session_id]['history'].append((student, event))
 
    # the Reports page uses the same template that holds the Activity button
    return render_template('faculty_sessions.html', rows=rows, activity=activity)
 
@app.route('/createsession', methods=['GET'])
@role_required('Faculty', page=True)   # CHANGED: page=True
def create_session_page():
    return render_template('create_session_test.html')
 
 
if __name__ == '__main__':
    app.run(debug=True)
 
# CHANGED: removed the block of FastAPI notes that was at the bottom of the file. It was an
# unused string and didn't describe anything this app does.