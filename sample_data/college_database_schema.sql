-- ==========================================================
-- Smart Mentor Connect - the tables of ONE college's database
-- Every college has its own database (named smc_<college>), created by the apps
-- with these tables. This file is only a reference / for manual set-up: run it
-- inside an empty database of your own. It does not create or drop databases.
-- ==========================================================

CREATE TABLE teachers (
    Gmail VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    password VARCHAR(255) NOT NULL,
    advisor_dept VARCHAR(10),
    advisor_year INT,
    advisor_section VARCHAR(2),
    face_id VARCHAR(200)
);

CREATE TABLE students (
    roll_no VARCHAR(20) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL,
    department VARCHAR(10) NOT NULL,
    year INT NOT NULL CHECK (year BETWEEN 1 AND 4),
    section VARCHAR(2) NOT NULL,
    student_gmail VARCHAR(100),
    DOB DATE,
    mobile_no BIGINT
);

CREATE INDEX idx_student_group ON students(department, year, section);

CREATE TABLE exams (
    exam_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_name VARCHAR(50) NOT NULL UNIQUE,
    semester INT
);

CREATE TABLE courses (
    code VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(10) NOT NULL,      -- 'ALL' = common to every department
    semester INT NOT NULL,
    credits INT NOT NULL DEFAULT 3
);

CREATE TABLE marks (
    roll_no VARCHAR(20) NOT NULL,
    year INT NOT NULL,
    exam_id INT NOT NULL,
    subject VARCHAR(20) NOT NULL,         -- courses.code
    marks INT DEFAULT 0,
    PRIMARY KEY (roll_no, exam_id, subject),
    FOREIGN KEY (roll_no) REFERENCES students(roll_no) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE ON UPDATE CASCADE,
    CHECK (marks BETWEEN 0 AND 100 OR marks IS NULL)
);

CREATE INDEX idx_marks_subject ON marks(subject);
CREATE INDEX idx_marks_exam ON marks(exam_id);

CREATE TABLE Admin (
    Gmail VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    password VARCHAR(255) NOT NULL,
    face_id VARCHAR(200)
);

CREATE TABLE attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no VARCHAR(20) NOT NULL,
    department VARCHAR(10) NOT NULL,
    year INT NOT NULL,
    section VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    status VARCHAR(10) NOT NULL,          -- 'present' | 'absent' | 'leave'
    marked_by VARCHAR(120),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_attendance_student_day UNIQUE (roll_no, date)
);

CREATE INDEX idx_attendance_group ON attendance(department, year, section, date);
