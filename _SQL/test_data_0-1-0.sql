USE exam_registration;

-- campus
INSERT INTO campus (name, address, city, state, zip, location_phone)
	VALUES ('Charleston Campus', '6375 W Charleston Blvd', 'Las Vegas', 'NV', '89146', '(702) 651-5000');

-- room
INSERT INTO rooms (campus_id, building, room_num)
	VALUES (1, 'NUL', '000');

-- student
INSERT INTO users (first_name, last_name, email, password, role, created_at)
	VALUES ('John', 'Doe', '9999999999@student.csn.edu', '9999999999', 'Student', '2026-10-1 11:00:00');

-- proctor
INSERT INTO users (first_name, last_name, email, password, role, created_at)
	VALUES ('Jane', 'Doe', 'jDoe@csn.edu', '1111111111', 'Faculty', '2026-10-1 10:30:00');

-- exam
INSERT INTO exams (subject, exam_level, exam_name, description, created_at)
	VALUES ('CIT', '260', 'Systems Development and Design Midterm', 'Midterm covering Dr. Coombs''s textbook through chapter 8', '2026-10-1 10:00:00');

-- session
INSERT INTO exam_sessions (exam_id, room_id, proctor_id, exam_date, exam_time, capacity, created_at)
	VALUES (1, 1, 2, '2026-10-14', '18:00:00', 20, '2026-10-11 11:00:00');

-- registration
INSERT INTO registrations (student_ID, session_id, status, registered_at)
	VALUES (1, 1, 'Active', '2026-10-5 12:00:00');