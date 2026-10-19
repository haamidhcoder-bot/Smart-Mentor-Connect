<p align="center"><img src="teacher_side/static/images/smart-mentor-connect.jpg" alt="Smart Mentor Connect logo" width="140"></p>

# Smart Mentor Connect

Smart Mentor Connect is a web-based student management and performance platform for an **engineering college**. It manages students by **department, year and section**, faculty who act as **class advisors (mentors)**, **courses with credits**, semester exams, marks with **grades and GPA**, and attendance with a **75% shortage check**.

## Features

* Faculty (class advisor) dashboard: each advisor manages one department / year / section
* Management (college office) dashboard
* **Many colleges in one deployment:** every college has its own database; people choose their college on every login page, and new colleges can register themselves
* Student portal (read-only: own marks, grades, GPA, attendance, section rank)
* Students identified by alphanumeric roll / register number (e.g. `21CS001`)
* Departments, years 1-4, sections (all configurable)
* Courses with codes, semesters and credits (Courses page on the management side)
* Semester exams (Internal 1, Internal 2, Model Exam, End Semester for Sem 1-8, created automatically)
* Marks out of 100 with a configurable pass mark (default 50), grades and a credit-weighted GPA
* Attendance with an attendance-shortage panel (default minimum 75%) and per-student "classes needed / can still miss" on the student portal
* Section leaderboard and performance graphs
* CSV import / export of students (adds and updates, never deletes)
* End-of-year promotion with graduating students archived to CSV
* User authentication, including Face ID login
* AI-assisted student data interaction
* Email functionality
* Application logging

## Technologies Used

### Backend

* Python
* Flask
* MySQL
* SQLAlchemy

### Frontend

* HTML
* CSS
* JavaScript
* Font Awesome

### Libraries and Tools

* Pandas, NumPy
* Matplotlib, Seaborn
* OpenCV, Pillow
* MySQL Connector / PyMySQL
* Google Generative AI (Gemini)
* Git
* GitHub

## Project Structure

```text
Smart-Mentor-Connect/
│
├── teacher_side/
│   ├── app/
│   │   ├── routes/
│   │   └── __init__.py
│   ├── templates/
│   ├── static/
│   └── run_teacher.py
│
├── management_side/
│   ├── app/
│   │   ├── routes/
│   │   └── __init__.py
│   ├── templates/
│   ├── static/
│   └── run_management.py
│
├── student_side/
│   ├── app/
│   ├── templates/
│   ├── static/
│   └── run_student.py
│
├── shared/
│   ├── settings.py        (reads environment variables)
│   ├── app_factory.py
│   ├── extensions.py
│   ├── models/
│   ├── services/
│   └── utils/
│
├── sample_data/
├── tests/
│   ├── conftest.py
│   └── test_smart_mentor_connect_full.py
├── requirements.txt
├── create_databases.py    (optional helper: registers a new empty college)
├── .env.example
├── .gitignore
└── README.md
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/haamidhcoder-bot/Smart-Mentor-Connect.git
```

### 2. Navigate to the project directory

```bash
cd Smart-Mentor-Connect
```

### 3. Create a virtual environment

```bash
python -m venv .venv
```

### 4. Activate the virtual environment

On Windows:

```bash
.venv\Scripts\activate
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

### 5. Install the required dependencies

```bash
pip install -r requirements.txt
```

## Database Setup

Smart Mentor Connect uses MySQL as its database.

All three applications create what they need on startup and never drop existing data:

* a small **registry database** (`smartmentor_master`, change it with `MASTER_DATABASE`) that only lists the colleges, and
* **one database per college** (`smc_<college name>`), holding that college's students, teachers, administrators, courses, exams, marks and attendance.

The MySQL user therefore needs permission to `CREATE DATABASE`. An old installation with a single `collegedb` database is registered automatically as the college **Default College**, so existing data keeps working.

### Colleges and logins

* The **management, teacher and student login pages all have a College dropdown** (the choice is remembered in the browser). Roll numbers and e-mail addresses only have to be unique inside one college, and a person only ever sees their own college's data.
* **Forgot password** (teacher / management) also asks for the college.
* **Registering a new college:** on the management side open **Register**, choose *Register a new college*, enter the college name, your e-mail and a password. After the OTP e-mail (sent to the owner accounts, `ADMIN1_EMAIL` / `ADMIN2_EMAIL`) is verified, the college and its own database are created and you become its first administrator. Choose *My college is already registered* to add another administrator to an existing college. Teachers and students are then added by the college's administrators, as before.
* You can also register an empty college from the command line: `python create_databases.py "My College Name"`.
* The college name is shown in the sidebar once logged in.

### Configuration (environment variables)

There is no `config.py`. Copy `.env.example` to `.env` (git-ignored) and fill it in, or export the variables in your shell. Real environment variables take priority over `.env`.

| Variable | Used by | Purpose |
|---|---|---|
| `MYSQL_PASSWORD` (`MYSQL_HOST`, `MYSQL_USER` optional) | all | MySQL login (needs `CREATE DATABASE` permission) |
| `MASTER_DATABASE` (`smartmentor_master`) | all | Name of the registry database that lists the colleges |
| `TEACHER_SECRET_KEY` | teacher side | Flask session key |
| `MANAGEMENT_SECRET_KEY` | management side | Flask session key (use a different value) |
| `STUDENT_SECRET_KEY` | student side | Flask session key (use a different value) |
| `GEMINI_API_KEY` | teacher side | AI assistant |
| `ADMIN1_EMAIL`, `ADMIN1_APP_PASSWORD` | both | Gmail sender for OTP and result emails |
| `ADMIN2_EMAIL`, `ADMIN2_APP_PASSWORD` | both | Gmail account that receives OTPs / sends log files |
| `TEACHER_PORT` (8000), `MANAGEMENT_PORT` (5000), `STUDENT_PORT` (9000), `FLASK_DEBUG` (0) | optional | Run settings |
| `DEPARTMENTS` (`CSE,IT,AIDS,ECE,EEE,MECH,CIVIL`) | all | Department codes offered by the college |
| `SECTIONS` (`A,B,C,D`), `MAX_YEAR` (4) | all | Sections per department/year and length of the degree |
| `PASS_MARK` (50) | all | Minimum marks out of 100 to pass a course |
| `MIN_ATTENDANCE` (75) | all | Attendance percentage below which a student is flagged |
| `SESSION_COOKIE_SECURE` (0) | all | Set to `1` when serving over HTTPS so cookies are never sent over plain HTTP |
| `REMEMBER_DAYS` (7) | all | How long "Remember me" keeps a person logged in |
| `CSRF_DISABLED` (0) | tests only | Turns CSRF checking off; never set it in production |

(Optional) Create two demo colleges with sample data:

```bash
python sample_data/populate_college_database.py --yes   # (re)creates the two demo colleges and fills them with demo data
```

It registers **Demo Engineering College** and **Sample Institute of Technology**, each with its own database and the demo logins `admin@example.com` / `demo-advisor@example.com` (password `pass@123`). Pick the college on the login page. Other colleges you registered are not touched.

## Running the Application

Smart Mentor Connect is split into three separate Flask applications that run independently and share the same databases (the college registry plus each college's own database). Activate the virtual environment first, then start each side from the project root.

Management side:

```bash
python management_side/run_management.py
```

Teacher side:

```bash
python teacher_side/run_teacher.py
```

Student side:

```bash
python student_side/run_student.py
```

Students choose their **college** and sign in with their **roll / register number and date of birth** (the database has no student passwords). After 5 wrong attempts for a roll number (in that college), that roll number is locked for 5 minutes. The student side is read-only and only ever shows the logged-in student's own records.

The applications can then be accessed at:

```text
Management side: http://127.0.0.1:5000
Teacher side:     http://127.0.0.1:8000
Student side:     http://127.0.0.1:9000
```

### Deploying

Each side has a `wsgi.py`. Example (run one per side, behind nginx/HTTPS, with `SESSION_COOKIE_SECURE=1`):

```bash
gunicorn --chdir management_side -w 1 --threads 4 -b 127.0.0.1:5000 wsgi:app
gunicorn --chdir teacher_side    -w 1 --threads 4 -b 127.0.0.1:8000 wsgi:app
gunicorn --chdir student_side    -w 1 --threads 4 -b 127.0.0.1:9000 wsgi:app
```

Keep `-w 1`: the e-mail progress state is held in memory. Add `gunicorn` to your environment (`pip install gunicorn`).

## Testing

Smart Mentor Connect includes a pytest suite (`tests/`) covering the shared decorators, teacher-side, management-side and student-side routes, grading and attendance rules, CSV import and promotion. It runs against isolated Flask apps (mocked, or a throw-away SQLite database), so it does not touch your real college databases, email account, Face ID files, or the AI API.

Install pytest (included in `requirements.txt`) and run the suite from the project root:

```bash
pytest -q
```

All tests should pass on a clean checkout.

## How the college structure works

* A **student** belongs to a department, a year (1-4) and a section, and has a roll number that never changes.
* A **faculty member** is the **class advisor** of exactly one department / year / section and can only see and edit that group.
* **Courses** (code, name, department, semester, credits) are added on the management side under *Courses*. Use department `ALL` for courses taken by every department (e.g. Mathematics I). Year 1 studies semesters 1-2, year 2 semesters 3-4, and so on.
* **Exams** are per semester (`Sem 5 - Internal 1`, ...). Marks from earlier semesters are kept when students move up a year.
* A teacher picks an exam, then a course of that exam's semester, and enters marks 0-100 (0 means "not entered yet").
* **Grades:** 90+ O (10), 80+ A+ (9), 70+ A (8), 60+ B+ (7), 55+ B (6), 50+ C (5), below the pass mark F (0). Edit `GRADE_SCALE` in `shared/services/grading.py` to match your university. GPA is credit-weighted.
* **Attendance** is counted per academic year (it starts afresh after promotion). Students below `MIN_ATTENDANCE` are listed to the advisor and the office, and the student sees how many classes they need to attend.
* **Promotion** (management side > More > Promote) moves everyone up one year. Final-year students are written to `archive/<college>/graduated_students_*.csv` and `archive/<college>/graduated_marks_*.csv`, then removed.

### Setting up a new college

1. Start the management side and open **Register** > *Register a new college* (or use `python create_databases.py "College name"`), verify the OTP, and log in with your college selected.
2. Set `DEPARTMENTS` (and `SECTIONS`, `PASS_MARK`, ...) in `.env` if the defaults don't fit.
3. Add each department's courses under **Courses**.
4. Add faculty under **Faculty** and assign each one a department / year / section.
5. Import students from CSV (or add them one by one).

## CSV Import

Choose the department, year and section on the import page, then upload a CSV with a header row. `roll_no` and `student_name` are required; the other columns may be blank. DOB can be `YYYY-MM-DD` or `DD/MM/YYYY`.

```csv
roll_no,student_name,student_gmail,DOB,mobile_no
21CS001,Asha Kumar,asha@example.com,2004-08-09,9722646238
21CS002,Bala Singh,bala@example.com,2004-11-02,7214475883
```

Existing roll numbers in the same group are updated, new ones are added, nothing is deleted. A roll number that already belongs to another department, year or section is rejected and the whole file is rolled back.

## Security

Smart Mentor Connect follows security practices such as:

* Session-based authentication
* Protected routes
* Input validation
* CSV validation
* Secure credential management
* Prevention of unauthorized access
* CSRF tokens on every form and on all POST requests
* Login throttling (5 failed attempts locks that account for 5 minutes)
* Delete actions are POST-only and ask for confirmation
* Security headers and cookies flagged `HttpOnly` / `SameSite=Lax`

Sensitive information such as passwords, API keys, and secret keys should be stored outside the source code.

## AI Assistance

Smart Mentor Connect includes an AI-assisted interface for interacting with student data and obtaining useful information from the college database.

## Email Functionality

The application supports email functionality for system-related communication, including OTP-based password resets, sending generated files, and notifications.

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a new branch:

```bash
git checkout -b feature/your-feature
```

3. Make your changes.
4. Commit your changes:

```bash
git commit -m "Add your feature"
```

5. Push the branch:

```bash
git push origin feature/your-feature
```

6. Create a Pull Request.

## License

This project is licensed under the MIT License.

## Author

**Haamidh Mohideen**

GitHub: `https://github.com/haamidhcoder-bot`

## Deployment

See [DEPLOY_RENDER.md](DEPLOY_RENDER.md) for deploying all three sites on Render with `render.yaml`.
