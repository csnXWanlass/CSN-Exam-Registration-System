# libraries
from flask import render_template, request, jsonify, session, redirect, url_for
from pydantic import ValidationError
from functools import wraps # adds a wrapper so we can redirect if not logged in
from sqlalchemy import func, and_
# import secrets -- UNUSED

# project files
from project import create_app, db  # call create_app funct and db obj from project/__init__.py
from project.models import Campus, Rooms, Users, Exams, Sessions, Registrations
from schemas_auth import UserRegister, UserLogin, TokenResponse


app = create_app()

# Login-checking function
def login_required(view):
    # "view" is chosen because flask calls the route functions "view" functions
    # 
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:  # if the user ID is not in a session cookie
            return redirect(url_for('Index'))  # redirect home
        return view(*args, **kwargs)
    return wrapped

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
@login_required # redirect to home page to login and register
def exam_selection():
    # creates an SQL Alchemy query to run
    query = (
        db.select(
            # select session IDs & registration counts
            Sessions,
            func.count(Registrations.session_id).label('taken'),
        )
        .outerjoin(
            Registrations,
            and_(
                Registrations.session_id == Sessions.session_id,
                Registrations.status == 'Active',
            ),
        )
    .group_by(Sessions.session_id)
    # filter out results with 20 registrations or more (can't register what you can't see)
    .having(func.count(Registrations.session_id) < Sessions.capacity)
    )
    rows = db.session.execute(query).all()  # .all makes a list of ordered pairs (session_id, taken)
    return render_template('exams.html', rows=rows)


    
# REGISTRATION IS NOT DONE
# @app.route('/exams', methods=['POST'])
# @login_required
# def exam_registration():
#     # read session ID
#     data = request.get_json
#     user_id = session['user_id']


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

