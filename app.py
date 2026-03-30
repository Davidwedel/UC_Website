from flask import Flask, render_template, jsonify, session, request, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
import os
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps

load_dotenv('/var/www/unitedcenter/.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

DATABASE = '/var/www/unitedcenter/recordings.db'

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
        recordings = conn.execute(
            '''SELECT id, link, COALESCE(custom_title, title) AS title, received_at
               FROM recordings WHERE hidden = 0
               ORDER BY received_at DESC LIMIT 100'''
        ).fetchall()
    return render_template('index.html', recordings=recordings)

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
    return render_template('admin.html', recordings=recordings)

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

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
