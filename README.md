# Church Recordings Website

Automatically display church recording links from email on a public website.

## Features

- ✅ Public website to view and access church recordings
- ✅ Automatic email monitoring with IMAP
- ✅ Extracts listentochurch.com links from emails
- ✅ Rate limiting to prevent abuse
- ✅ Secure configuration with environment variables
- ✅ SQLite database for storage
- ✅ Responsive design

## Security Features

- Rate limiting (500 requests/day, 100 requests/hour per IP)
- SQL injection protection via parameterized queries
- Environment variables for sensitive credentials
- Production-ready configuration
- No debug mode in production

## Setup Instructions

### 1. Install Python Dependencies

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Email Settings

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your email credentials:
```bash
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_app_specific_password
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
CHECK_INTERVAL=300
```

**For Gmail users:**
1. Enable 2-factor authentication on your Google account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the App Password (not your regular password) in EMAIL_PASSWORD

**For other email providers:**
- Update IMAP_SERVER and IMAP_PORT accordingly
- Common IMAP servers:
  - Outlook/Hotmail: `imap-mail.outlook.com:993`
  - Yahoo: `imap.mail.yahoo.com:993`
  - iCloud: `imap.mail.me.com:993`

### 3. Initialize Database

```bash
python app.py
```

This will create the `recordings.db` SQLite database. Stop it with Ctrl+C.

### 4. Start Email Monitor (Background Process)

```bash
python email_monitor.py &
```

Or use `screen` or `tmux` for persistent sessions:
```bash
screen -S email_monitor
python email_monitor.py
# Press Ctrl+A, then D to detach
```

### 5. Start Web Server

**Development:**
```bash
python app.py
```

**Production (recommended):**
```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### 6. Access Website

Open browser: `http://localhost:5000`

## Production Deployment

### Using systemd (Linux)

Create `/etc/systemd/system/church-recordings-web.service`:
```ini
[Unit]
Description=Church Recordings Web Server
After=network.target

[Service]
User=your_user
WorkingDirectory=/path/to/streamwebsite
Environment="PATH=/path/to/streamwebsite/venv/bin"
EnvironmentFile=/path/to/streamwebsite/.env
ExecStart=/path/to/streamwebsite/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/church-recordings-email.service`:
```ini
[Unit]
Description=Church Recordings Email Monitor
After=network.target

[Service]
User=your_user
WorkingDirectory=/path/to/streamwebsite
Environment="PATH=/path/to/streamwebsite/venv/bin"
EnvironmentFile=/path/to/streamwebsite/.env
ExecStart=/path/to/streamwebsite/venv/bin/python email_monitor.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start services:
```bash
sudo systemctl enable church-recordings-web
sudo systemctl enable church-recordings-email
sudo systemctl start church-recordings-web
sudo systemctl start church-recordings-email
```

### Using Nginx with SSL/TLS (Highly Recommended)

Install nginx and certbot:
```bash
sudo apt install nginx certbot python3-certbot-nginx
```

Configure nginx (`/etc/nginx/sites-available/church-recordings`):
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site and get SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/church-recordings /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d your-domain.com
```

## File Structure

```
streamwebsite/
├── app.py                  # Flask web application
├── email_monitor.py        # Email monitoring script
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (create from .env.example)
├── .env.example           # Example environment configuration
├── .gitignore             # Git ignore file
├── recordings.db          # SQLite database (auto-created)
├── templates/
│   └── index.html         # Main website template
└── static/
    └── css/
        └── style.css      # Website styles
```

## Troubleshooting

### Email not connecting
- Check EMAIL_ADDRESS and EMAIL_PASSWORD in .env
- For Gmail, ensure you're using an App Password
- Check firewall allows outbound connections on port 993
- Try running `python email_monitor.py` to see detailed error messages

### Website not accessible
- Check if Flask is running: `ps aux | grep python`
- Verify port 5000 is not blocked by firewall
- Check logs for errors

### Links not appearing
- Verify email_monitor.py is running
- Check database: `sqlite3 recordings.db "SELECT * FROM recordings;"`
- Ensure emails contain listentochurch.com links in the expected format

## Maintenance

### View logs (systemd)
```bash
sudo journalctl -u church-recordings-web -f
sudo journalctl -u church-recordings-email -f
```

### Backup database
```bash
cp recordings.db recordings.db.backup
```

### Clear old recordings
```bash
sqlite3 recordings.db "DELETE FROM recordings WHERE received_at < date('now', '-90 days');"
```

## Support

For issues or questions, check:
- Python version: 3.8 or higher required
- Database permissions: ensure write access to recordings.db
- Network connectivity: IMAP and HTTP ports open
