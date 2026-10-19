# libraries
from flask import render_template, request, jsonify, session, redirect, url_for
from flask_login import current_user
from pydantic import ValidationError
from functools import wraps # adds a wrapper so we can redirect if not logged in
from sqlalchemy import func, and_
# import secrets -- UNUSED

# project files
from project import create_app, db  # call create_app funct and db obj from project/__init__.py
from project.models import Campus, Rooms, Users, Exams, Sessions, Registrations
from schemas_auth import UserRegister, UserLogin, TokenResponse


app = create_app()
app.config['SQLALCHEMY_ECHO'] = True  # For debug, lets you see queries.


## HELPERS ##

# DECORATORS #
def login_required(view):  # Redirect home if not logged in
    # "view" is chosen because flask calls the route functions "view" functions
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:  # if the user ID is not in a session cookie
            # if it's because user session expired
            if request.method == 'POST':
                return jsonify(error='Session expired. Please log in again.'), 401
            return redirect(url_for('Index'))  # redirect home
        return view(*args, **kwargs)
    return wrapped

# FUNCTIONS #
def get_current_user():
    """Return the logged-in Users row, or None if there's no login or the cookie is stale."""
    user_id = session.get('user_id')
    if user_id is None:
        return None
    return db.session.get(Users, int(user_id))


# flask.route: connects url to a function that will handle requests to that url
@app.route('/', methods=['GET'])
def Index():
    print(db.session.scalar(db.text("SELECT DATABASE()")))
    print(db.session.execute(db.text("DESCRIBE exam_sessions")).all())
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

    student_id = data.email.split("@")[0]           # the 10 digits before @student.csn.edu

    user = Users(first_name=data.first_name, last_name=data.last_name, email=data.email, 
                 password=data.password)
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
        .group_by(Sessions.session_id)
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
        fail('This session is full.', 409)

    # ADD/REACTIVATE REGISTRATION #
    if existing:
        # SQL Alchemy will automatically apply this change to all records in existing variable
        existing.status = 'Active'
    else:
        db.session.add(Registrations(student_id=user.user_id, session_id=session_id))

    db.session.commit()

    ## END TRANSACION ##
    
    return jsonify(message='Registered!'), 201


if __name__ == '__main__':
    app.run(debug=True)

""""
Syntax:

@app.get("/") Tells FastAPI that this function is the handler for GET requests to the root URL ("/").
def login(): Defines a function named read_root that will be called when a GET request is

////////////////////////////////////////////////////////////////////////////////////////////////

Arguments: UserLogin: This is a Pydantic model that defines the expected structure of the request body for the login endpoint. It includes fields for email and password.
db: Session = Depends(get_db): This argument uses FastAPI's dependency injection system to provide a database session to the function. 
The get_db function is called to create a new session, and FastAPI ensures that the session is properly closed after the request is processed.




@app.route("/login", methods=['POST'])
def login(data: UserLogin, db: Session = Depends(db.session)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    #access_token = create_access_token(data={"sub": user.email}
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_name=user.name,
        user_email=user.email
    )
"""

