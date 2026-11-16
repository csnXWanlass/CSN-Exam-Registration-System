"""
project/api.py

JSON routes the site's JavaScript calls with fetch().

Sign-in works the same way as in app.py: the /login route saves the
user's ID in Flask's session cookie (session["user_id"]), and the routes
in this file read it back to find out who is asking.

Right now this file has one route: the reservation history search
(requirement 13). A signed-in student can list every reservation they
have made and narrow it down with optional filters:

    GET /api/registrations
        ?q=CIT                  text found in the exam name, subject or level
        &status=Active          Active, Cancelled or Complete
        &date_from=2026-10-01   exam date on or after this day
        &date_to=2026-12-31     exam date on or before this day

Every filter is optional. With none of them you get the whole history,
newest exam first.

It also has the cancel route (requirement 12):

    POST /api/registrations/<registration_id>/cancel
        Changes one of the signed-in student's Active reservations to
        Cancelled. The seat is freed automatically, because seat counts
        are made by counting Active registrations.
"""

from datetime import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError

from . import db
from .models import Campus, Exams, Registrations, Rooms, Sessions, Users
from schemas_exams_sessions import RoomSearch, SessionCreate
from helpers import role_required, get_current_user, parse_date, validation_errors

# A Blueprint is a bundle of routes that gets plugged into the app in
# create_app(). Every route in this file starts with /api.
api = Blueprint("api", __name__, url_prefix="/api")

# The only statuses the registrations table allows
VALID_STATUSES = ("Active", "Cancelled", "Complete")

@api.route("/registrations", methods=["GET"])
@role_required('Student')
def registration_history():
    """Return the signed-in student's reservations, filtered by the query string."""

    # Find out who is asking. Nobody signed in (or a stale cookie for a
    # user that no longer exists) gets a 401 and no data.
    user = get_current_user() #get_signed_in_user()
    # if user is None:
    #     session.clear()
    #     return jsonify(error="Please log in."), 401

    # # Faculty don't book exams, so they have no history to search.
    # if user.role != "Student":
    #     return jsonify(error="Only students have a reservation history."), 403

    # Join the five tables so every row carries what the page needs:
    # the registration, its session, the exam, the room and the campus.
    # The student ID comes from the login (user), never from the browser,
    # so a student can only ever see their own reservations.
    query = (
        db.select(Registrations, Sessions, Exams, Rooms, Campus)
        .select_from(Registrations)
        .join(Sessions, Registrations.session_id == Sessions.session_id)
        .join(Exams, Sessions.exam_id == Exams.exam_id)
        .join(Rooms, Sessions.room_id == Rooms.room_id)
        .join(Campus, Rooms.campus_id == Campus.campus_id)
        .where(Registrations.student_id == user.user_id)
    )

    # ---- optional filters, applied only when the browser sent them ----

    # Text search: matches part of the exam name, subject or level
    # Returns arguments for the query ex: url.com/registrations?q=CIT&status=Active
    #                   would return: {"q": "CIT": "status": "Active"}
    text = request.args.get("q", "").strip()  # Returns the value after "q="
    if text:
        # autoescape=True treats % and _ in the search text as plain characters
        query = query.where(or_(
            Exams.exam_name.contains(text, autoescape=True),
            Exams.subject.contains(text, autoescape=True),
            Exams.exam_level.contains(text, autoescape=True),
            Campus.name.contains(text, autoescape=True),
            Campus.address.contains(text, autoescape=True),
        ))

    # Status: Active, Cancelled or Complete
    status = request.args.get("status", "").strip()
    if status:
        if status not in VALID_STATUSES:
            return jsonify(error="status must be Active, Cancelled or Complete."), 400
        query = query.where(Registrations.status == status)

    # Date range on the exam date (both ends are included)
    date_from = request.args.get("date_from", "").strip()
    if date_from:
        start = parse_date(date_from)
        if start is None:
            return jsonify(error="date_from must look like 2026-10-14."), 400
        query = query.where(Sessions.session_date >= start)

    date_to = request.args.get("date_to", "").strip()
    if date_to:
        end = parse_date(date_to)
        if end is None:
            return jsonify(error="date_to must look like 2026-10-14."), 400
        query = query.where(Sessions.session_date <= end)

    # Newest exam first
    query = query.order_by(Sessions.session_date.desc(), Sessions.session_time.desc())

    # Turn each row into a plain dictionary that jsonify can send to the browser
    history = []
    for registration, exam_session, exam, room, campus in db.session.execute(query).all():
        history.append({
            "registration_id":  registration.registration_id,
            "status":           registration.status,
            # dates and times aren't JSON types, so they are sent as text
            "registered_at":    registration.registered_at.isoformat() if registration.registered_at else None,
            "session_id":       exam_session.session_id,
            "exam_name":        exam.exam_name,
            "subject":          exam.subject,
            "exam_level":       exam.exam_level,
            "session_date":        exam_session.session_date.isoformat(),
            "session_time":        exam_session.session_time.isoformat(),
            "campus":           campus.name,
            "address":          f"{campus.address}, {campus.city}, {campus.state} {campus.zip}",
            "building":         room.building,
            "room_num":         room.room_num,
        })

    return jsonify(registrations=history, count=len(history))


@api.route("/registrations/<int:registration_id>/cancel", methods=["POST"])
def cancel_registration(registration_id):
    """Cancel one of the signed-in student's reservations."""

    # Find out who is asking, the same way the history route does
    user = get_current_user() #get_signed_in_user()
    if user is None:
        session.clear()
        return jsonify(error="Please log in."), 401

    if user.role != "Student":
        return jsonify(error="Only students can cancel reservations."), 403

    # Look the reservation up by its ID AND the signed-in student's ID.
    # Someone else's reservation (or one that doesn't exist) comes back as
    # None, so a student can't cancel, or even confirm the existence of,
    # another student's booking by guessing ID numbers.
    # with_for_update() locks the row until commit() or rollback(), so two
    # clicks at the same moment can't both go through.
    registration = db.session.scalar(
        db.select(Registrations)
        .where(
            Registrations.registration_id == registration_id,
            Registrations.student_id == user.user_id,
        )
        .with_for_update()
    )
    if registration is None:
        db.session.rollback()  # release the lock
        return jsonify(error="Reservation not found."), 404

    # Only an Active reservation can be cancelled
    if registration.status == "Cancelled":
        db.session.rollback()
        return jsonify(error="This reservation is already cancelled."), 409
    if registration.status == "Complete":
        db.session.rollback()
        return jsonify(error="A completed exam can't be cancelled."), 409

    # The seat count for the session is made by counting Active registrations,
    # so changing the status is all it takes to free the seat.
    registration.status = "Cancelled"
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Could not cancel the reservation. Please try again."), 500

    return jsonify(message="Reservation cancelled."), 200

## END STUDENT HISTORY ROUTES ##



## BEGIN FACULTY REPORT ROUTES ##

@api.route("/faculty-report", methods=["GET"])
@role_required('Faculty')
def proctor_history():
    "Return the signed-in faculty member's current and previous sessions."
    # Find out who is asking. Nobody signed in (or a stale cookie for a
        # user that no longer exists) gets a 401 and no data.

    # TESTING role_required DECORATOR
    # user = get_current_user() #get_signed_in_user()
    # if user is None:
    #     session.clear()
    #     return jsonify(error="Please log in."), 401

    # # Students do not have access to Faculty reports
    # if user.role != "Faculty":
    #     return jsonify(error="Only faculty may use the faculty portal."), 403

    user = get_current_user()
    # The query to return the faculty member's owned sessions
    query = (
            db.select(Sessions, Registrations, Exams, Rooms, Campus, Users)
            .select_from(Sessions)
            .outerjoin(Registrations, Sessions.session_id == Registrations.session_id)
            .outerjoin(Users, Users.user_id == Registrations.student_id)
            .join(Exams, Sessions.exam_id == Exams.exam_id)
            .join(Rooms, Sessions.room_id == Rooms.room_id)
            .join(Campus, Rooms.campus_id == Campus.campus_id)
            .where(Sessions.proctor_id == user.user_id)
        )

# ---- optional filters, applied only when the browser sent them ----

    # Text search: matches part of the exam name, subject or level
    # Returns arguments for the query ex: url.com/registrations?q=CIT&status=Active
    #                   would return: {"q": "CIT": "status": "Active"}
    text = request.args.get("q", "").strip()  # Returns the value after "q=" or None if ""
    if text:
        # Search by exam details, location information, or student first/last name.
        # autoescape=True treats % and _ in the search text as plain characters
        query = query.where(or_(
            Exams.exam_name.contains(text, autoescape=True),
            Exams.subject.contains(text, autoescape=True),
            Exams.exam_level.contains(text, autoescape=True),
            Campus.name.contains(text, autoescape=True),
            Campus.address.contains(text, autoescape=True),
            Users.first_name.contains(text, autoescape=True),
            Users.last_name.contains(text, autoescape=True),
        ))

    # Status: Active, Cancelled or Complete [Session OR Registration]
    session_status = request.args.get("session_status", "").strip()
    if session_status:
        if session_status not in VALID_STATUSES:
            return jsonify(error="status must be Active, Cancelled or Complete."), 400
        query = query.where(Sessions.status == session_status)

    reg_status = request.args.get("reg_status", "").strip()
    if reg_status:
        if reg_status not in VALID_STATUSES:
            return jsonify(error="status must be Active, Cancelled or Complete."), 400
        query = query.where(Registrations.status == reg_status)

    # Date range on the exam date (both ends are included)
    date_from = request.args.get("date_from", "").strip()
    if date_from:
        start = parse_date(date_from)
        if start is None:
            return jsonify(error="date_from must look like 2026-10-14."), 400
        query = query.where(Sessions.session_date >= start)

    date_to = request.args.get("date_to", "").strip()
    if date_to:
        end = parse_date(date_to)
        if end is None:
            return jsonify(error="date_to must look like 2026-10-14."), 400
        query = query.where(Sessions.session_date <= end)

    # Newest Sessions first, then by exam subject and name, then by student last / first.
    query = query.order_by(
        Sessions.session_date.desc(),
        Sessions.session_time.desc(),
        Exams.subject.asc(),
        Exams.exam_level.asc(),
        Exams.exam_name.asc(),
        Users.last_name.asc(),
        Users.first_name.asc()
    )

# Turn each row into a plain dictionary that jsonify can send to the browser
    session_history = []
    for exam_session, registration, exam, room, campus, student in db.session.execute(query).all():
        session_history.append({
            "session_id": exam_session.session_id,
            "subject": exam.subject,
            "exam_level": exam.exam_level,
            "exam_name": exam.exam_name,
            "session_date": exam_session.session_date.isoformat(),
            "session_time": exam_session.session_time.isoformat(),
            # dates and times aren't JSON types, so they are sent as text
            "campus": campus.name,
            "address": f"{campus.address}, {campus.city}, {campus.state} {campus.zip}",
            "building": room.building,
            "room_num": room.room_num,

            # 
            "last_name": student.last_name if student else None,
            "first_name": student.first_name if student else None,
            "registration_status": registration.status if registration else None,
            "registered_at": (
                registration.registered_at.isoformat()
                if registration and registration.registered_at else None,
                )
        })

    return jsonify(sessions=session_history, count=len(session_history))


@api.route("/faculty-report/<int:session_id>/cancel", methods=["POST"])
@role_required('Faculty')
def cancel_session(exam_session_id):
    """Cancel one of the signed-in student's reservations."""

    # # Find out who is asking, the same way the history route does
    user = get_current_user()
    # if user is None:
    #     session.clear()
    #     return jsonify(error="Please log in."), 401

    # if user.role != "Faculty":
    #     return jsonify(error="Only faculty can cancel sessions."), 403



    ### BEGIN TRANSACTION ###
    ## SESSION CANCELLATION BEGIN ##
    # Look up session
    # with_for_update() locks the row until commit() or rollback(), so two
    # clicks at the same moment can't both go through.
    session = db.session.scalar(
        db.select(Sessions)
        .where(
            Sessions.session_id == exam_session_id,
            Sessions.proctor_id == user.user_id,
        )
        .with_for_update()
    )
    if session is None:
        db.session.rollback()  # release the lock
        return jsonify(error="Reservation not found."), 404

    # Only an Active session can be cancelled
    if session.status == "Cancelled":
        db.session.rollback()
        return jsonify(error="This reservation is already cancelled."), 409
    if session.status == "Complete":
        db.session.rollback()
        return jsonify(error="A completed exam can't be cancelled."), 409

    # The seat count for the session is made by counting Active registrations,
    # so changing the status is all it takes to free the seat.
    session.status = "Cancelled"
    ## SESSION CANCELLATION END ##

    # All active student registrations for this session must be cancelled, too.

    ## REGISTRATION CANCELLATION BEGIN ##
    reg_cancelled = db.session.execute(
        db.update(Registrations)
        .where(
            Registrations.session_id == exam_session_id,
            Registrations.status == 'Active',
        )
        .values(status = 'Cancelled')
    )
    ## REGISTRATION CANCELLATION END ##


    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Could not cancel the session. Please try again."), 500

    return jsonify(message="Session cancelled."), 200

## END FACULTY REPORT ROUTES ##



## BEGIN SESSION CREATION ROUTES##

@api.route("/rooms", methods=["GET"])
@role_required('Faculty')
def find_location():
    """Same function is used to find campus, building, and room. Supports search-as-type"""

    # validate the queries against pydantic model
    try:
        # turn the search parameters into a dictionary, then validate it
        params = RoomSearch.model_validate(request.args.to_dict())
    except ValidationError as e:
        return jsonify(error="Invalid search.", details = validation_errors(e)), 400
    
    # base query: the list of all campuses that have rooms, as well as the rooms contained
    query = (
        db.select(Campus, Rooms)
        .join(Rooms, Rooms.campus_id == Campus.campus_id)
    )

    ## SEARCH OPTIONS ##

    # If you have the campus ID, use that. Else search by name.
    if params.campus_id is not None:
        query = query.where(
            Campus.campus_id == params.campus_id
        )
    elif params.campus:  # if there is a query for campus
        # filter by campus name search
        query = query.where(
            Campus.name.contains(params.campus, autoescape=True)
        )

    if params.building:  # if there is a query for building
        query = query.where(
            Rooms.building.contains(params.building, autoescape=True)
        )
    if params.room_num:  # if there is a query for room
        query = query.where(
            Rooms.room_num.contains(params.room_num, autoescape=True)
        )

    rooms = []  # create a list of dictionaries
    # fill dictionary with query results
    for campus, room in db.session.execute(query).all():
        rooms.append({
            "c_id":         campus.campus_id,
            "c_name":       campus.name,
            "c_address":    campus.address,
            "c_city":       campus.city,
            "c_state":      campus.state,
            "c_zip":        campus.zip,
            "r_id":         room.room_id,
            "r_building":   room.building,
            "r_room_num":   room.room_num,
        })

    # return a json file with all rooms as a list of dictionaries as well as the count
    return jsonify(roomsFound=rooms, count=len(rooms))

@api.route("/exams", methods=["GET"])
@role_required('Faculty')
def find_exam():
    """Simple exam search function"""

    search = request.args.get("q","").strip() # return the value after "q="
    # base query: search exam names, subject, and level
    query = db.select(Exams).limit(20)
    if search:
            # autoescape=True treats % and _ in the search text as plain characters
            query = query.where(or_(
                Exams.subject.contains(search, autoescape=True),
                Exams.exam_level.contains(search, autoescape=True),
                Exams.exam_name.contains(search, autoescape=True),
            ))

    query = query.order_by(
        Exams.subject.asc(),
        Exams.exam_level.asc(),
        Exams.exam_name.asc(),
        Exams.description.asc()
    )

    # create an empty list
    results = []

    # fill the list with each row as a dictionary
    for exam in db.session.scalars(query).all():
        results.append({
            "e_id":             exam.exam_id,
            "e_subject":        exam.subject,
            "e_level":          exam.exam_level,
            "e_name":           exam.exam_name,
            "e_description:":   exam.description,
        })


    return jsonify(exams=results, count=len(results))

@api.route("/create/session", methods=["POST"])
@role_required('Faculty')
def create_session():
    # IMPORTANT: all SQL Alchemy queries begin a transaction, which must be later committed

    # Initialize data variables #

    user = get_current_user()

    try:
        # take data from the javascript or create empty dict, then validate.
        new_session = SessionCreate.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify(error="Invalid input.", details=validation_errors(e)), 400

    ## BEGIN TRANSACTION ##

    # build the new row as a Sessions object
    session_row = Sessions(
        exam_id=new_session.exam_id,
        room_id=new_session.room_id,
        proctor_id=user.user_id,
        session_date=new_session.session_date,
        session_time=new_session.session_time,
    )

    # Check if room and exam exist #
    if (db.session.get(Exams, session_row.exam_id) is None
            or db.session.get(Rooms, session_row.room_id) is None):
        db.session.rollback()
        return jsonify(error="Exam or room not found."), 404
    
    # Check if the room is taken #
    room_conflict = db.session.scalar(
        db.select(Sessions).where(
            Sessions.room_id == session_row.room_id,
            Sessions.session_date == session_row.session_date,
            Sessions.session_time == session_row.session_time,
            Sessions.status == "Active",
        ).limit(1)
    )
    if room_conflict is not None:
        db.session.rollback()
        return jsonify(error="Time slot for this room is taken."), 409

    # Check if proctor has a schedule conflict #
    proctor_conflict = db.session.scalar(
        db.select(Sessions).where(
            Sessions.proctor_id == user.user_id,
            Sessions.session_date == session_row.session_date,
            Sessions.session_time == session_row.session_time,
            Sessions.status == "Active",
        ).limit(1)
    )
    if proctor_conflict is not None:
        db.session.rollback()
        return jsonify(error="You already have a session at this date and time."), 409


    # Commit the transaction #
    db.session.add(session_row)
    try:
        db.session.commit()  # INSERT data
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Could not create the session. Try again."), 500

    # if successful, print success.
    return jsonify(message="Session created successfully", session_id=session_row.session_id), 201