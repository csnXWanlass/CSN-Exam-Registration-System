"""
project/models.py

SQLAlchemy models for the exam_registration database. They map onto the tables created by
the SQL file (reset_exam_registration_db.sql), so Flask reads and writes those tables
rather than creating its own.

Reviewed version. Your code is kept; the edits are marked:
  # CHANGED: an existing line was fixed
  # NEW:     something was added
Save this over project/models.py (copy everything, replace the whole file).
"""

from flask_login import UserMixin
from sqlalchemy.dialects.mysql import INTEGER, TINYINT

from . import db, login_manager
# SQL Alchemy database models following examregistration v 0.1.1 schema



class Campus(db.Model):
    """One row in the campuses table"""

    __tablename__ = "campuses"

    campus_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    state = db.Column(db.String(2), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    zip = db.Column(db.String(5), nullable=False)
    
    __table_args__ = (
        db.UniqueConstraint("city", "state", "address", name="uq_campus_location"),
        db.UniqueConstraint("name", name="uq_campus_name"),
    )

    def __repr__(self):
        return f"<Campus {self.name}>"



class Rooms(db.Model):
    """One row in the rooms table"""

    __tablename__ = "rooms"

    room_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    campus_id = db.Column(INTEGER(unsigned=True), nullable=False)
    building = db.Column(db.String(3), nullable=False)
    room_num = db.Column(db.String(10), nullable=False)

    __table_args__ = (
        db.ForeignKeyConstraint(["campus_id"], ["campuses.campus_id"], name="fk_rooms_campus"),
        db.UniqueConstraint("campus_id", "building", "room_num", name="uq_room"),
    )

    def __repr__(self):
        return f"<Room {self.room_num} at campus {self.campus_id}>"



class Users(UserMixin, db.Model):
    """One row in the users table"""

    __tablename__ = "users"

    user_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    first_name = db.Column(db.String(35), nullable=False)
    last_name = db.Column(db.String(35), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(10), nullable=False)
    role = db.Column(db.Enum("Student", "Faculty"), nullable=False, server_default="Student")
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    # Matches CONSTRAINT uq_user in the SQL file. If you change that to
    # UNIQUE (email), change this to db.UniqueConstraint("email", name="uq_user").
    __table_args__ = (db.UniqueConstraint("password", "email", name="uq_user"),)

    def get_id(self):
        # Flask-Login looks for a column called "id" by default. This table
        # calls it user_id, so this tells Flask-Login where to find it.
        return str(self.user_id)

    def __repr__(self):
        return f"<User {self.email}>"



class Exams(db.Model):
    """One row in the exams table"""

    __tablename__ = "exams"

    exam_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    subject = db.Column(db.String(100), nullable=False)
    exam_level = db.Column(db.String(4), nullable=False)
    exam_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.UniqueConstraint("exam_name", name="uq_exam"),)
    def __repr__(self):
        return f"<Exam {self.exam_name}>"



class Sessions(db.Model):
    """One row in the exam_sessions table"""

    __tablename__ = "exam_sessions"

    session_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    exam_id = db.Column(INTEGER(unsigned=True), nullable=False)
    room_id = db.Column(INTEGER(unsigned=True), nullable=False)
    proctor_id = db.Column(INTEGER(unsigned = True), nullable = False)
    session_date = db.Column(db.Date, nullable = False)
    session_time = db.Column(db.Time, nullable = False)
    capacity = db.Column(TINYINT(unsigned=True), nullable = False, server_default="20")
    status = db.Column(db.Enum("Active", "Cancelled", "Complete"), nullable=False, server_default="Active")
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.ForeignKeyConstraint(["exam_id"], ["exams.exam_id"], name="fk_sessions_exam"),
        db.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name="fk_sessions_room"),
        db.ForeignKeyConstraint(["proctor_id"], ["users.user_id"], name="fk_session_proctor"),
        db.UniqueConstraint("exam_id", "session_date", "session_time",
                            "room_id", name="uq_session"),
    )

    def __repr__(self):
        return f"<Session {self.session_id} for exam {self.exam_id} on {self.session_date} at {self.session_time}>"



class Registrations(db.Model):
    """One row in the registrations table"""

    __tablename__ = "registrations"

    registration_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    student_id = db.Column(INTEGER(unsigned=True), nullable=False)
    session_id = db.Column(INTEGER(unsigned=True), nullable=False)
    status = db.Column(db.Enum("Active", "Cancelled", "Complete"), nullable=False, server_default="Active")
    registered_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))
    # NEW: when the registration was cancelled. The database trigger fills this in; it is
    # empty for registrations that are not cancelled.
    cancelled_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.ForeignKeyConstraint(["student_id"], ["users.user_id"], name="fk_registrations_student"),
        db.ForeignKeyConstraint(["session_id"], ["exam_sessions.session_id"], name="fk_registrations_session"),
        db.UniqueConstraint("student_id", "session_id", name="no_duplicate_session"),
    )

    def __repr__(self):
        # CHANGED: self.student_id (this model has no user_id, so printing a registration crashed)
        return f"<Registration {self.registration_id} for user {self.student_id} and session {self.session_id}>"



# NEW: one row in the registration_activity table: a single register or cancel event.
# The database triggers add these rows automatically; the faculty Activity panel reads them.
class RegistrationActivity(db.Model):
    """One row in the registration_activity table"""

    __tablename__ = "registration_activity"

    activity_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    student_id = db.Column(INTEGER(unsigned=True), nullable=False)
    session_id = db.Column(INTEGER(unsigned=True), nullable=False)
    action = db.Column(db.Enum("Registered", "Cancelled"), nullable=False)
    occurred_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.ForeignKeyConstraint(["student_id"], ["users.user_id"], name="fk_activity_student"),
        db.ForeignKeyConstraint(["session_id"], ["exam_sessions.session_id"], name="fk_activity_session"),
    )

    def __repr__(self):
        return f"<Activity {self.action} by user {self.student_id} in session {self.session_id}>"



# CHANGED: moved out of the Registrations class to module level (it was indented inside it).
# Flask-Login passes the id saved in the session cookie;
# return the matching Users row, or None if it no longer exists
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Users, int(user_id))