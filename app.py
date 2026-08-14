import os
import re
import json
import sqlite3
import secrets
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from starlette.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / os.getenv("DATABASE_PATH", "data/dealership.db")
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

APP_NAME = os.getenv("APP_NAME", "CarMarket")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET")
JWT_ALGORITHM = "HS256"
TOKEN_DAYS = 7
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

if SECRET_KEY == "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET":
    # Fine for local development; production should use a real secret in .env.
    SECRET_KEY = secrets.token_urlsafe(48)

app = FastAPI(title=f"{APP_NAME} API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your domain in production if desired.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

security = HTTPBearer(auto_error=False)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=64)
    return f"scrypt${salt.hex()}${derived.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$", 2)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex),
            n=16384, r=8, p=1, dklen=64
        )
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False

def create_token(user_id: int, role: str, username: str):
    payload = {
        "sub": str(user_id),
        "role": role,
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

def current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    return decode_token(credentials.credentials)

def admin_user(user=Depends(current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'customer',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER NOT NULL,
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Other',
        price REAL NOT NULL,
        mileage INTEGER NOT NULL,
        transmission TEXT NOT NULL,
        fuel_type TEXT NOT NULL,
        image_url TEXT,
        images_json TEXT NOT NULL DEFAULT '[]',
        description TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'available',
        featured INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        car_id INTEGER,
        message TEXT NOT NULL,
        sender_role TEXT NOT NULL,
        created_at TEXT NOT NULL,
        read_by_admin INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(customer_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY(car_id) REFERENCES cars(id) ON DELETE SET NULL
    );
    """)
    admin_username = os.getenv("ADMIN_USERNAME", "admin").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe_123!")
    row = conn.execute("SELECT id FROM users WHERE email = ?", (admin_username.lower(),)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            ("Administrator", admin_username.lower(), hash_password(admin_password), "admin", now_iso())
        )

    count = conn.execute("SELECT COUNT(*) AS c FROM cars").fetchone()["c"]
    if count == 0:
        demo = [
            (2021,"Chevrolet","Corvette Stingray","Sports Cars",64500,32450,"Automatic","Gasoline",
             "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&q=85",
             ["https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&q=85"],
             "A clean example with strong performance and premium equipment.","available",1),
            (2020,"BMW","X5 xDrive40i","SUVs",42900,45231,"Automatic","Gasoline",
             "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1200&q=85",
             ["https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=1200&q=85"],
             "Luxury SUV with a comfortable cabin and all-wheel drive.","available",1),
            (2019,"Toyota","4Runner SR5","SUVs",36800,56210,"Automatic","Gasoline",
             "https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?auto=format&fit=crop&w=1200&q=85",
             ["https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?auto=format&fit=crop&w=1200&q=85"],
             "Practical and rugged SUV ready for daily driving or adventure.","available",0),
            (2021,"Ford","F-150 XLT","Trucks",38750,28900,"Automatic","Gasoline",
             "https://images.unsplash.com/photo-1553440569-bcc63803a83d?auto=format&fit=crop&w=1200&q=85",
             ["https://images.unsplash.com/photo-1553440569-bcc63803a83d?auto=format&fit=crop&w=1200&q=85"],
             "Popular pickup with strong utility and modern technology.","available",0),
            (2020,"Honda","Accord EX","Sedans",27400,40125,"Automatic","Gasoline",
             "https://images.unsplash.com/photo-1590362891991-f776e747a588?auto=format&fit=crop&w=1200&q=85",
             ["https://images.unsplash.com/photo-1590362891991-f776e747a588?auto=format&fit=crop&w=1200&q=85"],
             "Comfortable midsize sedan with excellent everyday practicality.","available",0),
            (2018,"Audi","A4 Premium","Sedans",22900,58300,"Automatic","Gasoline",
             "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=1200&q=85",
             ["https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=1200&q=85"],
             "Premium compact sedan with a refined interior.","available",0),
        ]
        for c in demo:
            conn.execute("""INSERT INTO cars
                (year,make,model,category,price,mileage,transmission,fuel_type,image_url,images_json,description,status,featured,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*c[:8], c[8], json.dumps(c[9]), *c[10:13], now_iso()))
    conn.commit()
    conn.close()

init_db()

class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)

class LoginRequest(BaseModel):
    email: str
    password: str

class CarCreate(BaseModel):
    year: int = Field(ge=1900, le=2100)
    make: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=80)
    category: str = Field(default="Other", max_length=40)
    price: float = Field(gt=0)
    mileage: int = Field(ge=0)
    transmission: str = Field(default="Automatic", max_length=40)
    fuel_type: str = Field(default="Gasoline", max_length=40)
    image_url: Optional[str] = ""
    images: list[str] = []
    description: str = Field(default="", max_length=5000)
    status: str = Field(default="available", max_length=20)
    featured: bool = False

class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    car_id: Optional[int] = None

class StatusUpdate(BaseModel):
    status: str

class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)
    async def broadcast(self, payload):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = ConnectionManager()

def car_dict(r):
    d = dict(r)
    d["images"] = json.loads(d.pop("images_json") or "[]")
    d["featured"] = bool(d["featured"])
    return d

@app.get("/")
def home():
    return FileResponse(TEMPLATES_DIR / "index.html")

@app.get("/login")
def login_page():
    return FileResponse(TEMPLATES_DIR / "login.html")

@app.get("/register")
def register_page():
    return FileResponse(TEMPLATES_DIR / "register.html")

@app.get("/car-details")
def car_details_page():
    return FileResponse(TEMPLATES_DIR / "car-details.html")

@app.get("/contact")
def contact_page():
    return FileResponse(TEMPLATES_DIR / "contact.html")

@app.get("/admin-login")
def admin_login_page():
    return FileResponse(TEMPLATES_DIR / "admin-login.html")

@app.get("/admin")
def admin_page():
    return FileResponse(TEMPLATES_DIR / "admin.html")

@app.get("/api/health")
def health():
    return {"status":"ok","app":APP_NAME}

@app.post("/api/auth/register")
def register(payload: RegisterRequest):
    email = payload.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Enter a valid email")
    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            (payload.name.strip(), email, hash_password(payload.password), "customer", now_iso())
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    conn.close()
    return {"token": create_token(user_id, "customer", email), "user": {"id": user_id, "name": payload.name, "email": email, "role": "customer"}}

@app.post("/api/auth/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"token": create_token(row["id"], row["role"], row["email"]),
            "user": {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}}

@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    conn = db()
    row = conn.execute("SELECT id,name,email,role,created_at FROM users WHERE id=?", (int(user["sub"]),)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)

@app.get("/api/cars")
def get_cars(category: Optional[str] = None, search: Optional[str] = None, status: str = "available"):
    conn = db()
    query = "SELECT * FROM cars WHERE 1=1"
    args = []
    if status != "all":
        query += " AND status = ?"
        args.append(status)
    if category and category.lower() != "all":
        query += " AND category = ?"
        args.append(category)
    if search:
        query += " AND (make LIKE ? OR model LIKE ? OR category LIKE ?)"
        q = f"%{search}%"
        args.extend([q,q,q])
    query += " ORDER BY featured DESC, created_at DESC"
    rows = conn.execute(query, args).fetchall()
    conn.close()
    return [car_dict(r) for r in rows]

@app.get("/api/cars/{car_id}")
def get_car(car_id: int):
    conn = db()
    row = conn.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return car_dict(row)

@app.post("/api/cars")
def add_car(car: CarCreate, user=Depends(admin_user)):
    images = [x.strip() for x in car.images if x.strip()]
    image_url = car.image_url.strip() if car.image_url else (images[0] if images else "")
    conn = db()
    cur = conn.execute("""INSERT INTO cars
        (year,make,model,category,price,mileage,transmission,fuel_type,image_url,images_json,description,status,featured,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (car.year,car.make.strip(),car.model.strip(),car.category,car.price,car.mileage,
         car.transmission,car.fuel_type,image_url,json.dumps(images or ([image_url] if image_url else [])),
         car.description.strip(),car.status,1 if car.featured else 0,now_iso()))
    conn.commit()
    car_id = cur.lastrowid
    row = conn.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchone()
    conn.close()
    return {"message":"Vehicle added","car":car_dict(row)}

@app.put("/api/cars/{car_id}")
def update_car(car_id: int, car: CarCreate, user=Depends(admin_user)):
    images = [x.strip() for x in car.images if x.strip()]
    image_url = car.image_url.strip() if car.image_url else (images[0] if images else "")
    conn = db()
    cur = conn.execute("""UPDATE cars SET year=?,make=?,model=?,category=?,price=?,mileage=?,
        transmission=?,fuel_type=?,image_url=?,images_json=?,description=?,status=?,featured=? WHERE id=?""",
        (car.year,car.make.strip(),car.model.strip(),car.category,car.price,car.mileage,car.transmission,
         car.fuel_type,image_url,json.dumps(images or ([image_url] if image_url else [])),
         car.description.strip(),car.status,1 if car.featured else 0,car_id))
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Vehicle not found")
    conn.commit()
    row = conn.execute("SELECT * FROM cars WHERE id=?", (car_id,)).fetchone()
    conn.close()
    return {"message":"Vehicle updated","car":car_dict(row)}

@app.delete("/api/cars/{car_id}")
def delete_car(car_id: int, user=Depends(admin_user)):
    conn = db()
    cur = conn.execute("DELETE FROM cars WHERE id=?", (car_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return {"message":"Vehicle deleted"}

@app.post("/api/cars/{car_id}/status")
def update_status(car_id: int, payload: StatusUpdate, user=Depends(admin_user)):
    if payload.status not in {"available","sold","reserved"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    conn = db()
    cur = conn.execute("UPDATE cars SET status=? WHERE id=?", (payload.status, car_id))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return {"message":"Status updated"}

@app.post("/api/uploads")
async def upload_images(files: list[UploadFile] = File(...), user=Depends(admin_user)):
    uploaded = []
    allowed = {"image/jpeg","image/png","image/webp","image/avif"}
    for file in files:
        if file.content_type not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {file.content_type}")
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{file.filename} is larger than {MAX_UPLOAD_MB} MB")
        ext = mimetypes.guess_extension(file.content_type) or ".img"
        name = f"{secrets.token_hex(12)}{ext}"
        target = UPLOAD_DIR / name
        target.write_bytes(data)
        uploaded.append(f"/static/uploads/{name}")
    return {"images": uploaded}

@app.post("/api/messages")
async def create_message(payload: MessageCreate, user=Depends(current_user)):
    conn = db()
    row = conn.execute("SELECT id,name,email FROM users WHERE id=?", (int(user["sub"]),)).fetchone()
    if not row or row["role"] != "customer":
        conn.close()
        raise HTTPException(status_code=403, detail="Customer account required")
    if payload.car_id:
        exists = conn.execute("SELECT id FROM cars WHERE id=?", (payload.car_id,)).fetchone()
        if not exists:
            conn.close()
            raise HTTPException(status_code=404, detail="Vehicle not found")
    cur = conn.execute("""INSERT INTO messages
        (customer_id,customer_name,customer_email,car_id,message,sender_role,created_at)
        VALUES(?,?,?,?,?,?,?)""",
        (row["id"],row["name"],row["email"],payload.car_id,payload.message.strip(),"customer",now_iso()))
    conn.commit()
    msg_id = cur.lastrowid
    msg = conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()
    payload_out = dict(msg)
    await manager.broadcast({"type":"message","message":payload_out})
    return payload_out

@app.get("/api/messages")
def get_messages(user=Depends(admin_user)):
    conn = db()
    rows = conn.execute("""SELECT m.*, c.year, c.make, c.model
        FROM messages m LEFT JOIN cars c ON c.id=m.car_id
        ORDER BY m.created_at DESC""").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/messages/{customer_id}")
def get_customer_messages(customer_id: int, user=Depends(current_user)):
    if user.get("role") != "admin" and int(user["sub"]) != customer_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    conn = db()
    rows = conn.execute("""SELECT m.*, c.year, c.make, c.model
        FROM messages m LEFT JOIN cars c ON c.id=m.car_id
        WHERE m.customer_id=? ORDER BY m.created_at ASC""", (customer_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/messages/{customer_id}/reply")
async def reply_message(customer_id: int, payload: MessageCreate, user=Depends(admin_user)):
    conn = db()
    customer = conn.execute("SELECT id,name,email FROM users WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")
    cur = conn.execute("""INSERT INTO messages
        (customer_id,customer_name,customer_email,car_id,message,sender_role,created_at,read_by_admin)
        VALUES(?,?,?,?,?,?,?,1)""",
        (customer["id"],customer["name"],customer["email"],payload.car_id,payload.message.strip(),"admin",now_iso()))
    conn.commit()
    row = conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    out = dict(row)
    await manager.broadcast({"type":"message","message":out})
    return out

@app.post("/api/messages/read")
def mark_messages_read(user=Depends(admin_user)):
    conn = db()
    conn.execute("UPDATE messages SET read_by_admin=1 WHERE read_by_admin=0")
    conn.commit()
    conn.close()
    return {"message":"Messages marked as read"}

@app.get("/api/admin/stats")
def admin_stats(user=Depends(admin_user)):
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM cars").fetchone()["c"]
    available = conn.execute("SELECT COUNT(*) c FROM cars WHERE status='available'").fetchone()["c"]
    sold = conn.execute("SELECT COUNT(*) c FROM cars WHERE status='sold'").fetchone()["c"]
    unread = conn.execute("SELECT COUNT(*) c FROM messages WHERE read_by_admin=0").fetchone()["c"]
    customers = conn.execute("SELECT COUNT(*) c FROM users WHERE role='customer'").fetchone()["c"]
    conn.close()
    return {"vehicles":total,"available":available,"sold":sold,"unread_messages":unread,"customers":customers}

@app.websocket("/ws/admin")
async def admin_socket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return
    try:
        user = decode_token(token)
        if user.get("role") != "admin":
            await websocket.close(code=1008)
            return
    except HTTPException:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
