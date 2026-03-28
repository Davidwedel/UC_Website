from flask import Flask, render_template, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Rate limiting to prevent abuse
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

DATABASE = 'recordings.db'

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
        conn.commit()

@app.route('/')
@limiter.limit("60 per minute")
def index():
    with get_db() as conn:
        recordings = conn.execute(
            'SELECT * FROM recordings ORDER BY received_at DESC LIMIT 100'
        ).fetchall()
    return render_template('index.html', recordings=recordings)

@app.route('/api/recordings')
@limiter.limit("30 per minute")
def get_recordings():
    with get_db() as conn:
        recordings = conn.execute(
            'SELECT * FROM recordings ORDER BY received_at DESC LIMIT 100'
        ).fetchall()
    return jsonify([dict(r) for r in recordings])

if __name__ == '__main__':
    init_db()
    # For production: use gunicorn with nginx and SSL/TLS
    app.run(host='0.0.0.0', port=5000, debug=False)
