"""Sinhala Text Creator - COMPLETE VERSION WITH ADMIN DASHBOARD
=============================================================
Full working version with admin panel included"""
import gradio as gr
from PIL import Image, ImageDraw, ImageFont, ImageColor # Added ImageColor
import requests
import io
import os
import tempfile
import copy
from datetime import datetime
import hashlib
from typing import Optional, Tuple
from dataclasses import dataclass
import urllib.parse # Added for DB connection

# ============================================
# DATABASE SETUP
# ============================================
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("❌ psycopg2 not installed! Add 'psycopg2-binary' to requirements.txt")

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Get PostgreSQL database connection with better error handling"""
    if not PSYCOPG2_AVAILABLE:
        print("❌ psycopg2-binary not installed!")
        return None

    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables/secrets!")
        return None

    print(f"🔍 Checking connection... URL exists: {bool(DATABASE_URL)}")

    try:
        print("🔄 Attempting to connect to database...")
        # Ensure correct URL format
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            print("📝 Fixed URL format (postgres:// → postgresql://)")

        conn = psycopg2.connect(DATABASE_URL)
        print("✅ Database connected successfully!")
        return conn

    except psycopg2.OperationalError as e:
        error_msg = str(e)
        print(f"❌ Connection failed: {error_msg}")
        # Try parsing URL if direct connection fails (useful for some providers)
        try:
            print("🔄 Trying alternative connection method...")
            parsed = urllib.parse.urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path[1:] if parsed.path else 'postgres'
            )
            print("✅ Connected with alternative method!")
            return conn
        except Exception as e2:
            print(f"❌ Alternative method also failed: {e2}")
            return None
    except Exception as e:
        print(f"❌ Unexpected error connecting to database: {e}")
        return None

# ============================================
# USER MANAGEMENT FUNCTIONS
# ============================================
def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(email: str, password: str) -> Tuple[bool, str]:
    """Register new user"""
    if not email or not password:
        return False, "❌ Email and password required"
    if len(password) < 6:
        return False, "❌ Password must be at least 6 characters"

    conn = get_db_connection()
    if not conn:
        return False, "❌ Database connection failed during registration."
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                return False, "❌ Email already registered"

            password_hash = hash_password(password)
            current_month = datetime.now().strftime('%Y-%m')
            cursor.execute(
                'INSERT INTO users (email, password_hash, last_reset_date) VALUES (%s, %s, %s)',
                (email, password_hash, current_month)
            )
        conn.commit()
        return True, "✅ Account created! Please login."
    except Exception as e:
        conn.rollback() # Important: Rollback on error
        print(f"❌ Registration Error: {e}")
        return False, f"❌ Registration failed: {e}"
    finally:
        if conn:
            conn.close()

def login_user(email: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    """Login user and return user info"""
    if not email or not password:
        return False, "❌ Email and password required", None

    conn = get_db_connection()
    if not conn:
        return False, "❌ Database connection failed during login.", None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            password_hash = hash_password(password)
            cursor.execute(
                'SELECT id, email, plan, monthly_generations, last_reset_date, total_generations FROM users WHERE email = %s AND password_hash = %s AND is_active = true',
                (email, password_hash)
            )
            user = cursor.fetchone()

        if not user:
            return False, "❌ Invalid email or password", None

        # Reset monthly if new month (ensure reset_monthly_usage handles its own connection)
        current_month = datetime.now().strftime('%Y-%m')
        if user['last_reset_date'] != current_month:
            reset_monthly_usage(user['id']) # This needs separate connection handling
            # Re-fetch user data after potential reset if necessary, or just update locally
            user['monthly_generations'] = 0
            user['last_reset_date'] = current_month


        user_info = {
            'id': user['id'],
            'email': user['email'],
            'plan': user['plan'],
            'monthly_generations': user['monthly_generations'],
            'total_generations': user['total_generations'],
            'remaining': get_remaining_generations(user['plan'], user['monthly_generations'])
        }
        return True, f"✅ Welcome back, {email}!", user_info
    except Exception as e:
        print(f"❌ Login Error: {e}")
        return False, f"❌ Login failed: {e}", None
    finally:
         if conn:
            conn.close()

def get_remaining_generations(plan: str, used: int) -> int:
    """Calculate remaining generations for plan"""
    limits = {'free': 5, 'starter': 25, 'popular': 60, 'premium': 200}
    limit = limits.get(plan, 5)
    return max(0, limit - used)

def reset_monthly_usage(user_id: int):
    """Reset monthly generation count"""
    conn = get_db_connection()
    if not conn:
        print(f"❌ DB connection failed during reset_monthly_usage for user {user_id}")
        return
    try:
        with conn.cursor() as cursor:
            current_month = datetime.now().strftime('%Y-%m')
            cursor.execute(
                'UPDATE users SET monthly_generations = 0, last_reset_date = %s WHERE id = %s',
                (current_month, user_id)
            )
        conn.commit()
        print(f"✅ Reset monthly usage for user {user_id}")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error resetting usage for user {user_id}: {e}")
    finally:
        if conn:
            conn.close()

def increment_usage(user_id: int) -> Tuple[bool, str]:
    """Increment user's generation count"""
    conn = get_db_connection()
    if not conn:
        return False, "❌ Database connection failed during usage increment."
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get current usage and plan first
            cursor.execute('SELECT monthly_generations, plan FROM users WHERE id = %s', (user_id,))
            result = cursor.fetchone()
            if not result:
                return False, "❌ User not found"

            monthly_gens = result['monthly_generations']
            plan = result['plan']
            remaining = get_remaining_generations(plan, monthly_gens)

            if remaining <= 0:
                return False, "❌ Monthly limit reached! Upgrade or wait."

            # If limit not reached, increment counters
            cursor.execute(
                'UPDATE users SET monthly_generations = monthly_generations + 1, total_generations = total_generations + 1 WHERE id = %s',
                (user_id,)
            )
            # Log usage
            cursor.execute(
                'INSERT INTO usage_logs (user_id, action_type) VALUES (%s, %s)',
                (user_id, 'ai_generation')
            )
        conn.commit()
        new_remaining = remaining - 1
        return True, f"✅ Generated! {new_remaining} remaining this month"
    except Exception as e:
        conn.rollback()
        print(f"❌ Usage Increment Error for user {user_id}: {e}")
        return False, f"❌ Usage update failed: {e}"
    finally:
        if conn:
            conn.close()

def get_user_stats(user_id: int) -> str:
    """Get user statistics for dashboard"""
    conn = get_db_connection()
    if not conn:
        return "❌ Database connection failed for stats."
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                'SELECT email, plan, monthly_generations, total_generations, created_at FROM users WHERE id = %s',
                (user_id,)
            )
            user = cursor.fetchone()

        if user:
            remaining = get_remaining_generations(user['plan'], user['monthly_generations'])
            created_date = user['created_at'].strftime('%Y-%m-%d') if user['created_at'] else 'N/A'
            return f"""### 👤 {user['email']}
- **Plan:** {user['plan'].upper()}
- **This Month:** {user['monthly_generations']} used | **{remaining} remaining**
- **All Time:** {user['total_generations']} generations
- **Member Since:** {created_date}
"""
        return "❌ User not found"
    except Exception as e:
        print(f"❌ Get User Stats Error for user {user_id}: {e}")
        return f"❌ Error loading stats: {e}"
    finally:
        if conn:
            conn.close()

# ============================================
# ADMIN DASHBOARD FUNCTIONS
# ============================================
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    print("❌ WARNING: ADMIN_PASSWORD not set! Admin panel will not work.")

def check_admin_password(password: str) -> bool:
    """Check if admin password is correct"""
    return password == ADMIN_PASSWORD

def get_admin_stats() -> str:
    """Get complete admin statistics"""
    conn = get_db_connection()
    if not conn: return "❌ Database connection failed for admin stats."
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']
            cursor.execute("SELECT plan, COUNT(*) as count FROM users GROUP BY plan ORDER BY plan")
            plan_stats = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) as active FROM users WHERE created_at > NOW() - INTERVAL '30 days'")
            active_users = cursor.fetchone()['active']
            cursor.execute("SELECT COALESCE(SUM(total_generations), 0) as total_gens, COALESCE(SUM(monthly_generations), 0) as monthly_gens FROM users")
            gen_stats = cursor.fetchone()
            cursor.execute("SELECT email, plan, created_at, total_generations, monthly_generations FROM users ORDER BY created_at DESC LIMIT 15")
            recent_users = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) as today_count FROM users WHERE DATE(created_at) = CURRENT_DATE")
            today_signups = cursor.fetchone()['today_count']
        
        report = f"# 📊 ADMIN DASHBOARD\n\n## 👥 User Statistics\n- Total Users: {total_users}\n- New Today: {today_signups}\n- Active (30 days): {active_users}\n\n## 💎 Users by Plan"
        for plan in plan_stats: report += f"\n- **{plan['plan'].upper()}:** {plan['count']} users"
        report += f"\n\n## 🎨 Generation Statistics\n- Total All-Time: {gen_stats['total_gens']}\n- Used This Month: {gen_stats['monthly_gens']}\n- Average per User: {gen_stats['total_gens'] // max(total_users, 1)}"
        report += "\n\n## 🆕 Recent Users (Latest 15)\n| Email | Plan | Joined | Monthly | Total |\n|-------|------|--------|---------|-------|"
        for user in recent_users:
            date = user['created_at'].strftime('%m/%d') if user['created_at'] else 'N/A'
            email = user['email'][:20] + '...' if len(user['email']) > 20 else user['email']
            report += f"\n| {email} | {user['plan']} | {date} | {user['monthly_generations']} | {user['total_generations']} |"
        report += f"\n\n---\n*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
        return report
    except Exception as e:
        print(f"❌ Get Admin Stats Error: {e}")
        return f"❌ Error loading stats: {e}"
    finally:
        if conn: conn.close()

def export_user_data() -> tuple:
    """Export all user data as CSV format"""
    conn = get_db_connection()
    if not conn: return None, "❌ Database connection failed for export."
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT email, plan, monthly_generations, total_generations, created_at, is_active FROM users ORDER BY created_at DESC")
            users = cursor.fetchall()
        if not users: return None, "No users found"
        csv_data = "Email,Plan,Monthly Usage,Total Usage,Joined Date,Status\n"
        for user in users:
            date = user['created_at'].strftime('%Y-%m-%d %H:%M') if user['created_at'] else 'N/A'
            status = "Active" if user['is_active'] else "Inactive"
            csv_data += f"{user['email']},{user['plan']},{user['monthly_generations']},{user['total_generations']},{date},{status}\n"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as temp_file:
            temp_file.write(csv_data)
            return temp_file.name, f"✅ Exported {len(users)} users to CSV"
    except Exception as e:
        print(f"❌ Export User Data Error: {e}")
        return None, f"❌ Export error: {e}"
    finally:
        if conn: conn.close()

# ============================================
# FONTS & CONFIG
# ============================================
FONT_DIR = "app/fonts"
os.makedirs(FONT_DIR, exist_ok=True)
FONT_PATHS = {
    "Anton": "Anton-Regular.ttf", "Bebas Neue": "BebasNeue-Regular.ttf",
    "Oswald Bold": "Oswald-Bold.ttf", "Oswald Regular": "Oswald-Regular.ttf",
    "Montserrat Bold": "Montserrat-Bold.ttf", "Montserrat Regular": "Montserrat-Regular.ttf", "Montserrat Italic": "Montserrat-Italic.ttf",
    "Hind Madurai Bold (Tamil)": "HindMadurai-Bold.ttf", "Hind Madurai Regular (Tamil)": "HindMadurai-Regular.ttf",
    "Abhaya Bold (Sinhala)": "AbhayaLibre-Bold.ttf", "Abhaya Regular (Sinhala)": "AbhayaLibre-Regular.ttf",
    "Noto Sans (Sinhala)": "NotoSansSinhala_Condensed-Regular.ttf"
}
fonts_available = {}
print("--- Loading Fonts ---")
for name, filename in FONT_PATHS.items():
    path = os.path.join(FONT_DIR, filename)
    if os.path.exists(path):
        try:
            ImageFont.truetype(path, 20)
            fonts_available[name] = path
            print(f"✅ Loaded: {name}")
        except Exception as e:
            print(f"❌ Error loading font '{name}' from '{path}': {e}")
    else:
        print(f"⚠️ Not Found: Font file for '{name}' at '{path}'")
if not fonts_available:
    print("❌ No custom fonts loaded. Falling back to system font.")
    # Attempt to find a common system font path
    fallback_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", # Linux
        "/System/Library/Fonts/HelveticaNeue.ttc", # MacOS (using a common one)
        "C:/Windows/Fonts/arialbd.ttf" # Windows (bold arial)
    ]
    for fp in fallback_paths:
        if os.path.exists(fp):
            fonts_available["
