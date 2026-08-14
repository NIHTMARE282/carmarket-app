# CarMarket Dealership Platform

A serious, responsive dealership web app built with FastAPI + SQLite + vanilla HTML/CSS/JS.

## Included

- Public inventory with search and categories
- SUVs, Sedans, Trucks, Sports Cars, Luxury and Other categories
- Vehicle details/gallery
- Customer registration and login
- Customer-to-dealership support messaging
- Admin login
- Admin dashboard
- Add/edit/delete vehicles
- Upload multiple vehicle photos directly from phone/PC
- Image URL support
- Live admin message updates through WebSockets
- Customer list
- Vehicle status support
- No online payment processing; customers contact support instead
- SQLite database for simple deployment

## Local setup

Python 3.10+ recommended.

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set a strong admin password and secret key.

Run:

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/admin-login

## Default local admin

If you do not create a `.env`, the development seed uses:

- username/email: `admin`
- password: `ChangeMe_123!`

CHANGE THIS before production.

## Hostinger

This project uses Python/FastAPI. Hostinger currently states that Python applications require a VPS with root access. Do not upload this as a normal static site and expect FastAPI to run there.

Recommended production layout:

- Hostinger VPS
- Ubuntu
- Python virtual environment
- Uvicorn behind Nginx
- HTTPS
- SQLite initially; PostgreSQL can be introduced later as the business grows

A typical process is:

```bash
sudo apt update
sudo apt install -y python3 python3-venv nginx

cd /var/www
sudo mkdir carmarket
sudo chown $USER:$USER carmarket
cd carmarket

# upload/extract this project here
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env

uvicorn app:app --host 127.0.0.1 --port 8000
```

For production, run Uvicorn through a systemd service and put Nginx in front of it. Configure your domain and HTTPS before going live.

## Important production notes

1. Replace the demo admin password.
2. Set a long random SECRET_KEY.
3. Restrict CORS to your real domain if the frontend/backend are separated.
4. Back up `data/dealership.db` and `static/uploads/`.
5. For larger inventory/traffic, migrate from SQLite to PostgreSQL.
6. Only upload/use vehicle photos you own or have permission to use.
7. The payment flow intentionally does not collect card/bank details. Customers contact support.

## Suggested next upgrades

- Email notifications when a customer messages
- Admin conversation threads instead of a flat message list
- Customer favorites
- Advanced price/year/mileage filters
- Multiple admin/staff roles
- Audit log
- Cloud image storage
- PostgreSQL
- Automated backups
- Rate limiting and CAPTCHA on public forms
