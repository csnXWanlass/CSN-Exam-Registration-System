"""
setup_exam_db.py

Builds the exam_registration database from exam_registration_final.sql:
the tables, the validate_registration procedure, its two triggers, the
available_exam_sessions view and the sample data. Then it runs the test
queries and prints the results.

It deletes and rebuilds exam_registration every time it runs (it asks you
first). Your Flask app's projectdb database isn't touched.

Put this file next to your .env file and run it with (.venv) active:
    python setup_exam_db.py
"""

import os

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

load_dotenv()

DB_NAME = "exam_registration"


# ============================================
# PART 1: DATABASE STRUCTURE
# ============================================

TABLES = [
    # 1. CAMPUS
    """
    CREATE TABLE campus (
        campus_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(100) NOT NULL,
        city VARCHAR(50) NOT NULL,
        state CHAR(2) NOT NULL,
        address VARCHAR(255) NOT NULL,
        zip CHAR(5),
        location_phone VARCHAR(20)
    )
    """,
    # 2. ROOMS
    """
    CREATE TABLE rooms (
        room_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        campus_id INT UNSIGNED NOT NULL,
        building VARCHAR(3) NOT NULL,
        room_num VARCHAR(10) NOT NULL,

        CONSTRAINT fk_room_campus
            FOREIGN KEY (campus_id)
            REFERENCES campus(campus_id)
            ON DELETE CASCADE
    )
    """,
    # 3. USERS
    """
    CREATE TABLE users (
        user_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        first_name VARCHAR(35) NOT NULL,
        last_name VARCHAR(35) NOT NULL,
        email VARCHAR(255) NOT NULL,
        password VARCHAR(10) NOT NULL,
        role ENUM('Student', 'Faculty')
            NOT NULL DEFAULT 'Student',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT uq_user UNIQUE (password, email)
    )
    """,
    # 4. EXAMS
    """
    CREATE TABLE exams (
        exam_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        subject VARCHAR(8) NOT NULL,
        exam_level VARCHAR(4),
        exam_name VARCHAR(100) NOT NULL,
        description VARCHAR(255),

        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # 5. EXAM SESSIONS
    """
    CREATE TABLE exam_sessions (
        session_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        exam_id INT UNSIGNED NOT NULL,
        room_id INT UNSIGNED NOT NULL,
        proctor_id INT UNSIGNED NOT NULL,
        exam_date DATETIME NOT NULL,
        capacity TINYINT UNSIGNED NOT NULL DEFAULT 20,
        created_at DATETIME NOT NULL
            DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT fk_session_exam
            FOREIGN KEY (exam_id)
            REFERENCES exams(exam_id)
            ON DELETE CASCADE,

        CONSTRAINT fk_session_room
            FOREIGN KEY (room_id)
            REFERENCES rooms(room_id),

        CONSTRAINT fk_session_proctor
            FOREIGN KEY (proctor_id)
            REFERENCES users(user_id),

        CONSTRAINT chk_session_capacity
            CHECK (capacity BETWEEN 1 AND 20)
    )
    """,
    # 6. REGISTRATIONS
    """
    CREATE TABLE registrations (
        registration_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
        student_id INT UNSIGNED NOT NULL,
        session_id INT UNSIGNED NOT NULL,
        status ENUM('Active', 'Cancelled', 'Complete')
            NOT NULL DEFAULT 'Active',
        registered_at DATETIME NOT NULL
            DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT fk_registration_student
            FOREIGN KEY (student_id)
            REFERENCES users(user_id)
            ON DELETE CASCADE,
        CONSTRAINT fk_registration_session
            FOREIGN KEY (session_id)
            REFERENCES exam_sessions(session_id)
            ON DELETE CASCADE,
        CONSTRAINT no_duplicate_session
            UNIQUE (student_id, session_id)
    )
    """,
]

# The .sql file wraps this in DELIMITER // because the procedure contains
# semicolons. DELIMITER is a Workbench/mysql-client command, not SQL, so
# Python doesn't use it: each string below is sent to MySQL as one statement.
#
# The procedure cuts down on code length, as it can be applied to updates
# as well.
# USAGE: validate_registration(
#        NEW.student_id,
#        NEW.session_id,
#        NEW.registration_id,
#        NEW.status)
PROCEDURE = """
CREATE PROCEDURE validate_registration(
    IN p_student_id INT UNSIGNED,
    IN p_session_id INT UNSIGNED,
    IN p_registration_id INT UNSIGNED,
    IN p_status VARCHAR(20)  -- status cannot be enum datatype
)
BEGIN

    DECLARE student_role VARCHAR(20);
    DECLARE active_registrations INT DEFAULT 0;
    DECLARE active_seats INT DEFAULT 0;
    DECLARE max_capacity INT DEFAULT 0;
    DECLARE selected_exam_id INT;
    DECLARE duplicate_exam INT DEFAULT 0;


    -- Only REGISTERED students can register
    SELECT role
    INTO student_role
    FROM users
    WHERE user_id = p_student_id;
    IF student_role IS NULL OR student_role <> 'Student' THEN  -- null check
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT =
            'Only registered students can register for exams';
    END IF;


    IF p_status = 'Active' THEN

        -- Maximum 3 active registrations
        SELECT COUNT(*)
        INTO active_registrations
        FROM registrations
        WHERE student_id = p_student_id
          AND status = 'Active'
          -- below check excludes registration ID if there is no new
          -- ID. ID creation happens after triggers.
          -- needed to allow changes to the table where student
          -- already has 3 registrations.
          AND registration_id <> COALESCE(p_registration_id, 0);

        -- EX: 3 active, student updates 1 more to active.
        --     count excludes the new update, returning 3
        --     3 >= 3, so error.
        IF active_registrations >= 3 THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT =
                'Student cannot have more than 3 active registrations';
        END IF;


        -- Get exam and capacity
        SELECT exam_id, capacity
        INTO selected_exam_id, max_capacity
        FROM exam_sessions
        WHERE session_id = p_session_id;

        -- Protect against nonexistent exam_id input
        IF selected_exam_id IS NULL THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Exam not found.';
        END IF;


        -- No duplicate active exam
        SELECT COUNT(*)
        INTO duplicate_exam
        FROM registrations r

        JOIN exam_sessions es
            ON r.session_id = es.session_id

        WHERE r.student_id = p_student_id
          AND r.status = 'Active'
          AND es.exam_id = selected_exam_id
          AND r.registration_id <> COALESCE(p_registration_id, 0);

        IF duplicate_exam > 0 THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT =
                'Student is already registered for this exam';
        END IF;


        -- Session capacity check
        SELECT COUNT(*)
        INTO active_seats
        FROM registrations
        WHERE session_id = p_session_id
          AND status = 'Active'
          AND registration_id <> COALESCE(p_registration_id, 0);

        IF active_seats >= max_capacity THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT =
                'Exam session is full';
        END IF;

    END IF;

END
"""

TRIGGERS = [
    """
    CREATE TRIGGER chk_registration_insert
    BEFORE INSERT ON registrations
    FOR EACH ROW
        CALL validate_registration(
            NEW.student_id,
            NEW.session_id,
            NEW.registration_id,
            NEW.status)
    """,
    """
    CREATE TRIGGER chk_registration_update
    BEFORE UPDATE ON registrations
    FOR EACH ROW
        CALL validate_registration(
            NEW.student_id,
            NEW.session_id,
            NEW.registration_id,
            NEW.status)
    """,
]

VIEW = """
CREATE VIEW available_exam_sessions AS

SELECT
    es.session_id,
    e.exam_name,
    e.subject,
    e.exam_level,
    es.exam_date,
    c.name,
    c.address,
    c.city,
    c.state,
    c.zip,
    r.building,
    r.room_num,
    es.capacity,
    COUNT(reg.registration_id) AS seats_taken,
    es.capacity - COUNT(reg.registration_id) AS seats_available
FROM exam_sessions es
    JOIN exams e
        ON es.exam_id = e.exam_id
    JOIN rooms r
        ON es.room_id = r.room_id
    JOIN campus c
        ON r.campus_id = c.campus_id
    LEFT JOIN registrations reg
        ON es.session_id = reg.session_id
        AND reg.status = 'Active'
GROUP BY
    es.session_id
HAVING COUNT(reg.registration_id) < es.capacity
"""


# ============================================
# PART 2: SAMPLE DATA
# ============================================
# The %s placeholders let PyMySQL insert each value safely, so a quote inside
# a value (like "Coombs's") doesn't need escaping. Order matters because of
# the foreign keys: users, campus and exams have to exist before the rows
# that point to them.

SAMPLE_DATA = [
    (
        "INSERT INTO users (first_name, last_name, email, password, role, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        [
            ("John", "Doe", "9999999999@student.csn.edu", "9999999999", "Student", "2026-10-01 11:00:00"),
            ("Jane", "Doe", "jDoe@csn.edu", "1111111111", "Faculty", "2026-10-01 10:30:00"),
        ],
    ),
    (
        "INSERT INTO campus (name, city, state, address, zip, location_phone) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        [
            ("Charleston Campus", "Las Vegas", "NV", "6375 W Charleston Blvd", "89146", "(702) 651-5000"),
        ],
    ),
    (
        "INSERT INTO exams (subject, exam_level, exam_name, description, created_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        [
            ("CIT", "260", "Systems Development and Design Midterm",
             "Midterm covering Dr. Coombs's textbook through chapter 8", "2026-10-01 10:00:00"),
        ],
    ),
    (
        "INSERT INTO rooms (campus_id, building, room_num) "
        "VALUES (%s, %s, %s)",
        [
            (1, "C", "115"),
        ],
    ),
    (
        "INSERT INTO exam_sessions (exam_id, room_id, proctor_id, exam_date, capacity, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        [
            (1, 1, 2, "2026-10-14 18:00:00", 20, "2026-10-01 11:00:00"),
        ],
    ),
    (
        "INSERT INTO registrations (student_id, session_id, status, registered_at) "
        "VALUES (%s, %s, %s, %s)",
        [
            (1, 1, "Active", "2026-10-05 12:00:00"),
        ],
    ),
]


# ============================================
# PART 3: TEST QUERIES
# ============================================

TEST_QUERIES = [
    ("All registrations", "SELECT * FROM registrations"),
    ("Available exam sessions", "SELECT * FROM available_exam_sessions"),
    (
        "Add a second exam",
        """
        INSERT INTO exams
            (subject, exam_level, exam_name, description, created_at)
        VALUES
            ('CIT', '180', 'Database Concepts Exam',
             'Database Concepts test',
             '2026-10-01 10:00:00')
        """,
    ),
    ("All exams", "SELECT * FROM exams"),
    (
        "Registration details for student 1",
        """
        SELECT
            r.registration_id,
            u.first_name,
            u.last_name,
            e.exam_name,
            es.exam_date,
            c.name AS campus,
            rm.building,
            rm.room_num,
            r.status,
            r.registered_at
        FROM registrations r
        JOIN users u
            ON r.student_id = u.user_id
        JOIN exam_sessions es
            ON r.session_id = es.session_id
        JOIN exams e
            ON es.exam_id = e.exam_id
        JOIN rooms rm
            ON es.room_id = rm.room_id
        JOIN campus c
            ON rm.campus_id = c.campus_id
        WHERE r.student_id = 1
        """,
    ),
]


# ============================================
# RUNNING IT
# ============================================

def run(cursor, sql, params=None, many=False):
    """Run one statement. If MySQL rejects it, say which one and stop."""
    try:
        if many:
            cursor.executemany(sql, params)
        else:
            cursor.execute(sql, params)
    except pymysql.MySQLError as error:
        first_line = sql.strip().splitlines()[0]
        raise SystemExit(f"\nMySQL rejected this statement:\n    {first_line}\n{error}")


def print_rows(title, rows):
    print(f"\n{title} ({len(rows)} row{'' if len(rows) == 1 else 's'})")
    for row in rows:
        print("  " + " | ".join(f"{column}: {value}" for column, value in row.items()))


def main():
    if not os.getenv("MYSQL_USER"):
        raise SystemExit("MYSQL_USER isn't set. Put this script in the same folder as your .env file.")

    answer = input(f"This deletes and rebuilds the '{DB_NAME}' database. Continue? (y/n) ")
    if answer.strip().lower() != "y":
        print("Cancelled.")
        return

    try:
        connection = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            autocommit=True,  # save each statement right away, like Workbench does
            cursorclass=DictCursor,
        )
    except pymysql.MySQLError as error:
        raise SystemExit(f"Couldn't connect to MySQL: {error}")

    try:
        with connection.cursor() as cursor:
            # PART 1: DATABASE STRUCTURE
            run(cursor, f"DROP DATABASE IF EXISTS {DB_NAME}")
            run(cursor, f"CREATE DATABASE {DB_NAME}")
            run(cursor, f"USE {DB_NAME}")
            for statement in TABLES + [PROCEDURE] + TRIGGERS + [VIEW]:
                run(cursor, statement)

            # PART 2: SAMPLE DATA
            for sql, rows in SAMPLE_DATA:
                run(cursor, sql, rows, many=True)

            print(f"\nBuilt the '{DB_NAME}' database.")
            run(cursor, "SHOW TABLES")
            print("Tables and views:", ", ".join(list(row.values())[0] for row in cursor.fetchall()))
            run(cursor, "SHOW TRIGGERS")
            for trigger in cursor.fetchall():
                print(f"Trigger: {trigger['Trigger']} ({trigger['Timing']} {trigger['Event']} on {trigger['Table']})")

            # PART 3: TEST QUERIES
            for title, sql in TEST_QUERIES:
                run(cursor, sql)
                if cursor.description:  # SELECTs return rows; INSERTs don't
                    print_rows(title, cursor.fetchall())
                else:
                    print(f"\n{title}: {cursor.rowcount} row(s) affected")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
