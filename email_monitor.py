import imaplib
import email
from email.header import decode_header
import sqlite3
import re
import time
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Email configuration from environment variables
EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
IMAP_SERVER = os.environ.get('IMAP_SERVER', 'imap.gmail.com')
IMAP_PORT = int(os.environ.get('IMAP_PORT', '993'))
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '300'))  # 5 minutes default

DATABASE = '/var/www/unitedcenter/recordings.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database if it doesn't exist"""
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

def extract_church_links(text):
    """Extract listentochurch.com links from email text"""
    pattern = r'https?://listentochurch\.com/signed/recording/\d+\?signature=[a-f0-9]+'
    links = re.findall(pattern, text)
    return links

def get_email_body(msg):
    """Extract email body from message"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" or content_type == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"Error decoding part: {e}")
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"Error decoding message: {e}")
    return body

def save_recording(link, title=None, received_at=None):
    """Save recording link to database if it doesn't exist"""
    if received_at is None:
        received_at = datetime.now()

    with get_db() as conn:
        # Check if link already exists
        existing = conn.execute('SELECT id FROM recordings WHERE link = ?', (link,)).fetchone()
        if not existing:
            conn.execute(
                'INSERT INTO recordings (link, title, received_at) VALUES (?, ?, ?)',
                (link, title, received_at)
            )
            conn.commit()
            print(f"New recording saved: {link}")
            return True
        else:
            print(f"Recording already exists: {link}")
            return False

def check_email():
    """Check email for new recording links"""
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("ERROR: EMAIL_ADDRESS and EMAIL_PASSWORD must be set in environment variables")
        return

    try:
        # Connect to email server
        print(f"Connecting to {IMAP_SERVER}...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        print("Login successful")

        # Select inbox
        mail.select('inbox')

        # Search for all emails from ListenToChurch from the last day
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%d-%b-%Y')
        status, messages = mail.search(None, f'(FROM "ListenToChurch" SINCE {yesterday})')

        if status != 'OK':
            print("No new messages")
            mail.logout()
            return

        email_ids = messages[0].split()
        print(f"Found {len(email_ids)} unread email(s)")

        for email_id in email_ids:
            # Fetch email
            status, msg_data = mail.fetch(email_id, '(RFC822)')

            if status != 'OK':
                continue

            # Parse email
            msg = email.message_from_bytes(msg_data[0][1])

            # Get subject
            subject = decode_header(msg['Subject'])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode('utf-8', errors='ignore')

            # Get email date and convert to local time
            email_date = None
            if msg['Date']:
                try:
                    email_date = email.utils.parsedate_to_datetime(msg['Date'])
                    # Convert to local time
                    if email_date.tzinfo is not None:
                        email_date = email_date.astimezone()
                except Exception as e:
                    print(f"Error parsing email date: {e}")

            print(f"Processing email: {subject}")

            # Check if email was received on Sunday
            if email_date is None or email_date.weekday() != 6:  # 6 = Sunday
                print("Email not received on Sunday, skipping...")
                continue

            # Determine service type based on time
            hour = email_date.hour
            minute = email_date.minute
            time_minutes = hour * 60 + minute

            service_title = None
            if 10 * 60 <= time_minutes < 10 * 60 + 45:  # 10:00 - 10:45
                service_title = "Sunday School Opening"
            elif 10 * 60 + 45 <= time_minutes < 14 * 60:  # 10:45 - 14:00
                service_title = "Sunday Morning Service"
            elif 18 * 60 + 30 <= time_minutes < 23 * 60:  # 18:30 - 23:00
                service_title = "Sunday Evening Service"
            else:
                print(f"Email received at {email_date.strftime('%H:%M')} - outside service times, skipping...")
                continue

            # Get email body
            body = get_email_body(msg)

            # Extract church links
            links = extract_church_links(body)

            if links:
                print(f"Found {len(links)} recording link(s) - {service_title}")
                for link in links:
                    save_recording(link, service_title, email_date)
            else:
                print("No recording links found in this email")

        mail.logout()
        print("Email check completed")

    except imaplib.IMAP4.error as e:
        print(f"IMAP error: {e}")
    except Exception as e:
        print(f"Error checking email: {e}")

def main():
    """Main loop - continuously check for new emails"""
    # Initialize database
    init_db()

    print("Email monitor started")
    print(f"Checking email: {EMAIL_ADDRESS}")
    print(f"IMAP server: {IMAP_SERVER}:{IMAP_PORT}")
    print(f"Check interval: {CHECK_INTERVAL} seconds")
    print("-" * 50)

    while True:
        try:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new emails...")
            check_email()
            print(f"Sleeping for {CHECK_INTERVAL} seconds...")
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\nEmail monitor stopped by user")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            print(f"Retrying in {CHECK_INTERVAL} seconds...")
            time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
