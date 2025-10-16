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
        print("Fix: Add 'psycopg2-binary' to requirements.txt")
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
        cursor.execute("""
            SELECT email, plan, created_at, total_generations, monthly_generations
            FROM users
            ORDER BY created_at DESC
            LIMIT 15
        """)
        recent_users = cursor.fetchall()

        # Get today's signups
        cursor.execute("""
            SELECT COUNT(*) as today_count
            FROM users
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today_signups = cursor.fetchone()['today_count']

        conn.close()

        # Format the report
        report = f"""# 📊 **ADMIN DASHBOARD**

## 👥 **User Statistics**
- **Total Users:** {total_users}
- **New Today:** {today_signups}
- **Active (30 days):** {active_users}

## 💎 **Users by Plan**"""

        for plan in plan_stats:
            report += f"\n- **{plan['plan'].upper()}:** {plan['count']} users"

        report += f"""

## 🎨 **Generation Statistics**
- **Total All-Time:** {gen_stats['total_gens']} generations
- **Used This Month:** {gen_stats['monthly_gens']} generations
- **Average per User:** {gen_stats['total_gens'] // max(total_users, 1)} generations

## 🆕 **Recent Users (Latest 15)**
| Email | Plan | Joined | Monthly | Total |
|-------|------|--------|---------|-------|"""

        for user in recent_users:
            date = user['created_at'].strftime('%m/%d') if user['created_at'] else 'N/A'
            email = user['email'][:20] + '...' if len(user['email']) > 20 else user['email']
            report += f"\n| {email} | {user['plan']} | {date} | {user['monthly_generations']} | {user['total_generations']} |"

        report += f"\n\n---\n*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"

        return report

    except Exception as e:
        return f"❌ Error loading stats: {str(e)}\n\nMake sure your database tables are created."

def export_user_data() -> tuple:
    """Export all user data as CSV format"""
    try:
        conn = get_db_connection()
        if not conn:
            return None, "❌ Database not available"

        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                email,
                plan,
                monthly_generations,
                total_generations,
                created_at,
                is_active
            FROM users
            ORDER BY created_at DESC
        """)

        users = cursor.fetchall()
        conn.close()

        if not users:
            return None, "No users found"

        # Create CSV format
        csv_data = "Email,Plan,Monthly Usage,Total Usage,Joined Date,Status\n"
        for user in users:
            date = user['created_at'].strftime('%Y-%m-%d %H:%M') if user['created_at'] else 'N/A'
            status = "Active" if user['is_active'] else "Inactive"
            csv_data += f"{user['email']},{user['plan']},{user['monthly_generations']},{user['total_generations']},{date},{status}\n"

        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        temp_file.write(csv_data)
        temp_file.close()

        return temp_file.name, f"✅ Exported {len(users)} users to CSV"

    except Exception as e:
        return None, f"❌ Export error: {str(e)}"


# ============================================
# FONTS & CONFIG
# ============================================
# Define a directory for your fonts
FONT_DIR = "app/fonts" # Assuming 'app/fonts' is where your fonts are stored

# Ensure the font directory exists (optional, but good for robustness)
os.makedirs(FONT_DIR, exist_ok=True)

# Define font paths for Sinhala, English and Tamil fonts
# Make sure these filenames match the actual files in your 'app/fonts' directory
FONT_PATHS = {
    # --- English / General Fonts ---
    "Anton": "Anton-Regular.ttf",
    "Bebas Neue": "BebasNeue-Regular.ttf",
    "Oswald Bold": "Oswald-Bold.ttf",
    "Oswald Regular": "Oswald-Regular.ttf",
    "Montserrat Bold": "Montserrat-Bold.ttf",
    "Montserrat Regular": "Montserrat-Regular.ttf",
    "Montserrat Italic": "Montserrat-Italic.ttf",

    # --- Tamil Fonts ---
    "Hind Madurai Bold (Tamil)": "HindMadurai-Bold.ttf",
    "Hind Madurai Regular (Tamil)": "HindMadurai-Regular.ttf",

    # --- Sinhala Fonts ---
    "Abhaya Bold (Sinhala)": "AbhayaLibre-Bold.ttf",
    "Abhaya Regular (Sinhala)": "AbhayaLibre-Regular.ttf",
    "Noto Sans (Sinhala)": "NotoSansSinhala_Condensed-Regular.ttf"
}

fonts_available = {}
print("--- Loading Fonts ---")
for name, filename in FONT_PATHS.items():
    # Construct the full path to the font file
    path = os.path.join(FONT_DIR, filename)

    # Check if the font file actually exists
    if os.path.exists(path):
        try:
            # Try loading with a small size to ensure it's a valid font file
            ImageFont.truetype(path, 20)
            fonts_available[name] = path
            print(f"✅ Loaded: {name}")
        except Exception as e:
            print(f"❌ Error loading font file '{name}' from '{path}': {e}")
    else:
        print(f"⚠️ Not Found: Font file for '{name}' at '{path}'")

if not fonts_available:
    # Fallback to a system font if no custom fonts are loaded
    print("❌ No custom fonts loaded. Falling back to a system font.")
    fonts_available["Fallback"] = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

print("--- Font loading complete ---")


# Replicate setup
try:
    import replicate
    REPLICATE_AVAILABLE = True
except ImportError:
    REPLICATE_AVAILABLE = False
    print("❌ Replicate not installed. AI generation will be disabled.")

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

IMAGE_SIZES = {
    "Instagram Post (1:1)": (1080, 1080),
    "Instagram Story (9:16)": (1080, 1920),
    "YouTube Thumbnail (16:9)": (1280, 720),
}

PRESETS = {
    "Bold & Readable": {
        "text_color": "#FFFFFF", "outline_color": "#000000",
        "outline_width": 10, "shadow_blur": 5,
        "add_shadow": True, "add_glow": False
    },
    "Elegant Gold": {
        "text_color": "#FFD700", "outline_color": "#8B4513",
        "outline_width": 6, "shadow_blur": 4,
        "add_shadow": True, "add_glow": False
    },
    "Neon Glow": {
        "text_color": "#00FFFF", "outline_color": "#FFFFFF",
        "outline_width": 3, "shadow_blur": 10,
        "add_shadow": False, "add_glow": True
    },
}

@dataclass
class TextLayer:
    id: int
    text: str
    font_style: str
    font_size: int
    text_color: str
    x: int
    y: int
    outline_width: int
    outline_color: str
    add_shadow: bool
    shadow_blur: int
    add_glow: bool
    opacity: int = 100
    visible: bool = True

# ============================================
# RENDERING FUNCTIONS
# ============================================
def parse_color(color_string: str) -> Optional[Tuple[int, int, int]]:
    """
    Parses a color string that can be in hex format (#RRGGBB)
    or rgb format (rgb(r, g, b)).
    """
    try:
        if color_string.startswith('#'):
            hex_color = color_string.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        elif color_string.startswith('rgb'):
            parts = color_string.strip('rgb()').split(',')
            return tuple(int(p.strip()) for p in parts)
    except (ValueError, TypeError, IndexError):
        print(f"---! Color Parse Error: Could not parse '{color_string}'. Defaulting color. ---")
        return None # Return None on failure
def render_text_layer(draw, layer, font):
    """Render a single text layer with effects"""
    
    # Use the new, safer color parser
    text_rgb = parse_color(layer.text_color)
    outline_rgb = parse_color(layer.outline_color)
    
    # If parsing failed for any reason, default to black/white to avoid a crash
    if text_rgb is None: text_rgb = (255, 255, 255)
    if outline_rgb is None: outline_rgb = (0, 0, 0)

    alpha = int(255 * layer.opacity / 100)
    x, y = layer.x, layer.y

    # Ensure the fill color includes alpha for transparency
    text_fill = text_rgb + (alpha,)
    outline_fill = outline_rgb + (alpha,)

    if layer.add_glow:
        # Glow effect
        for size in range(15, 0, -1):
            a = int(alpha * 0.4 * (size / 15))
            for gx in range(-size, size + 1):
                for gy in range(-size, size + 1):
                    # Only draw if within a circle for a smoother glow
                    if gx*gx + gy*gy <= size*size:
                        draw.text((x + gx, y + gy), layer.text, font=font, fill=text_rgb + (a,))

    if layer.add_shadow:
        # Shadow effect
        for offset in range(layer.shadow_blur, 0, -1):
            a = int(alpha * 0.5 * (offset / max(layer.shadow_blur, 1)))
            draw.text((x + offset*2, y + offset*2), layer.text, font=font, fill=(0, 0, 0, a))

    if layer.outline_width > 0:
        # Outline effect
        for ox in range(-layer.outline_width, layer.outline_width + 1):
            for oy in range(-layer.outline_width, layer.outline_width + 1):
                if ox*ox + oy*oy <= layer.outline_width*layer.outline_width:
                    draw.text((x + ox, y + oy), layer.text, font=font, fill=outline_fill)

    # Main text
    draw.text((x, y), layer.text, font=font, fill=text_fill)

def render_all_layers(base_image, layers):
    """Render all text layers onto base image"""
    if base_image is None:
        print("---! Render Error: Base image is None.")
        return None
    if not layers:
        return base_image.convert('RGB')

    print(f"--- Rendering {len(layers)} layers on a base image of size {base_image.size} ---")
    result = base_image.copy().convert('RGBA')
    for layer in layers:
        if not layer.visible:
            continue
        try:
            text_layer = Image.new('RGBA', result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(text_layer)
            font_path = fonts_available.get(layer.font_style, list(fonts_available.values())[0])
            font = ImageFont.truetype(font_path, layer.font_size)
            render_text_layer(draw, layer, font)
            result = Image.alpha_composite(result, text_layer)
        except Exception as e:
            print(f"---!!! CRITICAL ERROR rendering layer {layer.id}: {e} !!!---")
    
    print(f"--- Render finished successfully. Final image size: {result.size} ---")
    return result.convert('RGB')
# ============================================
# IMAGE GENERATION FUNCTIONS
# ============================================
def generate_image_with_auth(prompt, size_option, user_info, progress=gr.Progress()):
    """Generate AI image with authentication check"""
    if not user_info:
        return None, "❌ Please login first"

    # Check and increment usage
    can_generate, msg = increment_usage(user_info['id'])
    if not can_generate:
        return None, msg

    if not REPLICATE_AVAILABLE or not REPLICATE_API_TOKEN:
        return None, "❌ AI generation not available. Check REPLICATE_API_TOKEN."

    progress(0, desc="Generating...")
    width, height = IMAGE_SIZES[size_option]

    try:
        output = replicate.run(
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={"prompt": prompt, "width": width, "height": height, "num_outputs": 1}
        )
        response = requests.get(output[0])
        image = Image.open(io.BytesIO(response.content))
        return image, msg
    except Exception as e:
        return None, f"❌ Generation error: {str(e)}"

def process_uploaded_image(image):
    """Process uploaded image (always FREE)"""
    if image is None:
        return None, "❌ No image uploaded"

    max_size = 2048
    if image.width > max_size or image.height > max_size:
        ratio = min(max_size / image.width, max_size / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    return image, f"✅ Loaded: {image.width}x{image.height}px (FREE - no credits used!)"

def save_image(image, format_choice):
    """Save image to file"""
    if image is None:
        return None, "❌ No image to save"

    try:
        suffix = '.png' if "PNG" in format_choice else '.jpg'
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

        if image.mode != 'RGB':
            image = image.convert('RGB')

        if "PNG" in format_choice:
            image.save(temp_file.name, format="PNG")
        else:
            image.save(temp_file.name, format="JPEG", quality=95)

        temp_file.close()
        return temp_file.name, "✅ Ready to download!"
    except Exception as e:
        return None, f"❌ Save error: {str(e)}"

def format_layers(layers):
    """Format layers list for display"""
    if not layers:
        return "No layers yet"

    lines = []
    for l in layers:
        status = "👁️" if l.visible else "🚫"
        txt = l.text[:20] + "..." if len(l.text) > 20 else l.text
        lines.append(f"{status} Layer {l.id}: {txt}")
    return "\n".join(lines)

# ============================================
# SOCIAL MEDIA POST CREATOR FUNCTIONS
# ============================================

# Define the image sizes for social media posts
TEXT_EFFECT_SIZES = {
    "Instagram Post (1:1)": (1080, 1080),
    "Instagram Story (9:16)": (1080, 1920),
    "Facebook Post (Mobile)": (940, 788),
    "YouTube Thumbnail (16:9)": (1280, 720),
}

def create_text_effect(text, font_style, font_size, text_color, outline_color, outline_width, 
                         add_shadow, shadow_blur, bg_color, bg_type, size_preset, center_text, add_glow):
    """
    Creates an image from scratch with a custom background and text effects.
    """
    try:
        width, height = TEXT_EFFECT_SIZES[size_preset]
        
        # 1. Create the background
        if bg_type == "Transparent":
            base_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        else:
            # All other types start with a solid color and are converted to RGBA
            bg_rgb = parse_color(bg_color) if bg_color else (0,0,0)
            base_image = Image.new("RGB", (width, height), bg_rgb).convert("RGBA")
        
        # We can add more complex gradients here in the future if needed

        # 2. Prepare to draw the text
        draw = ImageDraw.Draw(base_image)
        font = ImageFont.truetype(fonts_available[font_style], font_size)

        # 3. Calculate text position
        if center_text:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (width - text_width) / 2
            y = (height - text_height) / 2
        else:
            x, y = 50, 50 # Default to top-left if not centered

        # 4. Use a TextLayer object to reuse our existing render function
        temp_layer = TextLayer(
            id=999, text=text, font_style=font_style, font_size=font_size,
            text_color=text_color, x=int(x), y=int(y), outline_width=outline_width,
            outline_color=outline_color, add_shadow=add_shadow, shadow_blur=shadow_blur,
            add_glow=add_glow, opacity=100
        )
        
        # 5. Render the text onto the background
        text_layer_image = Image.new("RGBA", base_image.size, (0,0,0,0))
        draw_text = ImageDraw.Draw(text_layer_image)
        render_text_layer(draw_text, temp_layer, font)
        
        final_image = Image.alpha_composite(base_image, text_layer_image)

        return final_image.convert("RGB"), "✅ Effect created successfully!"

    except Exception as e:
        error_message = f"❌ Error creating effect: {e}"
        print(error_message)
        # Return a blank image on error
        return Image.new("RGB", (500, 500), (0,0,0)), error_message
# ============================================
# GRADIO INTERFACE
# ============================================
def create_interface():
    """Create the main Gradio interface"""
    
    icon_dir = "app/icons"
    icon_files = []
    if os.path.exists(icon_dir):
        icon_files = [os.path.join(icon_dir, f) for f in os.listdir(icon_dir) if f.endswith(('.png', '.jpg', '.jpeg'))]

    with gr.Blocks(title="Sinhala Text Creator", theme=gr.themes.Soft()) as demo:

        user_state = gr.State(None)

        with gr.Row():
            gr.Markdown("# 🎨 Sinhala Text Creator")
            login_status = gr.Markdown("**Status:** Not logged in")

        # AUTH SECTION
        with gr.Group(visible=True) as auth_section:
            gr.Markdown("## 🔐 Login Required")
            with gr.Tabs():
                with gr.Tab("Login"):
                    login_email = gr.Textbox(label="Email", placeholder="your@email.com")
                    login_password = gr.Textbox(label="Password", type="password")
                    login_btn = gr.Button("🔑 Login", variant="primary", size="lg")
                    login_msg = gr.Textbox(label="Message")
                with gr.Tab("Register FREE"):
                    reg_email = gr.Textbox(label="Email", placeholder="your@email.com")
                    reg_password = gr.Textbox(label="Password (min 6 chars)", type="password")
                    reg_password2 = gr.Textbox(label="Confirm Password", type="password")
                    reg_btn = gr.Button("✨ Create FREE Account", variant="primary", size="lg")
                    reg_msg = gr.Textbox(label="Message")

        # MAIN APP
        with gr.Group(visible=False) as main_app:
            with gr.Accordion("📊 Your Dashboard", open=True):
                with gr.Row():
                    stats_display = gr.Markdown("Loading...")
                    logout_btn = gr.Button("🚪 Logout", size="sm")

            with gr.Tabs():

                # TAB 1: Get Image
                with gr.Tab("1️⃣ Get Image"):
                    gr.Markdown("### Get Your Base Image")
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("#### 📤 Upload (FREE)")
                            upload_img = gr.Image(label="Upload", type="pil")
                            upload_btn = gr.Button("📤 Use Image", variant="primary")
                            gr.Markdown("#### 🎨 Generate AI (Uses 1 credit)")
                            prompt = gr.Textbox(label="Prompt", lines=2, placeholder="sunset over ocean...")
                            size = gr.Dropdown(list(IMAGE_SIZES.keys()), value=list(IMAGE_SIZES.keys())[0])
                            gen_btn = gr.Button("🎨 Generate", variant="secondary")
                        with gr.Column():
                            img_display = gr.Image(label="Your Image", type="pil")
                            img_status = gr.Textbox(label="Status")

                # TAB 2: Add Text
                with gr.Tab("2️⃣ Add Text"):
                    base_image_with_graphics_state = gr.State(None) 
                    layers_state = gr.State([])
                    next_layer_id = gr.State(1)
                    history = gr.State([])
                    with gr.Row():
                        with gr.Column(scale=2):
                            preview = gr.Image(label="Click to position", type="pil")
                            with gr.Row():
                                x_coord = gr.Number(label="X", value=100, interactive=False)
                                y_coord = gr.Number(label="Y", value=100, interactive=False)
                            status = gr.Textbox(label="Status")
                        with gr.Column(scale=1):
                            text_input = gr.Textbox(label="Text", lines=2)
                            preset = gr.Dropdown(["Custom"] + list(PRESETS.keys()), value="Bold & Readable", label="Style Preset")
                            with gr.Row():
                                font = gr.Dropdown(list(fonts_available.keys()), value=list(fonts_available.keys())[0] if fonts_available else "", label="Font Style")
                                font_size = gr.Slider(20, 300, 60, label="Font Size")
                            with gr.Row():
                                text_color = gr.ColorPicker("#FFFFFF", label="Text Color")
                                outline_color = gr.ColorPicker("#000000", label="Outline Color")
                            outline_w = gr.Slider(0, 30, 10, label="Outline Width")
                            with gr.Row():
                                add_shadow = gr.Checkbox(True, label="Add Shadow")
                                add_glow = gr.Checkbox(False, label="Add Glow")
                            shadow_blur = gr.Slider(0, 20, 5, label="Shadow Blur")
                            opacity = gr.Slider(0, 100, 100, label="Opacity")
                            add_btn = gr.Button("➕ ADD TEXT", variant="primary", size="lg")
                            layers_list = gr.Textbox(label="Layers", lines=4, interactive=False)
                            with gr.Row():
                                remove_last_btn = gr.Button("🔙 Remove Last")
                                undo_btn = gr.Button("↩️ Undo")

                # TAB 3: Social Media (YOUR NEW TAB)
                with gr.Tab("3️⃣ Social Media"):
                    gr.Markdown("### Create Social Media Posts")
                    with gr.Row():
                        with gr.Column():
                            eff_txt = gr.Textbox("සුන්දර අකුරු", label="Text", lines=2)
                            eff_size_p = gr.Dropdown(list(TEXT_EFFECT_SIZES.keys()), value="Instagram Post (1:1)", label="Size")
                            eff_font = gr.Dropdown(list(fonts_available.keys()), value=list(fonts_available.keys())[0], label="Font")
                            eff_size = gr.Slider(30, 300, 120, label="Font Size")
                            with gr.Row():
                                eff_txt_col = gr.ColorPicker("#FFD700", label="Text Color")
                                eff_out_col = gr.ColorPicker("#000000", label="Outline Color")
                            eff_out_w = gr.Slider(0, 20, 6, label="Outline Width")
                            with gr.Row():
                                eff_shad = gr.Checkbox(True, label="Shadow")
                                eff_glow = gr.Checkbox(False, label="Glow")
                            eff_blur = gr.Slider(0, 20, 5, label="Shadow/Glow Blur")
                            eff_bg_type = gr.Radio(["Solid Color", "Transparent"], value="Solid Color", label="Background Type")
                            eff_bg_col = gr.ColorPicker("#1a1a2e", label="Background Color")
                            eff_center = gr.Checkbox(True, label="Center Text")
                            eff_btn = gr.Button("✨ Create Post", variant="primary", size="lg")
                        with gr.Column():
                            eff_prev = gr.Image(label="Preview", type="pil")
                            eff_status = gr.Textbox(label="Status")
                            gr.Markdown("### 💾 Download")
                            dl3_fmt = gr.Radio(["PNG", "JPG"], value="PNG", label="Format")
                            dl3_btn = gr.Button("⬇️ Download", size="lg")
                            dl3_file = gr.File(label="Download File")
                            dl3_status = gr.Textbox(label="Status")
                
                # TAB 4: Pro Tools
                with gr.Tab("✨ Pro Tools"):
                    gr.Markdown("### Add Icons & Logos (Pro Feature)")
                    selected_graphic_state = gr.State(None)
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("#### Icon Library")
                            icon_gallery = gr.Gallery(value=icon_files, label="Select an Icon", columns=8, height=300)
                            gr.Markdown("#### Or Upload Your Logo")
                            logo_upload = gr.Image(label="Upload Logo", type="pil")
                        with gr.Column():
                            gr.Markdown("#### Graphic Controls")
                            graphic_size = gr.Slider(50, 500, 150, label="Size")
                            graphic_opacity = gr.Slider(0, 100, 100, label="Opacity")
                            add_graphic_btn = gr.Button("➕ Add Icon/Logo to Image", variant="primary")
                
                # TAB 5: Upgrade
                with gr.Tab("💎 Upgrade"):
                    gr.Markdown("...") # Your upgrade text here

                # TAB 6: Admin
                with gr.Tab("🔐 Admin"):
                    gr.Markdown("...") # Your admin panel code here

            # --- EVENT HANDLERS FOR ALL TABS ---
            
            def load_image_to_tabs(image):
                return image, image, [], 1, "No layers yet", "✅ Image loaded into Text & Pro tabs."

            upload_btn.click(process_uploaded_image, [upload_img], [img_display, img_status]).then(
                load_image_to_tabs, [img_display], [base_image_with_graphics_state, preview, layers_state, next_layer_id, layers_list, status]
            )
            gen_btn.click(gen_and_update_stats, [prompt, size, user_state], [img_display, img_status, stats_display]).then(
                load_image_to_tabs, [img_display], [base_image_with_graphics_state, preview, layers_state, next_layer_id, layers_list, status]
            )

            # --- PRO TOOLS LOGIC ---
            def select_graphic(evt: gr.SelectData):
                return Image.open(evt.value).convert("RGBA")
            icon_gallery.select(select_graphic, None, selected_graphic_state)
            logo_upload.upload(lambda img: img.convert("RGBA"), logo_upload, selected_graphic_state)
            add_graphic_btn.click(
                add_graphic_layer,
                [base_image_with_graphics_state, selected_graphic_state, x_coord, y_coord, graphic_size, graphic_opacity],
                [preview, status]
            ).then(
                lambda img: img, [preview], [base_image_with_graphics_state]
            )
            
            # --- ADD TEXT LOGIC ---
            def apply_preset(preset_name):
                if preset_name in PRESETS:
                    settings = PRESETS[preset_name]
                    return settings["text_color"], settings["outline_color"], settings["outline_width"], settings["shadow_blur"], settings["add_shadow"], settings["add_glow"]
                return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
            preset.change(apply_preset, preset, [text_color, outline_color, outline_w, shadow_blur, add_shadow, add_glow])
            
            add_btn.click(
                add_text,
                [base_image_with_graphics_state, layers_state, next_layer_id, history, text_input, font, font_size, text_color, outline_color, outline_w, add_shadow, shadow_blur, add_glow, opacity, x_coord, y_coord],
                [layers_state, next_layer_id, history, layers_list, preview, status]
            )
            
            # ... [Other Add Text button handlers remain the same] ...
            
            # --- SOCIAL MEDIA TAB LOGIC ---
            eff_btn.click(create_text_effect, 
                          [eff_txt, eff_font, eff_size, eff_txt_col, eff_out_col, eff_out_w, eff_shad, eff_blur, eff_bg_col, eff_bg_type, eff_size_p, eff_center, eff_glow], 
                          [eff_prev, eff_status])
            dl3_btn.click(lambda img, fmt: save_image(img, f"{fmt} Format"), [eff_prev, dl3_fmt], [dl3_file, dl3_status])
            
            # ... [All other event handlers for login, register, admin, etc. remain the same] ...
        return demo
# ============================================
# LAUNCH
# ============================================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Sinhala Text Creator - With Admin Dashboard")
    print("=" * 50)

    # Check configuration
    if DATABASE_URL:
        print("✅ DATABASE_URL configured")
    else:
        print("❌ DATABASE_URL not found!")

    if REPLICATE_API_TOKEN:
        print("✅ REPLICATE_API_TOKEN configured")
    else:
        print("⚠️  REPLICATE_API_TOKEN not found (AI generation disabled)")

    if PSYCOPG2_AVAILABLE:
        print("✅ psycopg2 available")
        # Test connection
        conn = get_db_connection()
        if conn:
            print("✅ Database: Connected")
            conn.close()
        else:
            print("❌ Database: Connection failed")
    else:
        print("❌ psycopg2 not available")

    print("=" * 50)
    print(f"🔐 Admin Password is set: {'Yes' if ADMIN_PASSWORD else 'No'}")
    print("⚠️  Remember to change the admin password!")
    print("=" * 50)

    demo = create_interface()
    # Changed server_port to 8000 as requested
    demo.launch(server_name="0.0.0.0", server_port=8000)






