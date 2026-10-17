"""
project/models.py

The User model for the exam_registration database. It maps onto the users
table that setup_exam_db.py creates, so Flask reads and writes that table
rather than creating its own.
"""

from flask_login import UserMixin
from sqlalchemy.dialects.mysql import INTEGER, TINYINT

from . import db
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
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))
    
    __table_args__ = (
        db.UniqueConstraint("city", "state", "address", name="uq_campus_location"),
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
        db.UniqueConstraint("campus_id", "room_num", name="uq_room"),
    )

    def __repr__(self):
        return f"<Room {self.room_number} at campus {self.campus_id}>"



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
    """One row in the sessions table"""

    __tablename__ = "exam_sessions"

    session_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    exam_id = db.Column(INTEGER(unsigned=True), nullable=False)
    room_id = db.Column(INTEGER(unsigned=True), nullable=False)
    proctor_id = db.Column(INTEGER(unsigned = True), nullable = False)
    exam_date = db.Column(db.Date, nullable = False)
    exam_time = db.Column(db.Time, nullable = False)
    capacity = db.Column(TINYINT(unsigned=True), nullable = False, server_default="20")

    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.ForeignKeyConstraint(["exam_id"], ["exams.exam_id"], name="fk_sessions_exam"),
        db.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name="fk_sessions_room"),
        db.UniqueConstraint("exam_id", "exam_date", "exam_time", name="uq_session"),
    )

    def __repr__(self):
        return f"<Session {self.session_id} for exam {self.exam_id} on {self.exam_date} at {self.exam_time}>"



class Registrations(db.Model):
    """One row in the registrations table"""

    __tablename__ = "registrations"

    registration_id = db.Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    user_id = db.Column(INTEGER(unsigned=True), nullable=False)
    session_id = db.Column(INTEGER(unsigned=True), nullable=False)
    status = db.Column(db.Enum("Active", "Cancelled", "Complete"), nullable=False, server_default="Active")
    registered_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        db.ForeignKeyConstraint(["user_id"], ["users.user_id"], name="fk_registrations_student"),
        db.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], name="fk_registrations_session"),
        db.UniqueConstraint("user_id", "session_id", name="no_duplicate_session"),
    )

    def __repr__(self):
        return f"<Registration {self.registration_id} for user {self.user_id} and session {self.session_id}>"