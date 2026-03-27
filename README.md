# IHC Attendance Tracker

Run the full app locally with the Python backend and SQLite database:

```bash
chmod +x start-server.sh
./start-server.sh
```

Then open:

[http://localhost:8000](http://localhost:8000)

To open it on your phone on the same Wi-Fi:

1. Start the server:

```bash
./start-server.sh
```

2. Find your Mac's local IP address:

```bash
ifconfig | grep "inet "
```

3. On your phone, open:

```text
http://YOUR_LOCAL_IP:8000
```

Example:

```text
http://192.168.1.25:8000
```

The app uses:

- local SQLite at `attendance.db` when `DATABASE_URL` is not set
- Render Postgres automatically when `DATABASE_URL` is provided in production

Default admin login:

- username: `admin`
- password: `admin123`

New full-app features:

- secure password change for the logged-in admin
- multiple admin users stored in SQLite
- monthly dashboard summary
- roster search, team filter, and status filter

You can also start it without the script:

```bash
python3 server.py
```

Online deployment:

This project now includes [render.yaml](/Users/sangeeth/Documents/New%20project%204/render.yaml) for Render deployment.

This setup is now prepared specifically for Render Postgres:

- [render.yaml](/Users/sangeeth/Documents/New%20project%204/render.yaml) provisions both a web service and a Postgres database
- [requirements.txt](/Users/sangeeth/Documents/New%20project%204/requirements.txt) installs `psycopg`
- [server.py](/Users/sangeeth/Documents/New%20project%204/server.py) uses `DATABASE_URL` automatically in production

Basic Render steps:

1. Push this project to GitHub.
2. In Render, create a new Blueprint and connect that GitHub repo.
3. Render will create:
   - a Postgres database named `ihc-attendance-db`
   - a web service named `ihc-attendance-tracker`
4. Render will inject `DATABASE_URL` automatically.
5. After deploy, Render gives you a public URL like:

```text
https://your-app-name.onrender.com
```
