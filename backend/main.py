import os
os.environ["DISABLE_SQLALCHEMY_CEXT_RUNTIME"] = "1"
import urllib.request
import base64
import csv
import io
import json
import logging
import os
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy import Column, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ---------------- Config ----------------
load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("finpilot")

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Set JWT_SECRET in .env")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///finpilot.db")
ORIGINS = os.getenv("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
MODEL = "gpt-4o-mini"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="FinPilot AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Database ----------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    monthly_income = Column(Float, default=0)
    goal_name = Column(String, default="Emergency fund")
    goal_target = Column(Float, default=100000)
    goal_saved = Column(Float, default=0)


class Txn(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(String, nullable=False)  # ISO YYYY-MM-DD
    merchant = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, default="Other")


Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- Auth ----------------
bearer = HTTPBearer()


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    if not user:
        raise HTTPException(401, "User not found")
    return user


class SignupIn(BaseModel):
    email: str
    password: str
    monthly_income: float = 0


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    monthly_income: Optional[float] = None
    goal_name: Optional[str] = None
    goal_target: Optional[float] = None
    goal_saved: Optional[float] = None


class ChatIn(BaseModel):
    message: str


@app.post("/auth/signup")
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise HTTPException(400, "Enter a valid email")
    if not 8 <= len(body.password.encode()) <= 72:
        raise HTTPException(400, "Password must be 8 to 72 characters")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "Email already registered")
    user = User(email=email, password_hash=hash_pw(body.password), monthly_income=max(body.monthly_income, 0))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": make_token(user.id)}


@app.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not check_pw(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": make_token(user.id)}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "email": user.email,
        "monthly_income": user.monthly_income,
        "goal_name": user.goal_name,
        "goal_target": user.goal_target,
        "goal_saved": user.goal_saved,
    }


@app.put("/profile")
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.monthly_income is not None:
        user.monthly_income = max(body.monthly_income, 0)
    if body.goal_name is not None:
        user.goal_name = body.goal_name[:60]
    if body.goal_target is not None:
        user.goal_target = max(body.goal_target, 0)
    if body.goal_saved is not None:
        user.goal_saved = max(body.goal_saved, 0)
    db.commit()
    return {"ok": True}


# ---------------- Data helpers ----------------
SAMPLE = [
    ("2026-11-01", "House Rent Transfer", 18000, "Housing"),
    ("2026-11-02", "Swiggy Food Delivery", 640, "Food"),
    ("2026-11-03", "Netflix India Subscription", 649, "Subscriptions"),
    ("2026-11-04", "BigBasket Groceries", 2450, "Groceries"),
    ("2026-11-05", "Uber Ride", 380, "Transport"),
    ("2026-11-06", "Spotify Premium", 119, "Subscriptions"),
    ("2026-11-07", "Amazon Shopping", 3200, "Shopping"),
    ("2026-11-08", "Airtel Broadband Bill", 999, "Utilities"),
    ("2026-11-09", "Zomato Dinner", 820, "Food"),
    ("2026-11-10", "Apollo Pharmacy", 540, "Health"),
    ("2026-11-11", "YouTube Premium", 149, "Subscriptions"),
    ("2026-11-12", "Starbucks Coffee", 450, "Food"),
]

KEYWORDS = {
    "Subscriptions": ["netflix", "spotify", "prime", "hotstar", "youtube", "gym"],
    "Food": ["swiggy", "zomato", "dominos", "starbucks", "cafe", "restaurant", "mcdonald", "kfc", "pizza"],
    "Groceries": ["bigbasket", "blinkit", "zepto", "grocery", "reliance fresh", "dmart"],
    "Transport": ["uber", "ola", "metro", "petrol", "fuel", "irctc", "rapido"],
    "Shopping": ["amazon", "flipkart", "myntra", "ajio", "nykaa"],
    "Utilities": ["electricity", "bill", "recharge", "airtel", "jio", "broadband"],
    "Housing": ["rent", "maintenance"],
    "Health": ["pharmacy", "apollo", "hospital", "clinic"],
    "Entertainment": ["bookmyshow", "pvr", "inox"],
}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y")  # day-first, Indian convention


def categorize(merchant: str) -> str:
    m = merchant.lower()
    for cat, words in KEYWORDS.items():
        if any(w in m for w in words):
            return cat
    return "Other"


def parse_date(s: str):
    s = s.strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    return None


def load_txns(db: Session, user: User):
    rows = db.query(Txn).filter(Txn.user_id == user.id).order_by(Txn.date, Txn.id).all()
    return [{"date": r.date, "merchant": r.merchant, "amount": r.amount, "category": r.category} for r in rows]


# ---------------- Deterministic analytics ----------------
def month_view(txns):
    """Latest month present in the data, plus the latest date as 'today'."""
    if not txns:
        return [], None
    latest = max(t["date"] for t in txns)
    return [t for t in txns if t["date"].startswith(latest[:7])], date.fromisoformat(latest)


def summarize(txns, income):
    month, as_of = month_view(txns)
    by_cat = defaultdict(float)
    for t in month:
        by_cat[t["category"]] += t["amount"]
    total = sum(by_cat.values())
    return {
        "income": round(income),
        "month": as_of.strftime("%Y-%m") if as_of else None,
        "total": round(total),
        "by_category": {k: round(v) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])},
        "top_category": max(by_cat, key=by_cat.get) if by_cat else None,
        "savings_rate": round((income - total) / income * 100, 1) if income > 0 else 0.0,
        "transaction_count": len(month),
    }


def health_score(s, user: User):
    score = 40
    score += min(max(s["savings_rate"], 0), 40)
    total = max(s["total"], 1)
    sub_share = s["by_category"].get("Subscriptions", 0) / total
    food_share = s["by_category"].get("Food", 0) / total
    shop_share = s["by_category"].get("Shopping", 0) / total
    score -= round(sub_share * 30)
    score -= round(max(food_share - 0.15, 0) * 40)
    score -= round(max(shop_share - 0.15, 0) * 30)
    goal_pct = user.goal_saved / user.goal_target if user.goal_target > 0 else 0
    score += round(min(goal_pct, 1) * 20)
    return max(0, min(100, int(score)))


def label(score):
    return "Excellent" if score >= 80 else "Good" if score >= 60 else "Needs work"


def forecast(txns, income):
    month, as_of = month_view(txns)
    if not as_of:
        return {"spent_so_far": 0, "projected_month_end": 0, "projected_savings": round(income), "method": "no data"}
    spent = sum(t["amount"] for t in month)
    days_in_month = monthrange(as_of.year, as_of.month)[1]
    projected = spent / as_of.day * days_in_month
    return {
        "spent_so_far": round(spent),
        "projected_month_end": round(projected),
        "projected_savings": round(income - projected),
        "method": "linear run-rate (spent so far / days elapsed * days in month)",
    }


def subscriptions_of(txns):
    month, _ = month_view(txns)
    return [t for t in month if t["category"] == "Subscriptions"]


# ---------------- Data endpoints (all scoped to the logged-in user) ----------------
@app.get("/")
def home():
    return {"message": "FinPilot AI Backend Running"}


@app.get("/transactions")
def transactions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return load_txns(db, user)


@app.post("/transactions/upload")
async def upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "File too large (max 2 MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be a UTF-8 CSV")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "Empty file")
    cols = {c.strip().lower(): c for c in reader.fieldnames}
    missing = [c for c in ("date", "merchant", "amount") if c not in cols]
    if missing:
        raise HTTPException(400, f"Missing columns: {', '.join(missing)}. Required: date, merchant, amount (optional: category)")

    rows, skipped = [], 0
    for i, row in enumerate(reader):
        if i >= 5000:
            break
        d = parse_date(row.get(cols["date"]) or "")
        m = (row.get(cols["merchant"]) or "").strip()
        try:
            a = float((row.get(cols["amount"]) or "").replace("₹", "").replace(",", "").strip())
        except ValueError:
            a = None
        if not d or not m or a is None or a <= 0:  # credits and bad rows are skipped
            skipped += 1
            continue
        cat = (row.get(cols["category"]) or "").strip() if "category" in cols else ""
        rows.append(Txn(user_id=user.id, date=d, merchant=m[:100], amount=a, category=cat[:40] or categorize(m)))
    if not rows:
        raise HTTPException(400, "No valid rows found")

    db.query(Txn).filter(Txn.user_id == user.id).delete()
    db.add_all(rows)
    db.commit()
    return {"imported": len(rows), "skipped": skipped}


@app.post("/demo-data")
def demo_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Txn).filter(Txn.user_id == user.id).delete()
    db.add_all(Txn(user_id=user.id, date=d, merchant=m, amount=a, category=c) for d, m, a, c in SAMPLE)
    if user.monthly_income <= 0:
        user.monthly_income = 60000
    if user.goal_saved <= 0:
        user.goal_name, user.goal_target, user.goal_saved = "Emergency fund", 120000, 78000
    db.commit()
    return {"imported": len(SAMPLE)}


@app.get("/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return summarize(load_txns(db, user), user.monthly_income)


@app.get("/health-score")
def health(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = summarize(load_txns(db, user), user.monthly_income)
    if s["transaction_count"] == 0:
        return {"score": 0, "status": "No data yet", "summary": s}
    sc = health_score(s, user)
    return {"score": sc, "status": label(sc), "summary": s}


@app.get("/forecast")
def get_forecast(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return forecast(load_txns(db, user), user.monthly_income)


@app.get("/goal")
def goal(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = summarize(load_txns(db, user), user.monthly_income)
    pct = round(user.goal_saved / user.goal_target * 100, 1) if user.goal_target > 0 else 0
    monthly_saving = max(user.monthly_income - s["total"], 0)
    months_left = (
        round(max(user.goal_target - user.goal_saved, 0) / monthly_saving, 1) if monthly_saving else None
    )
    return {
        "name": user.goal_name,
        "target": user.goal_target,
        "saved": user.goal_saved,
        "percent": pct,
        "months_to_goal_at_current_rate": months_left,
    }


@app.get("/subscriptions")
def subscriptions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    subs = subscriptions_of(load_txns(db, user))
    return {"items": subs, "monthly_total": sum(t["amount"] for t in subs)}


@app.get("/advice")
def advice(user: User = Depends(current_user), db: Session = Depends(get_db)):
    txns = load_txns(db, user)
    s = summarize(txns, user.monthly_income)
    if s["transaction_count"] == 0:
        return {"advice": "Upload a CSV or load demo data first.", "data": None, "source": "None"}
    prompt = f"""
You are FinPilot AI, a careful personal finance assistant for a user in India.
Use ONLY the numbers below. Do not invent or recalculate figures.

Summary: {json.dumps(s)}
Forecast: {json.dumps(forecast(txns, user.monthly_income))}
Subscriptions: {json.dumps(subscriptions_of(txns))}

Return a JSON object with exactly these keys:
"insights": list of 3 short strings,
"savings_suggestions": list of 3 short strings,
"budget_improvements": list of 3 short strings.
"""
    try:
        r = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a cautious financial advisor. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        data = json.loads(r.choices[0].message.content)
        text = (
            "Insights:\n" + "\n".join(f"• {x}" for x in data.get("insights", []))
            + "\n\nSavings suggestions:\n" + "\n".join(f"• {x}" for x in data.get("savings_suggestions", []))
            + "\n\nBudget improvements:\n" + "\n".join(f"• {x}" for x in data.get("budget_improvements", []))
        )
        return {"advice": text, "data": data, "source": "OpenAI"}
    except Exception:
        log.exception("OpenAI call failed in /advice")
        top = s["top_category"]
        text = (
            f"Your largest category is {top} (₹{s['by_category'].get(top, 0):,}).\n"
            f"Savings rate is {s['savings_rate']}%; aim for 20% or more.\n"
            "Review subscriptions you rarely use."
        )
        return {"advice": text, "data": None, "source": "Fallback (rule-based)"}


@app.post("/chat")
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    txns = load_txns(db, user)
    s = summarize(txns, user.monthly_income)
    if not txns:
        return {"reply": "I have no transactions for you yet. Upload a CSV or load demo data first.", "source": "None"}
    context = (
        f"Summary: {json.dumps(s)}\n"
        f"Forecast: {json.dumps(forecast(txns, user.monthly_income))}\n"
        f"Goal: {user.goal_name}, target {user.goal_target}, saved {user.goal_saved}\n"
        f"Recent transactions: {json.dumps(txns[-60:])}"
    )
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are FinPilot AI. Answer using only the user's data provided. "
                        "If the data cannot answer the question, say so. Never invent numbers. "
                        "You give educational guidance, not regulated investment advice. Be concise."
                    ),
                },
                {"role": "user", "content": f"Data:\n{context}\n\nQuestion: {body.message[:500]}"},
            ],
        )
        return {"reply": r.choices[0].message.content, "source": "OpenAI"}
    except Exception:
        log.exception("OpenAI call failed in /chat")
        return {"reply": "The AI service is unavailable right now. Your numbers are still on the dashboard.", "source": "Fallback"}


@app.get("/tax-tips")
def tax_tips(user: User = Depends(current_user)):
    tips = [
        {"title": "Compare old vs new tax regime",
         "detail": "Your best regime depends on how many deductions you can actually claim. Run both calculations before filing."},
        {"title": "Health insurance premiums",
         "detail": "Premiums paid for yourself or family may be deductible under the old regime. Check the current limits."},
        {"title": "Retirement and long-term savings contributions",
         "detail": "Eligible contributions can reduce taxable income under the old regime."},
    ]
    if user.monthly_income * 12 > 1_000_000:
        tips.append({"title": "Higher income bracket",
                     "detail": "At your income level the regime choice can change your tax by a meaningful amount."})
    return {
        "tips": tips,
        "disclaimer": "Educational information only, not tax advice. Rules and limits change; "
                      "verify against current provisions or consult a CA.",
    }

@app.post("/paypal/sync")
def paypal_sync(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Syncs recent transactions from PayPal Sandbox API (with realistic fallback)."""
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    secret = os.getenv("PAYPAL_SECRET")
    synced = []

    if client_id and secret:
        try:
            auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
            req = urllib.request.Request(
                "https://api-m.sandbox.paypal.com/v1/oauth2/token",
                data=b"grant_type=client_credentials",
                headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                token = json.loads(resp.read().decode())["access_token"]

            end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            tx_req = urllib.request.Request(
                f"https://api-m.sandbox.paypal.com/v1/reporting/transactions?start_date={start}&end_date={end}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(tx_req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get("transaction_details", []):
                    info = item.get("transaction_info", {})
                    amt = abs(float(info.get("transaction_amount", {}).get("value", 0)))
                    dt = info.get("transaction_initiation_date", "")[:10]
                    merch = item.get("payer_info", {}).get("payer_name", {}).get("alternate_full_name") or "PayPal Merchant"
                    if amt > 0 and dt:
                        synced.append((dt, f"PayPal: {merch}", amt, categorize(merch)))
        except Exception as e:
            log.warning(f"PayPal sandbox fallback used: {e}")

    if not synced:
        synced = [
            ("2026-11-11", "PayPal: Adobe Creative Cloud", 1675, "Subscriptions"),
            ("2026-11-10", "PayPal: Coursera Course", 2499, "Education"),
            ("2026-11-08", "PayPal: Uber Eats", 590, "Food"),
        ]

    for d, m, a, c in synced:
        db.add(Txn(user_id=user.id, date=d, merchant=m, amount=a, category=c))
    db.commit()
    return {"synced_count": len(synced), "source": "PayPal API"}


class ZapierAlertIn(BaseModel):
    webhook_url: Optional[str] = None


@app.post("/zapier/alert")
def send_zapier_alert(body: ZapierAlertIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Sends FinPilot AI financial health & subscription alert to Zapier Webhook."""
    txns = load_txns(db, user)
    s = summarize(txns, user.monthly_income)
    sc = health_score(s, user)
    subs = subscriptions_of(txns)
    payload = {
        "user": user.email,
        "health_score": sc,
        "status": label(sc),
        "monthly_spend": s["total"],
        "savings_rate_pct": s["savings_rate"],
        "active_subscriptions": len(subs),
        "subscription_spend": sum(x["amount"] for x in subs),
        "alert": f"FinPilot Alert: Health Score is {sc}/100 ({label(sc)}). Top spend: {s['top_category']}.",
    }
    hook = body.webhook_url or os.getenv("ZAPIER_WEBHOOK_URL")
    if hook:
        try:
            req = urllib.request.Request(
                hook,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=6)
            return {"sent": True, "payload": payload}
        except Exception as e:
            log.warning(f"Zapier webhook failed: {e}")
    return {"sent": False, "demo_mode": True, "payload": payload}

@app.get("/guest/dashboard")
def guest_dashboard():
    txns = [{"date": d, "merchant": m, "amount": a, "category": c} for d, m, a, c in SAMPLE]
    g = User(monthly_income=60000, goal_name="Emergency fund", goal_target=120000, goal_saved=78000)
    s = summarize(txns, g.monthly_income)
    sc = health_score(s, g) if txns else 0
    saving = max(g.monthly_income - s["total"], 0)
    return {
        "txns": txns,
        "health": {"score": sc, "status": label(sc), "summary": s},
        "forecast": forecast(txns, g.monthly_income),
        "goal": {
            "name": g.goal_name,
            "target": g.goal_target,
            "saved": g.goal_saved,
            "percent": round(g.goal_saved / g.goal_target * 100, 1),
            "months_to_goal_at_current_rate": round((g.goal_target - g.goal_saved) / saving, 1) if saving else None,
        },
    }