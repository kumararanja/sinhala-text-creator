"""Sinhala Text Creator - COMPLETE VERSION WITH ADMIN DASHBOARD
=============================================================
Full working version with admin panel included"""
import gradio as gr
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import os
import tempfile
import copy
from datetime import datetime
import hashlib
from typing import Optional, Tuple
from dataclasses import dataclass

# ============================================
# DATABASE SETUP
# ============================================
# Check for required packages
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("❌ psycopg2 not installed! Add 'psycopg2-binary' to requirements.txt")

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ WARNING: DATABASE_URL not found in environment variables!")
    print("Add it to Secrets in HF Space Settings")

def get_db_connection():
    """Get PostgreSQL database connection with better error handling"""
    # First, check if psycopg2 is installed
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2-binary not installed!")
        print("Fix: Add 'ps psycopg2-binary' to requirements.txt")
        return None

    # Get the database URL from environment
    DATABASE_URL = os.getenv("DATABASE_URL")

    # Show debugging info
    print(f"🔍 Checking connection... URL exists: {bool(DATABASE_URL)}")

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in Hugging Face Secrets!")
        print("Fix: Go to Settings → Variables and secrets → New secret")
        print("Name: DATABASE_URL")
        print("Value: Your Supabase connection string")
        return None

    # Try to connect with better error messages
    try:
        print("🔄 Attempting to connect to database...")

        # If the URL starts with postgres:// change it to postgresql://
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            print("📝 Fixed URL format (postgres:// → postgresql://)")

        # Try Method 1: Direct connection
        conn = psycopg2.connect(DATABASE_URL)
        print("✅ Database connected successfully!")
        return conn

    except psycopg2.OperationalError as e:
        error_msg = str(e)
        print(f"❌ Connection failed: {error_msg[:100]}")

        # Give specific help based on error
        if "password authentication failed" in error_msg:
            print("🔧 Fix: Check your password in Supabase dashboard")
        elif "could not connect to server" in error_msg:
            print("🔧 Fix: Check if Supabase project is active (not paused)")
        elif "timeout" in error_msg:
            print("🔧 Fix: Supabase might be paused. Go to dashboard and unpause it")
        else:
            print("🔧 Fix: Check your connection string in Supabase Settings → Database")

        # Try Method 2: Parse URL and reconnect
        try:
            print("🔄 Trying alternative connection method...")
            import urllib.parse

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
            print(f"❌ Alternative method also failed: {str(e2)[:100]}")
            print("\n📋 WHAT TO DO:")
            print("1. Go to Supabase Dashboard")
            print("2. Click Settings → Database")
            print("3. Copy the 'Session pooler' connection string")
            print("4. Update it in Hugging Face Secrets")
            return None

    except Exception as e:
        print(f"❌ Unexpected error: {str(e)[:100]}")
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

    try:
        conn = get_db_connection()
        if not conn:
            return False, "❌ Database not available"

        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            conn.close()
            return False, "❌ Email already registered"

        # Create user
        password_hash = hash_password(password)
        current_month = datetime.now().strftime('%Y-%m')

        cursor.execute('''
            INSERT INTO users (email, password_hash, last_reset_date)
            VALUES (%s, %s, %s)
        ''', (email, password_hash, current_month))

        conn.commit()
        conn.close()

        return True, "✅ Account created! Please login."

    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def login_user(email: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    """Login user and return user info"""
    if not email or not password:
        return False, "❌ Email and password required", None

    try:
        conn = get_db_connection()
        if not conn:
            return False, "❌ Database not available", None

        cursor = conn.cursor(cursor_factory=RealDictCursor)
        password_hash = hash_password(password)

        cursor.execute('''
            SELECT id, email, plan, monthly_generations, last_reset_date, total_generations
            FROM users
            WHERE email = %s AND password_hash = %s AND is_active = true
        ''', (email, password_hash))

        user = cursor.fetchone()
        conn.close()

        if not user:
            return False, "❌ Invalid email or password", None

        # Reset monthly if new month
        current_month = datetime.now().strftime('%Y-%m')
        if user['last_reset_date'] != current_month:
            reset_monthly_usage(user['id'])
            user['monthly_generations'] = 0

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
        return False, f"❌ Error: {str(e)}", None

def get_remaining_generations(plan: str, used: int) -> int:
    """Calculate remaining generations for plan"""
    limits = {
        'free': 5,
        'starter': 25,
        'popular': 60,
        'premium': 200
    }
    limit = limits.get(plan, 5)
    return max(0, limit - used)

def reset_monthly_usage(user_id: int):
    """Reset monthly generation count"""
    try:
        conn = get_db_connection()
        if not conn:
            return

        cursor = conn.cursor()
        current_month = datetime.now().strftime('%Y-%m')

        cursor.execute('''
            UPDATE users
            SET monthly_generations = 0, last_reset_date = %s
            WHERE id = %s
        ''', (current_month, user_id))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error resetting usage: {e}")

def increment_usage(user_id: int) -> Tuple[bool, str]:
    """Increment user's generation count"""
    try:
        conn = get_db_connection()
        if not conn:
            return False, "❌ Database not available"

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get current usage
        cursor.execute('''
            SELECT monthly_generations, plan FROM users WHERE id = %s
        ''', (user_id,))

        result = cursor.fetchone()
        if not result:
            conn.close()
            return False, "❌ User not found"

        monthly_gens = result['monthly_generations']
        plan = result['plan']
        remaining = get_remaining_generations(plan, monthly_gens)

        if remaining <= 0:
            conn.close()
            return False, "❌ Monthly limit reached! Upgrade your plan or wait for next month."

        # Increment counters
        cursor.execute('''
            UPDATE users
            SET monthly_generations = monthly_generations + 1,
                total_generations = total_generations + 1
            WHERE id = %s
        ''', (user_id,))

        # Log usage
        cursor.execute('''
            INSERT INTO usage_logs (user_id, action_type)
            VALUES (%s, %s)
        ''', (user_id, 'ai_generation'))

        conn.commit()
        conn.close()

        new_remaining = remaining - 1
        return True, f"✅ Generated! {new_remaining} remaining this month"

    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def get_user_stats(user_id: int) -> str:
    """Get user statistics for dashboard"""
    try:
        conn = get_db_connection()
        if not conn:
            return "❌ Database not available"

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute('''
            SELECT email, plan, monthly_generations, total_generations, created_at
            FROM users WHERE id = %s
        ''', (user_id,))

        user = cursor.fetchone()
        conn.close()

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
        return f"❌ Error: {str(e)}"

# ============================================
# ADMIN DASHBOARD FUNCTIONS
# ============================================
# 🔐 Admin password from environment variables (SECURE!)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    print("❌ WARNING: ADMIN_PASSWORD not set! Admin panel will not work.")
    print("📝 Add ADMIN_PASSWORD to Hugging Face Secrets")

def check_admin_password(password: str) -> bool:
    """Check if admin password is correct"""
    return password == ADMIN_PASSWORD

def get_admin_stats() -> str:
    """Get complete admin statistics"""
    try:
        conn = get_db_connection()
        if not conn:
            return "❌ Database not available"

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get total users
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']

        # Get users by plan
        cursor.execute("""
            SELECT plan, COUNT(*) as count
            FROM users
            GROUP BY plan
            ORDER BY plan
        """)
        plan_stats = cursor.fetchall()

        # Get active users (logged in last 30 days)
        cursor.execute("""
            SELECT COUNT(*) as active
            FROM users
            WHERE created_at > NOW() - INTERVAL '30 days'
        """)
        active_users = cursor.fetchone()['active']

        # Get total generations
        cursor.execute("""
            SELECT
                COALESCE(SUM(total_generations), 0) as total_gens,
                COALESCE(SUM(monthly_generations), 0) as monthly_gens
            FROM users
        """)
        gen_stats = cursor.fetchone()

        # Get recent users
        cursor
