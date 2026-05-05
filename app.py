from flask import Flask, render_template, jsonify, session, request, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import re
import sqlite3
import os
import uuid
from collections import OrderedDict
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps
from werkzeug.utils import secure_filename

_DAY_PREFIX = re.compile(
    r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+',
    re.IGNORECASE
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
SITE_NAME = os.environ.get('SITE_NAME', 'Church Recordings')

@app.context_processor
def inject_site_name():
    return dict(site_name=SITE_NAME)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

DATABASE = os.path.join(BASE_DIR, 'recordings.db')

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'recordings')
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'ogg', 'aac', 'flac'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT NOT NULL,
                title TEXT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        for col, definition in [('hidden', 'INTEGER NOT NULL DEFAULT 0'),
                                 ('custom_title', 'TEXT')]:
            try:
                conn.execute(f'ALTER TABLE recordings ADD COLUMN {col} {definition}')
            except sqlite3.OperationalError:
                pass
        conn.commit()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
@limiter.limit("60 per minute")
def index():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT id, link, COALESCE(custom_title, title) AS title, received_at
               FROM recordings WHERE hidden = 0
               ORDER BY received_at DESC LIMIT 100'''
        ).fetchall()

    groups = OrderedDict()
    for row in rows:
        rec = dict(row)
        try:
            dt = datetime.fromisoformat(rec['received_at'])
            date_key = dt.date()
            date_label = dt.strftime('%A, %B %-d, %Y')
        except (ValueError, TypeError):
            date_key = 'unknown'
            date_label = 'Unknown Date'
        rec['display_title'] = _DAY_PREFIX.sub('', rec['title']) if rec['title'] else rec['title']
        if date_key not in groups:
            groups[date_key] = {'date_label': date_label, 'recordings': []}
        groups[date_key]['recordings'].append(rec)

    grouped = list(groups.values())
    for group in grouped:
        group['recordings'].sort(key=lambda r: r['received_at'] or '')

    return render_template('index.html', grouped_recordings=grouped)

@app.route('/api/recordings')
@limiter.limit("30 per minute")
def get_recordings():
    with get_db() as conn:
        recordings = conn.execute(
            '''SELECT id, link, COALESCE(custom_title, title) AS title, received_at
               FROM recordings WHERE hidden = 0
               ORDER BY received_at DESC LIMIT 100'''
        ).fetchall()
    return jsonify([dict(r) for r in recordings])

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def admin_login():
    error = None
    if request.method == 'POST':
        if ADMIN_PASSWORD and request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin'))
        error = 'Incorrect password.'
    return render_template('login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    with get_db() as conn:
        recordings = conn.execute(
            '''SELECT id, link, title, custom_title, hidden, received_at
               FROM recordings ORDER BY received_at DESC LIMIT 100'''
        ).fetchall()
    return render_template('admin.html', recordings=recordings,
                           today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/admin/recording/<int:id>/title', methods=['POST'])
@login_required
def admin_update_title(id):
    custom_title = request.form.get('title', '').strip() or None
    with get_db() as conn:
        conn.execute('UPDATE recordings SET custom_title = ? WHERE id = ?', (custom_title, id))
        conn.commit()
    return redirect(url_for('admin'))

@app.route('/admin/recording/<int:id>/toggle', methods=['POST'])
@login_required
def admin_toggle_hidden(id):
    with get_db() as conn:
        conn.execute('UPDATE recordings SET hidden = NOT hidden WHERE id = ?', (id,))
        conn.commit()
    return redirect(url_for('admin'))

@app.route('/admin/recording/<int:id>/delete', methods=['POST'])
@login_required
def admin_delete(id):
    with get_db() as conn:
        row = conn.execute('SELECT link FROM recordings WHERE id = ?', (id,)).fetchone()
        if row:
            link = row['link']
            if link and link.startswith('/static/uploads/'):
                file_path = os.path.join(BASE_DIR, link.lstrip('/'))
                if os.path.exists(file_path):
                    os.remove(file_path)
            conn.execute('DELETE FROM recordings WHERE id = ?', (id,))
            conn.commit()
    return redirect(url_for('admin'))


@app.route('/admin/upload', methods=['POST'])
@login_required
def admin_upload():
    file = request.files.get('audio_file')
    if not file or file.filename == '' or not allowed_file(file.filename):
        return redirect(url_for('admin'))

    safe_name = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    file.save(os.path.join(UPLOAD_FOLDER, safe_name))

    link = f"/static/uploads/recordings/{safe_name}"
    title = request.form.get('title', '').strip() or None
    raw_date = request.form.get('recording_date', '').strip()
    try:
        received_at = datetime.strptime(raw_date, '%Y-%m-%d')
    except (ValueError, TypeError):
        received_at = datetime.now()

    with get_db() as conn:
        conn.execute(
            'INSERT INTO recordings (link, title, received_at, hidden) VALUES (?, ?, ?, 0)',
            (link, title, received_at)
        )
        conn.commit()
    return redirect(url_for('admin'))


@app.errorhandler(413)
def file_too_large(e):
    return redirect(url_for('admin'))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
