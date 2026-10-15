-- ==========================================================
-- COMMON.SQL
-- Content identical in both:
--   school_database_schema_updated.sql
--   school_database_schema_updated_m.sql
-- ==========================================================

DROP DATABASE IF EXISTS schooldb;
CREATE DATABASE  schooldb;

USE schooldb;


-- ==========================================================
-- Teachers
-- ==========================================================

CREATE TABLE teachers (
    Gmail VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    password VARCHAR(255) NOT NULL,
    class_teacher INT,
    class_teacher_sec CHAR(1),
    face_id char(200)
);

-- ==========================================================
-- Students (common columns only — see differences.sql for
-- columns that exist in only one file)
-- ==========================================================

CREATE TABLE students (
    roll_no INT PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL,
    class INT NOT NULL CHECK (class BETWEEN 1 AND 12),
    section CHAR(1) NOT NULL CHECK (section IN ('A','B','C')),
    student_gmail CHAR(100) CHECK (student_gmail LIKE '%@gmail.com'),
    DOB DATE,                 
    mobile_no BIGINT          
);

-- ==========================================================
-- Exams
-- ==========================================================

CREATE TABLE exams (
    exam_id INT AUTO_INCREMENT PRIMARY KEY,
    exam_name VARCHAR(50) NOT NULL UNIQUE
);

-- ==========================================================
-- Marks
-- ==========================================================

CREATE TABLE marks (
    roll_no INT NOT NULL,
    class INT NOT NULL,
    exam_id INT NOT NULL,
    subject VARCHAR(30) NOT NULL,
    marks INT DEFAULT 0,

    PRIMARY KEY (roll_no, exam_id, subject),

    FOREIGN KEY (roll_no)
        REFERENCES students(roll_no)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (exam_id)
        REFERENCES exams(exam_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CHECK (marks BETWEEN 0 AND 100 OR marks IS NULL)
);

-- ==========================================================
-- Useful Indexes
-- ==========================================================

CREATE INDEX idx_student_class
ON students(class, section);

CREATE INDEX idx_marks_subject
ON marks(subject);

CREATE INDEX idx_marks_exam
ON marks(exam_id);

-- ==========================================================
-- Admin
-- ==========================================================

CREATE TABLE Admin (
    Gmail VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100),
    password VARCHAR(255) NOT NULL,
    face_id CHAR(200)
);

-- ==========================================================
-- Attendance
-- ==========================================================

CREATE TABLE attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no INT NOT NULL,
    class_value INT NOT NULL,
    section VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    status VARCHAR(10) NOT NULL,          -- 'present' | 'absent' | 'leave'
    marked_by VARCHAR(120),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_attendance_student_day UNIQUE (roll_no, class_value, section, date)
);