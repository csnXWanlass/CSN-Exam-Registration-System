DROP DATABASE IF EXISTS exam_registration;
CREATE DATABASE exam_registration;
USE exam_registration;
 
 
-- ================================================================
-- PART 1: TABLES
-- Created in this order because later tables point to earlier ones (foreign keys).
-- ================================================================
 
-- 1. CAMPUS
CREATE TABLE campuses (
    campus_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    city VARCHAR(50) NOT NULL,
    state CHAR(2) NOT NULL,
    address VARCHAR(255) NOT NULL,
    zip CHAR(5) NOT NULL,
    location_phone VARCHAR(20),   -- optional; not used by the Flask models
 
    CONSTRAINT uq_campus_location UNIQUE (city, state, address),
    CONSTRAINT uq_campus_name UNIQUE (name)
);
 
-- 2. USERS (students and faculty)
CREATE TABLE users (
    user_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    first_name VARCHAR(35) NOT NULL,
    last_name VARCHAR(35) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password VARCHAR(10) NOT NULL,
    role ENUM('Student', 'Faculty') NOT NULL DEFAULT 'Student',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT uq_user UNIQUE (password, email)
);
 
-- 3. EXAMS
CREATE TABLE exams (
    exam_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    subject VARCHAR(100) NOT NULL,
    exam_level VARCHAR(4) NOT NULL,
    exam_name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT uq_exam UNIQUE (exam_name)
);
 
-- 4. ROOMS (each room belongs to a campus)
CREATE TABLE rooms (
    room_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    campus_id INT UNSIGNED NOT NULL,
    building VARCHAR(3) NOT NULL,
    room_num VARCHAR(10) NOT NULL,
 
    CONSTRAINT fk_rooms_campus
        FOREIGN KEY (campus_id) REFERENCES campuses(campus_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_room UNIQUE (campus_id, building, room_num)
);
 
-- 5. EXAM SESSIONS (an exam, in a room, with a proctor, on a date and time)
CREATE TABLE exam_sessions (
    session_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    exam_id INT UNSIGNED NOT NULL,
    room_id INT UNSIGNED NOT NULL,
    proctor_id INT UNSIGNED NOT NULL,
    session_date DATE NOT NULL,
    session_time TIME NOT NULL,
    capacity TINYINT UNSIGNED NOT NULL DEFAULT 20,
    status ENUM('Active', 'Cancelled', 'Complete') NOT NULL DEFAULT 'Active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT fk_sessions_exam
        FOREIGN KEY (exam_id) REFERENCES exams(exam_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_sessions_room
        FOREIGN KEY (room_id) REFERENCES rooms(room_id),
    CONSTRAINT fk_session_proctor
        FOREIGN KEY (proctor_id) REFERENCES users(user_id),
    CONSTRAINT uq_session UNIQUE (exam_id, session_date, session_time, room_id),
    CONSTRAINT chk_session_capacity CHECK (capacity BETWEEN 1 AND 20)
);
 
-- 6. REGISTRATIONS (one row per student per session; the status changes instead of the row being deleted)
CREATE TABLE registrations (
    registration_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    student_id INT UNSIGNED NOT NULL,
    session_id INT UNSIGNED NOT NULL,
    status ENUM('Active', 'Cancelled', 'Complete') NOT NULL DEFAULT 'Active',
    registered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelled_at DATETIME NULL,   -- filled in by trg_registration_activity_times below
 
    CONSTRAINT fk_registrations_student
        FOREIGN KEY (student_id) REFERENCES users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_registrations_session
        FOREIGN KEY (session_id) REFERENCES exam_sessions(session_id)
        ON DELETE CASCADE,
    CONSTRAINT no_duplicate_session UNIQUE (student_id, session_id)
);
 
-- 7. REGISTRATION ACTIVITY (the full history: one row per register or cancel event)
CREATE TABLE registration_activity (
    activity_id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    student_id INT UNSIGNED NOT NULL,
    session_id INT UNSIGNED NOT NULL,
    action ENUM('Registered', 'Cancelled') NOT NULL,
    occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 
    CONSTRAINT fk_activity_student
        FOREIGN KEY (student_id) REFERENCES users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_activity_session
        FOREIGN KEY (session_id) REFERENCES exam_sessions(session_id)
        ON DELETE CASCADE,
    INDEX idx_activity_session (session_id, occurred_at)
);
 
 
-- ================================================================
-- PART 2: REGISTRATION RULES (stored procedure and triggers)
-- ================================================================
 
-- DELIMITER is a Workbench / mysql-client command, not SQL. The procedure contains
-- semicolons, so the delimiter is switched to // while it is created, then switched back.
DELIMITER //
 
-- Checks a registration before it is saved. It is called by the two validation triggers
-- below, so the same rules apply to new registrations and to updates.
CREATE PROCEDURE validate_registration(
    IN p_student_id INT UNSIGNED,
    IN p_session_id INT UNSIGNED,
    IN p_registration_id INT UNSIGNED,
    IN p_status VARCHAR(20)   -- status cannot be an enum datatype here
)
BEGIN
 
    DECLARE student_role VARCHAR(20);
    DECLARE active_registrations INT DEFAULT 0;
    DECLARE active_seats INT DEFAULT 0;
    DECLARE max_capacity INT DEFAULT 0;
    DECLARE selected_exam_id INT;
    DECLARE duplicate_exam INT DEFAULT 0;
 
    -- Only registered students can register
    SELECT role
    INTO student_role
    FROM users
    WHERE user_id = p_student_id;
    IF student_role IS NULL OR student_role <> 'Student' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Only registered students can register for exams';
    END IF;
 
    -- The remaining rules only apply when the registration is (or becomes) Active
    IF p_status = 'Active' THEN
 
        -- Maximum 3 active registrations.
        -- The current registration is excluded from the count (COALESCE handles a brand-new
        -- row that has no ID yet), so updating one of 3 existing registrations is allowed.
        SELECT COUNT(*)
        INTO active_registrations
        FROM registrations
        WHERE student_id = p_student_id
          AND status = 'Active'
          AND registration_id <> COALESCE(p_registration_id, 0);
 
        IF active_registrations >= 3 THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Student cannot have more than 3 active registrations';
        END IF;
 
        -- Look up the session's exam and capacity
        SELECT exam_id, capacity
        INTO selected_exam_id, max_capacity
        FROM exam_sessions
        WHERE session_id = p_session_id;
 
        -- Protect against a session that doesn't exist
        IF selected_exam_id IS NULL THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Exam not found.';
        END IF;
 
        -- No registering for the same exam twice (in any session of that exam)
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
            SET MESSAGE_TEXT = 'Student is already registered for this exam';
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
            SET MESSAGE_TEXT = 'Exam session is full';
        END IF;
 
    END IF;
 
END //
 
DELIMITER ;
 
-- VALIDATION: run the checks above before every insert and update on registrations.
CREATE TRIGGER chk_registration_insert
BEFORE INSERT ON registrations
FOR EACH ROW
    CALL validate_registration(NEW.student_id, NEW.session_id, NEW.registration_id, NEW.status);
 
CREATE TRIGGER chk_registration_update
BEFORE UPDATE ON registrations
FOR EACH ROW
    CALL validate_registration(NEW.student_id, NEW.session_id, NEW.registration_id, NEW.status);
 
-- TIMESTAMPS: runs just after the validation trigger on every update.
--   * Status changes to Cancelled    -> cancelled_at is set to the current time.
--   * Status changes back to Active  -> cancelled_at is cleared and registered_at is reset to
--                                       the current time (registering again is a new registration).
--   * Anything else                  -> both columns are left as they are.
CREATE TRIGGER trg_registration_activity_times
BEFORE UPDATE ON registrations
FOR EACH ROW
FOLLOWS chk_registration_update
SET NEW.cancelled_at = CASE
        WHEN NEW.status = 'Cancelled' AND OLD.status <> 'Cancelled' THEN NOW()
        WHEN NEW.status <> 'Cancelled' THEN NULL
        ELSE NEW.cancelled_at
    END,
    NEW.registered_at = CASE
        WHEN OLD.status = 'Cancelled' AND NEW.status = 'Active' THEN NOW()
        ELSE NEW.registered_at
    END;
 
-- HISTORY LOG: after a registration is saved, record the event in registration_activity.
-- A new Active registration is logged as "Registered".
CREATE TRIGGER trg_registration_log_insert
AFTER INSERT ON registrations
FOR EACH ROW
INSERT INTO registration_activity (student_id, session_id, action)
SELECT NEW.student_id, NEW.session_id, 'Registered'
FROM DUAL
WHERE NEW.status = 'Active';
 
-- A status change to Cancelled is logged as "Cancelled"; a change back to Active is logged as
-- "Registered". Updates that don't change the status are not logged.
CREATE TRIGGER trg_registration_log_update
AFTER UPDATE ON registrations
FOR EACH ROW
INSERT INTO registration_activity (student_id, session_id, action)
SELECT NEW.student_id, NEW.session_id,
       IF(NEW.status = 'Cancelled', 'Cancelled', 'Registered')
FROM DUAL
WHERE (NEW.status = 'Cancelled' AND OLD.status <> 'Cancelled')
   OR (NEW.status = 'Active' AND OLD.status <> 'Active');
 
 
-- ================================================================
-- PART 3: VIEW
-- Sessions that still have open seats.
-- ================================================================
CREATE VIEW available_exam_sessions AS
SELECT
    es.session_id,
    e.exam_name,
    e.subject,
    e.exam_level,
    es.session_date,
    es.session_time,
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
 
 
-- ================================================================
-- PART 4: QUICK CHECKS (shows that everything was built; safe to delete)
-- ================================================================
SHOW TABLES;
SHOW TRIGGERS;
SELECT * FROM registrations;
SELECT * FROM registration_activity ORDER BY activity_id;
SELECT * FROM available_exam_sessions;