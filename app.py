import os
import sqlite3
import datetime
import logging
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-key-please-change'
CORS(app)

# SQLite Configuration
DATABASE = 'ayo_fokus.db'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            DATABASE,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False # Allow multiple threads to use the same connection
        )
        g.db.row_factory = sqlite3.Row # Return rows as dict-like objects
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()
        logging.info("Database connection closed.")

def init_db():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        # Create tables if not exist (SQLite syntax)
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                meet_link TEXT NOT NULL,
                description TEXT,
                instructor_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instructor_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                class_id INTEGER,
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS student_status (
                student_id INTEGER,
                class_id INTEGER,
                is_in_meet BOOLEAN DEFAULT TRUE,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                PRIMARY KEY (student_id, class_id),
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                class_id INTEGER,
                event_type TEXT,
                message TEXT,
                source TEXT DEFAULT 'web',
                sync_id TEXT,
                original_timestamp TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS sync_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                class_id INTEGER,
                last_frontend_sync TIMESTAMP,
                last_backend_update TIMESTAMP,
                sync_lag_seconds INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            )
        ''')
        conn.commit()
        logging.info("Database initialized.")
    except sqlite3.Error as err:
        logging.error(f"Database initialization error: {err}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            c.close()
            conn.close()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            g.user_id = data['user_id']
            g.user_role = data['role']
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token!'}), 401
        return f(*args, **kwargs)
    return decorated

def is_dosen_pengajar(user_id, class_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT instructor_id FROM classes WHERE id = ?', (class_id,))
    row = c.fetchone()
    c.close()
    return row is not None and row['instructor_id'] == user_id

# Fungsi update_student_status ini tidak lagi digunakan secara langsung oleh log_monitoring
# karena heartbeat akan menjadi sumber utama update status.
# Namun, tetap dipertahankan jika ada bagian lain yang masih memanggilnya.
def update_student_status(student_id, class_id, is_in_meet, session_id=None):
    conn = get_db()
    c = conn.cursor()
    current_time = datetime.datetime.now() # SQLite TIMESTAMP format

    if session_id is None:
        c.execute('SELECT session_id FROM student_status WHERE student_id = ? AND class_id = ?', (student_id, class_id))
        existing = c.fetchone()
        session_id = existing['session_id'] if existing else None
        
    if session_id is None:
        session_id = f"auto_gen_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{student_id}"

    c.execute('''
        INSERT OR REPLACE INTO student_status (student_id, class_id, is_in_meet, last_activity, session_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (student_id, class_id, int(is_in_meet), current_time, session_id))
    conn.commit()
    c.close()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    if not username or not password or role not in ['mahasiswa', 'dosen']:
        return jsonify({'message': 'Invalid input'}), 400
    db = get_db()
    c = db.cursor()
    try:
        c.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                  (username, generate_password_hash(password), role))
        db.commit()
        return jsonify({'message': 'User registered'}), 201
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({'message': 'Username already exists'}), 409
    except Exception as e:
        db.rollback()
        logging.error(f"Error registering user: {e}")
        return jsonify({'message': f'Failed to register user: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'message': 'Invalid input'}), 400
    db = get_db()
    c = db.cursor()
    try:
        c.execute('SELECT id, password_hash, role FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            token = jwt.encode({
                'user_id': user['id'],
                'role': user['role'],
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            return jsonify({'token': token, 'role': user['role'], 'user_id': user['id']})
        return jsonify({'message': 'Invalid credentials'}), 401
    except Exception as e:
        logging.error(f"Error during login: {e}")
        return jsonify({'message': f'Login failed: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/classes', methods=['POST'])
@token_required
def create_class():
    if g.user_role != 'dosen':
        return jsonify({'message': 'Access denied'}), 403
    data = request.get_json()
    name = data.get('name')
    meet_link = data.get('meet_link')
    description = data.get('description')
    if not name or not meet_link:
        return jsonify({'message': 'Name and meet_link required'}), 400
    db = get_db()
    c = db.cursor()
    try:
        c.execute('INSERT INTO classes (name, meet_link, description, instructor_id) VALUES (?, ?, ?, ?)',
                  (name, meet_link, description, g.user_id))
        db.commit()
        return jsonify({'message': 'Class created'}), 201
    except Exception as e:
        db.rollback()
        logging.error(f"Error creating class: {e}")
        return jsonify({'message': f'Failed to create class: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/classes', methods=['GET'])
@token_required
def get_classes():
    db = get_db()
    c = db.cursor()
    try:
        # Modified query to always include instructor_name and handle roles
        c.execute('''
            SELECT c.id, c.name, c.meet_link, c.description, c.instructor_id, c.created_at,
                u.username AS instructor_name
            FROM classes c
            JOIN users u ON c.instructor_id = u.id
            WHERE (? = 'dosen' AND c.instructor_id = ?) OR (? = 'mahasiswa')
        ''', (g.user_role, g.user_id, g.user_role))
        classes = c.fetchall()
        return jsonify([dict(row) for row in classes])
    except Exception as e:
        logging.error(f"Error getting classes: {e}")
        return jsonify({'message': f'Failed to retrieve classes: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/classes/<int:class_id>', methods=['DELETE'])
@token_required
def delete_class(class_id):
    if g.user_role != 'dosen':
        return jsonify({'message': 'Access denied'}), 403
    if not is_dosen_pengajar(g.user_id, class_id):
        return jsonify({'message': 'Not owner of class'}), 403
    db = get_db()
    c = db.cursor()
    try:
        # Due to ON DELETE CASCADE, deleting the class will automatically delete
        # related entries in monitoring_logs, student_status, enrollments, and sync_status.
        c.execute('DELETE FROM classes WHERE id = ?', (class_id,))
        db.commit()
        logging.info(f"Class {class_id} and all related data deleted by instructor {g.user_id}")
        return jsonify({'message': 'Class deleted successfully.'}), 200
    except Exception as e:
        db.rollback()
        logging.error(f"Error deleting class {class_id}: {e}")
        return jsonify({'message': f'Failed to delete class: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/classes/<int:class_id>/clear_student_data', methods=['DELETE'])
@token_required
def clear_student_data_for_class(class_id):
    if g.user_role != 'dosen':
        return jsonify({'message': 'Access denied'}), 403
    if not is_dosen_pengajar(g.user_id, class_id):
        return jsonify({'message': 'Not owner of class'}), 403
    
    db = get_db()
    c = db.cursor()
    
    try:
        # Get student_ids enrolled in this class
        c.execute('SELECT student_id FROM enrollments WHERE class_id = ?', (class_id,))
        student_ids_in_class = [row['student_id'] for row in c.fetchall()]

        if not student_ids_in_class:
            # Return a success message even if no data to clear, as the intent is fulfilled
            return jsonify({'message': 'Tidak ada data mahasiswa atau log untuk dibersihkan di kelas ini.'}), 200

        # Delete monitoring logs for students in this class
        # Using a single query with IN clause for efficiency
        placeholders = ','.join(['?'] * len(student_ids_in_class))
        
        # Only execute if there are student_ids to avoid SQL syntax error with empty IN clause
        if student_ids_in_class:
            c.execute(f'DELETE FROM monitoring_logs WHERE class_id = ? AND student_id IN ({placeholders})', (class_id, *student_ids_in_class))
            c.execute(f'DELETE FROM student_status WHERE class_id = ? AND student_id IN ({placeholders})', (class_id, *student_ids_in_class))
            c.execute(f'DELETE FROM enrollments WHERE class_id = ? AND student_id IN ({placeholders})', (class_id, *student_ids_in_class))
            c.execute(f'DELETE FROM sync_status WHERE class_id = ? AND student_id IN ({placeholders})', (class_id, *student_ids_in_class))
        
        db.commit()
        logging.info(f"Cleared student data and logs for class_id {class_id} by instructor {g.user_id}")
        return jsonify({'message': 'Data mahasiswa dan log monitoring kelas berhasil dibersihkan.'}), 200
    except Exception as e:
        db.rollback()
        logging.error(f"Error clearing student data for class_id {class_id}: {e}")
        # Ensure a valid JSON response even on error
        return jsonify({'message': f'Terjadi kesalahan saat membersihkan data: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/classes/<int:class_id>/enroll', methods=['POST'])
@token_required
def enroll_class(class_id):
    if g.user_role != 'mahasiswa':
        return jsonify({'message': 'Access denied'}), 403
    db = get_db()
    c = db.cursor()
    try:
        c.execute('SELECT id FROM classes WHERE id = ?', (class_id,))
        if not c.fetchone():
            return jsonify({'message': 'Class not found'}), 404
        c.execute('SELECT id FROM enrollments WHERE student_id = ? AND class_id = ?', (g.user_id, class_id))
        if c.fetchone():
            return jsonify({'message': 'Already enrolled'}), 409
        c.execute('INSERT INTO enrollments (student_id, class_id) VALUES (?, ?)', (g.user_id, class_id))
        # Initial status is not in meet, but this will be overridden by heartbeat from desktop app
        # or updated by web app's own monitoring if desktop app is not running.
        update_student_status(g.user_id, class_id, False) 
        db.commit()
        return jsonify({'message': 'Enrolled successfully'})
    except Exception as e:
        db.rollback()
        logging.error(f"Error enrolling in class {class_id}: {e}")
        return jsonify({'message': f'Failed to enroll: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/class_detail/<int:class_id>', methods=['GET'])
@token_required
def class_detail(class_id):
    if g.user_role != 'dosen' or not is_dosen_pengajar(g.user_id, class_id):
        return jsonify({'message': 'Access denied'}), 403
    db = get_db()
    c = db.cursor()
    try:
        c.execute('SELECT * FROM classes WHERE id = ?', (class_id,))
        class_info = c.fetchone()
        if not class_info:
            return jsonify({'message': 'Class not found'}), 404
        c.execute('''
            SELECT u.id, u.username, e.enrolled_at, ss.is_in_meet, ss.last_activity, ss.session_id
            FROM enrollments e
            JOIN users u ON e.student_id = u.id
            LEFT JOIN student_status ss ON u.id = ss.student_id AND e.class_id = ss.class_id
            WHERE e.class_id = ?
            ORDER BY u.username ASC
        ''', (class_id,))
        students = c.fetchall()
        return jsonify({'class_info': dict(class_info), 'students': [dict(row) for row in students]})
    except Exception as e:
        logging.error(f"Error getting class detail for class {class_id}: {e}")
        return jsonify({'message': f'Failed to retrieve class details: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/monitoring/log', methods=['POST'])
@token_required
def log_monitoring():
    data = request.get_json()
    class_id = data.get('class_id')
    event_type = data.get('event_type')
    session_id = data.get('session_id')
    message = data.get('message', '')
    source = data.get('source', 'web')
    sync_id = data.get('sync_id', '')
    original_timestamp = data.get('original_timestamp', '')

    if not class_id or not event_type or not session_id:
        return jsonify({'message': 'class_id, event_type, and session_id required'}), 400

    db = get_db()
    c = db.cursor()
    try:
        c.execute('''
            INSERT INTO monitoring_logs
            (student_id, class_id, event_type, message, source, sync_id, original_timestamp, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (g.user_id, class_id, event_type, message, source, sync_id, original_timestamp, session_id))

        # Note: The student_status update logic based on enter/leave events is now primarily handled
        # by the /api/monitoring/heartbeat endpoint, which is called frequently by the desktop app.
        # This log_monitoring endpoint is for specific events, not continuous status.
        # However, if this endpoint is also used for web-based monitoring,
        # you might want to keep a simplified update here or ensure heartbeat covers it.
        # For now, we rely on heartbeat for continuous status.

        current_time = datetime.datetime.now() # SQLite TIMESTAMP format
        c.execute('''
            INSERT OR REPLACE INTO sync_status
            (student_id, class_id, last_backend_update)
            VALUES (?, ?, ?)
        ''', (g.user_id, class_id, current_time))

        db.commit()
        return jsonify({'message': 'Log recorded'})
    except Exception as e:
        db.rollback()
        logging.error(f"Error logging monitoring event: {e}")
        return jsonify({'message': f'Failed to record log: {str(e)}'}), 500
    finally:
        c.close()

@app.route('/api/synchronized_logs/<int:class_id>', methods=['GET'])
@token_required
def synchronized_logs(class_id):
    if g.user_role != 'dosen' or not is_dosen_pengajar(g.user_id, class_id):
        return jsonify({'message': 'Access denied'}), 403
    db = get_db()
    c = db.cursor()
    try:
        # Fetch all relevant log types for "Terdeteksi Keluar" count
        c.execute('''
            SELECT m.id, u.username, m.event_type, m.message, m.source, m.timestamp, m.original_timestamp, m.sync_id, m.student_id
            FROM monitoring_logs m
            JOIN users u ON m.student_id = u.id
            WHERE m.class_id = ?
            AND (m.event_type = 'warning_shown_sync' OR m.event_type = 'desktop_warning_shown')
            ORDER BY m.timestamp DESC
            LIMIT 500 
        ''', (class_id,))
        logs = c.fetchall()
        return jsonify([dict(row) for row in logs])
    except Exception as e:
        logging.error(f"Error getting synchronized logs for class {class_id}: {e}")
        return jsonify({'message': f'Failed to retrieve logs: {str(e)}'}), 500
    finally:
        c.close()

# cache sederhana di memori (opsional, bisa pakai DB SQLite juga)
student_status_cache = {}

@app.route('/api/monitoring/heartbeat', methods=['POST'])
@token_required
def monitoring_heartbeat():
    """
    Endpoint untuk menerima status dari monitoring.py
    """
    data = request.json
    student_id = g.user_id
    class_id = data.get("class_id")
    is_in_meet = data.get("is_in_meet", False)
    session_id = data.get("session_id")

    if not class_id:
        return jsonify({"error": "class_id required"}), 400

    # Simpan ke cache memori
    student_status_cache[(student_id, class_id)] = {
        "is_in_meet": bool(is_in_meet),
        "last_activity": datetime.datetime.now().isoformat(), # Menggunakan datetime.datetime.now()
        "session_id": session_id
    }
    logging.info(f"Heartbeat received for student {student_id} in class {class_id}: is_in_meet={is_in_meet}, session_id={session_id}")

    # Simpan juga ke SQLite:
    db = get_db()
    c = db.cursor()
    try:
        c.execute("""
            INSERT INTO student_status (student_id, class_id, is_in_meet, last_activity, session_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(student_id, class_id) DO UPDATE SET
                is_in_meet=excluded.is_in_meet,
                last_activity=excluded.last_activity,
                session_id=excluded.session_id
        """, (student_id, class_id, int(is_in_meet), datetime.datetime.now().isoformat(), session_id)) # Menggunakan datetime.datetime.now()
        db.commit()
        logging.debug(f"Student status for {student_id}/{class_id} updated in DB via heartbeat.")
    except Exception as e:
        db.rollback()
        logging.error(f"Error updating student status in DB from heartbeat for student {student_id}, class {class_id}: {e}")
        return jsonify({'message': f'Error updating heartbeat: {str(e)}'}), 500
    finally:
        c.close()

    return jsonify({"success": True, "status_updated": bool(is_in_meet)}), 200


@app.route('/api/student_current_status', methods=['GET'])
@token_required
def get_student_current_status():
    """
    Endpoint untuk dipanggil index.html agar tahu status terbaru
    """
    student_id = g.user_id
    class_id = request.args.get("class_id", type=int)

    if not class_id:
        return jsonify({"error": "class_id required"}), 400

    # Coba ambil dari cache dulu
    status = student_status_cache.get((student_id, class_id))
    if status:
        logging.debug(f"Status for {student_id}/{class_id} retrieved from cache: is_in_meet={status['is_in_meet']}.")
        return jsonify(status), 200

    # Kalau tidak ada di cache, coba ambil dari DB SQLite
    db = get_db()
    c = db.cursor()
    try:
        c.execute("""
            SELECT is_in_meet, last_activity, session_id
            FROM student_status
            WHERE student_id=? AND class_id=?
        """, (student_id, class_id))
        row = c.fetchone()

        if row:
            logging.debug(f"Status for {student_id}/{class_id} retrieved from DB: is_in_meet={bool(row['is_in_meet'])}.")
            # Simpan ke cache untuk request berikutnya
            student_status_cache[(student_id, class_id)] = {
                "is_in_meet": bool(row["is_in_meet"]),
                "last_activity": row["last_activity"],
                "session_id": row["session_id"]
            }
            return jsonify({
                "is_in_meet": bool(row["is_in_meet"]),
                "last_activity": row["last_activity"],
                "session_id": row["session_id"]
            }), 200
        else:
            logging.debug(f"No status found for {student_id}/{class_id} in DB. Returning default offline.")
            return jsonify({
                "is_in_meet": False,
                "last_activity": None,
                "session_id": None
            }), 200
    except Exception as e:
        logging.error(f"Error retrieving student status from DB for student {student_id}, class {class_id}: {e}")
        return jsonify({'message': f'Failed to retrieve student status: {str(e)}'}), 500
    finally:
        c.close()


if __name__ == '__main__':
    # For SQLite, we always ensure the database and tables are initialized.
    # This will create the 'ayo_fokus.db' file if it doesn't exist,
    # and create tables if they don't exist within that file.
    try:
        init_db()
        logging.info("SQLite database checked/initialized successfully.")
    except sqlite3.Error as err:
        logging.error(f"Failed to initialize SQLite database: {err}")
        # If DB initialization fails, the app cannot run, so re-raise or exit.
        raise

    logging.info("Starting Flask server...")
    print("=== Ayo Fokus Backend Started ===")
    app.run(host='0.0.0.0', port=5000, debug=False)
