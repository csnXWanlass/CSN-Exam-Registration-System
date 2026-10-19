-- ============================================
-- EXAM REGISTRATION SYSTEM
-- Version 0.1.2
-- ============================================
-- changelog:
--  0.1.2
--  * "campus" changed to "campuses"
--  0.1.1:
--  *added version control
--  *split exam_sessions.exam_date into date/time columns
--  *altered order of campus columns to match address forms
--  *added unique constraint to campus names
--  *changed CONSTRAINT no_duplicate_session to uq_registration
--  *added CONSTRAINT(s) uq_exam & uq_campus_location
--  *changed all DATETIME to TIMESTAMP (timestamp converts to UTC)
--  *separated sample data again
--  *campus.zip is NOT NULL
-- ============================================
-- PART 1: DATABASE STRUCTURE
-- ============================================

-- ============================================
-- EXAM REGISTRATION SYSTEM
-- CLEAN DATABASE SETUP
-- ============================================

DROP DATABASE IF EXISTS exam_registration;

CREATE DATABASE exam_registration;

USE exam_registration;


-- ============================================
-- 1. CAMPUS
-- ============================================

CREATE TABLE campuses (
    campus_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    address VARCHAR(255) NOT NULL,
    city VARCHAR(50) NOT NULL,
    state CHAR(2) NOT NULL,
    zip CHAR(5) NOT NULL,
    location_phone VARCHAR(20),

    CONSTRAINT uq_campus_location
        UNIQUE (city, state, address)
);


-- ============================================
-- 2. ROOMS
-- ============================================

CREATE TABLE rooms (
    room_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    campus_id INT UNSIGNED NOT NULL,
    building VARCHAR(3) NOT NULL,
    room_num VARCHAR(10) NOT NULL,

    CONSTRAINT fk_room_campus
        FOREIGN KEY (campus_id)
        REFERENCES campuses(campus_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_room UNIQUE (campus_id, building, room_num)
);


-- ============================================
-- 3. USERS
-- ============================================

CREATE TABLE users (
    user_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    first_name VARCHAR(35) NOT NULL,
    last_name VARCHAR(35) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password VARCHAR(10) NOT NULL,
    role ENUM('Student', 'Faculty')
        NOT NULL DEFAULT 'Student',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_user UNIQUE (email)
);


-- ============================================
-- 4. EXAMS
-- ============================================

CREATE TABLE exams (
    exam_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    subject VARCHAR(8) NOT NULL,
    exam_level VARCHAR(4),
    exam_name VARCHAR(100) NOT NULL,
    description VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_exam
        UNIQUE (exam_level, exam_name)
);


-- ============================================
-- 5. EXAM SESSIONS
-- ============================================

CREATE TABLE exam_sessions (
    session_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    exam_id INT UNSIGNED NOT NULL,
    room_id INT UNSIGNED NOT NULL,
    proctor_id INT UNSIGNED NOT NULL,
    exam_date DATE NOT NULL,
    exam_time TIME NOT NULL,
    capacity TINYINT UNSIGNED NOT NULL DEFAULT 20,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

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
);


-- ============================================
-- 6. REGISTRATIONS
-- ============================================

CREATE TABLE registrations (
    registration_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    student_id INT UNSIGNED NOT NULL,
    session_id INT UNSIGNED NOT NULL,
    status ENUM('Active', 'Cancelled', 'Complete')
        NOT NULL DEFAULT 'Active',
    registered_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_registration_student
        FOREIGN KEY (student_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_registration_session
        FOREIGN KEY (session_id)
        REFERENCES exam_sessions(session_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_registration
        UNIQUE (student_id, session_id)
);
DELIMITER //
-- procedure cuts down on code length, as it can be applied
-- to updates as well.

-- USAGE: validate_registration(
--        NEW.student_id,
--        NEW.session_id,
--        NEW.registration_id,
--        NEW.status,
--        )
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
        IF selected_exam_id IS NULL  THEN 
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

END//


CREATE TRIGGER chk_registration_insert
BEFORE INSERT ON registrations
FOR EACH ROW
    CALL validate_registration(
        NEW.student_id,
        NEW.session_id,
        NEW.registration_id,
        NEW.status)//

CREATE TRIGGER chk_registration_update
BEFORE UPDATE ON registrations
FOR EACH ROW
    CALL validate_registration(
        NEW.student_id,
        NEW.session_id,
        NEW.registration_id,
        NEW.status)//

DELIMITER ;
SHOW TABLES;

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
    JOIN campuses c
        ON r.campus_id = c.campus_id
    LEFT JOIN registrations reg
        ON es.session_id = reg.session_id
        AND reg.status = 'Active'
GROUP BY
    es.session_id
HAVING COUNT(reg.registration_id) < es.capacity;

SHOW TABLES;
SHOW TRIGGERS;