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

from . import db
from .models import Campus, Exams, Registrations, Rooms, Sessions, Users

# A Blueprint is a bundle of routes that gets plugged into the app in
# create_app(). Every route in this file starts with /api.
api = Blueprint("api", __name__, url_prefix="/api")

# The only statuses the registrations table allows
VALID_STATUSES = ("Active", "Cancelled", "Complete")


def get_signed_in_user():
    """Return the Users row for whoever is signed in, or None.

    Reads the same session["user_id"] that the /login route in app.py sets.
    """
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(Users, int(user_id))


def parse_date(text):
    """Turn text like '2026-10-14' into a date. Return None if it isn't one."""
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


@api.route("/registrations", methods=["GET"])
def registration_history():
    """Return the signed-in student's reservations, filtered by the query string."""

    # Find out who is asking. Nobody signed in (or a stale cookie for a
    # user that no longer exists) gets a 401 and no data.
    user = get_signed_in_user()
    if user is None:
        session.clear()
        return jsonify(error="Please log in."), 401

    # Faculty don't book exams, so they have no history to search.
    if user.role != "Student":
        return jsonify(error="Only students have a reservation history."), 403

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
    text = request.args.get("q", "").strip()
    if text:
        # autoescape=True treats % and _ in the search text as plain characters
        query = query.where(or_(
            Exams.exam_name.contains(text, autoescape=True),
            Exams.subject.contains(text, autoescape=True),
            Exams.exam_level.contains(text, autoescape=True),
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
        query = query.where(Sessions.exam_date >= start)

    date_to = request.args.get("date_to", "").strip()
    if date_to:
        end = parse_date(date_to)
        if end is None:
            return jsonify(error="date_to must look like 2026-10-14."), 400
        query = query.where(Sessions.exam_date <= end)

    # Newest exam first
    query = query.order_by(Sessions.exam_date.desc(), Sessions.exam_time.desc())

    # Turn each row into a plain dictionary that jsonify can send to the browser
    history = []
    for reg, exam_session, exam, room, campus in db.session.execute(query).all():
        history.append({
            "registration_id": reg.registration_id,
            "status": reg.status,
            # dates and times aren't JSON types, so they are sent as text
            "registered_at": reg.registered_at.isoformat() if reg.registered_at else None,
            "session_id": exam_session.session_id,
            "exam_name": exam.exam_name,
            "subject": exam.subject,
            "exam_level": exam.exam_level,
            "exam_date": exam_session.exam_date.isoformat(),
            "exam_time": exam_session.exam_time.isoformat(),
            "campus": campus.name,
            "address": f"{campus.address}, {campus.city}, {campus.state} {campus.zip}",
            "building": room.building,
            "room_num": room.room_num,
        })

    return jsonify(registrations=history, count=len(history))


@api.route("/registrations/<int:registration_id>/cancel", methods=["POST"])
def cancel_registration(registration_id):
    """Cancel one of the signed-in student's reservations."""

    # Find out who is asking, the same way the history route does
    user = get_signed_in_user()
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