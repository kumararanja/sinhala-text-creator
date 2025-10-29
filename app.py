"""
Sinhala Text Creator - COMPLETE VERSION WITH ADMIN DASHBOARD AND ADVANCED EFFECTS
==================================================================================
Full working version with background/template selector and layer management
"""

import gradio as gr
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import os
import tempfile
import copy
from datetime import datetime
import hashlib
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
import numpy as np  # For advanced effects
import glob # For finding templates

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

def get_db_connection():
    """Get PostgreSQL database connection with better error handling"""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2-binary not installed!")
        print("Fix: Add 'psycopg2-binary' to requirements.txt")
        return None
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in Hugging Face Secrets!")
        return None
    try:
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {str(e)[:100]}")
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
            return None
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)[:100]}")
        return None

# ============================================
# USER MANAGEMENT FUNCTIONS
# ============================================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(email: str, password: str) -> Tuple[bool, str]:
    if not email or not password: return False, "❌ Email and password required"
    if len(password) < 6: return False, "❌ Password must be at least 6 characters"
    try:
        conn = get_db_connection()
        if not conn: return False, "❌ Database not available"
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone(): conn.close(); return False, "❌ Email already registered"
        password_hash = hash_password(password)
        current_month = datetime.now().strftime('%Y-%m')
        cursor.execute(''' INSERT INTO users (email, password_hash, last_reset_date) VALUES (%s, %s, %s) ''', (email, password_hash, current_month))
        conn.commit()
        conn.close()
        return True, "✅ Account created! Please login."
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def login_user(email: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    if not email or not password: return False, "❌ Email and password required", None
    try:
        conn = get_db_connection()
        if not conn: return False, "❌ Database not available", None
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        password_hash = hash_password(password)
        cursor.execute(''' SELECT id, email, plan, monthly_generations, last_reset_date, total_generations FROM users WHERE email = %s AND password_hash = %s AND is_active = true ''', (email, password_hash))
        user = cursor.fetchone()
        conn.close()
        if not user: return False, "❌ Invalid email or password", None
        current_month = datetime.now().strftime('%Y-%m')
        if user['last_reset_date'] != current_month:
            reset_monthly_usage(user['id'])
            user['monthly_generations'] = 0
        user_info = {
            'id': user['id'], 'email': user['email'], 'plan': user['plan'],
            'monthly_generations': user['monthly_generations'], 'total_generations': user['total_generations'],
            'remaining': get_remaining_generations(user['plan'], user['monthly_generations'])
        }
        return True, f"✅ Welcome back, {email}!", user_info
    except Exception as e:
        return False, f"❌ Error: {str(e)}", None

def get_remaining_generations(plan: str, used: int) -> int:
    limits = {'free': 5, 'starter': 25, 'popular': 60, 'premium': 200}
    limit = limits.get(plan, 5)
    return max(0, limit - used)

def reset_monthly_usage(user_id: int):
    try:
        conn = get_db_connection()
        if not conn: return
        cursor = conn.cursor()
        current_month = datetime.now().strftime('%Y-%m')
        cursor.execute(''' UPDATE users SET monthly_generations = 0, last_reset_date = %s WHERE id = %s ''', (current_month, user_id))
        conn.commit()
        conn.close()
    except Exception as e: print(f"Error resetting usage: {e}")

def increment_usage(user_id: int) -> Tuple[bool, str]:
    try:
        conn = get_db_connection()
        if not conn: return False, "❌ Database not available"
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(''' SELECT monthly_generations, plan FROM users WHERE id = %s ''', (user_id,))
        result = cursor.fetchone()
        if not result: conn.close(); return False, "❌ User not found"
        monthly_gens = result['monthly_generations']; plan = result['plan']
        remaining = get_remaining_generations(plan, monthly_gens)
        if remaining <= 0: conn.close(); return False, "❌ Monthly limit reached! Upgrade your plan or wait for next month."
        cursor.execute(''' UPDATE users SET monthly_generations = monthly_generations + 1, total_generations = total_generations + 1 WHERE id = %s ''', (user_id,))
        cursor.execute(''' INSERT INTO usage_logs (user_id, action_type) VALUES (%s, %s) ''', (user_id, 'ai_generation'))
        conn.commit()
        conn.close()
        new_remaining = remaining - 1
        return True, f"✅ Generated! {new_remaining} remaining this month"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def get_user_stats(user_id: int) -> str:
    try:
        conn = get_db_connection()
        if not conn: return "❌ Database not available"
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(''' SELECT email, plan, monthly_generations, total_generations, created_at FROM users WHERE id = %s ''', (user_id,))
        user = cursor.fetchone()
        conn.close()
        if user:
            remaining = get_remaining_generations(user['plan'], user['monthly_generations'])
            created_date = user['created_at'].strftime('%Y-%m-%d') if user['created_at'] else 'N/A'
            return f"""
### 👤 {user['email']}
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
ADMIN_PASSWORD = "YourAdminPass2024"
def check_admin_password(password: str) -> bool:
    return password == ADMIN_PASSWORD

def get_admin_stats() -> str:
    try:
        conn = get_db_connection()
        if not conn: return "❌ Database not available"
        cursor = conn.cursor(cursor_factory=RealDictCursor)
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
        conn.close()
        report = f"""# 📊 **ADMIN DASHBOARD**\n\n## 👥 **User Statistics**\n- **Total Users:** {total_users}\n- **New Today:** {today_signups}\n- **Active (30 days):** {active_users}\n\n## 💎 **Users by Plan**"""
        for plan in plan_stats: report += f"\n- **{plan['plan'].upper()}:** {plan['count']} users"
        report += f"""\n\n## 🎨 **Generation Statistics**\n- **Total All-Time:** {gen_stats['total_gens']} generations\n- **Used This Month:** {gen_stats['monthly_gens']} generations\n- **Average per User:** {gen_stats['total_gens'] // max(total_users, 1)} generations\n\n## 🆕 **Recent Users (Latest 15)**\n| Email | Plan | Joined | Monthly | Total |\n|-------|------|--------|---------|-------|"""
        for user in recent_users: date = user['created_at'].strftime('%m/%d') if user['created_at'] else 'N/A'; email = user['email'][:20] + '...' if len(user['email']) > 20 else user['email']; report += f"\n| {email} | {user['plan']} | {date} | {user['monthly_generations']} | {user['total_generations']} |"
        report += f"\n\n---\n*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
        return report
    except Exception as e: return f"❌ Error loading stats: {str(e)}\n\nMake sure your database tables are created."

def export_user_data() -> tuple:
    try:
        conn = get_db_connection()
        if not conn: return None, "❌ Database not available"
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT email, plan, monthly_generations, total_generations, created_at, is_active FROM users ORDER BY created_at DESC")
        users = cursor.fetchall()
        conn.close()
        if not users: return None, "No users found"
        csv_data = "Email,Plan,Monthly Usage,Total Usage,Joined Date,Status\n"
        for user in users: date = user['created_at'].strftime('%Y-%m-%d %H:%M') if user['created_at'] else 'N/A'; status = "Active" if user['is_active'] else "Inactive"; csv_data += f"{user['email']},{user['plan']},{user['monthly_generations']},{user['total_generations']},{date},{status}\n"
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        temp_file.write(csv_data)
        temp_file.close()
        return temp_file.name, f"✅ Exported {len(users)} users to CSV"
    except Exception as e: return None, f"❌ Export error: {str(e)}"

# ============================================
# FONTS & CONFIG
# ============================================
FONT_PATHS = {
    "Abhaya Regular (Sinhala)": "fonts/AbhayaLibre-Regular.ttf", "Abhaya Bold (Sinhala)": "fonts/AbhayaLibre-Bold.ttf", "Abhaya Medium (Sinhala)": "fonts/AbhayaLibre-Medium.ttf",
    "Noto Sans (Sinhala)": "fonts/NotoSansSinhala_Condensed-Regular.ttf", "Montserrat Bold": "fonts/Montserrat-Bold.ttf", "Montserrat Regular": "fonts/Montserrat-Regular.ttf",
    "Montserrat Italic": "fonts/Montserrat-Italic.ttf", "Anton": "fonts/Anton-Regular.ttf", "Bebas Neue": "fonts/BebasNeue-Regular.ttf",
    "Oswald Bold": "fonts/Oswald-Bold.ttf", "Oswald Regular": "fonts/Oswald-Regular.ttf", "Hind Madurai Bold (Tamil)": "fonts/HindMadurai-Bold.ttf",
    "Hind Madurai Regular (Tamil)": "fonts/HindMadurai-Regular.ttf", "Catamaran (Tamil)": "fonts/Catamaran-Tamil.ttf"
}
fonts_available = {}
print("--- Loading Fonts ---")
for name, path in FONT_PATHS.items():
    try:
        print(f"Attempting to load: {name} from {path}")
        if not os.path.exists(path):
             print(f"  ❌ FAILED: Font file not found at '{path}'")
             continue
        ImageFont.truetype(path, 20)
        fonts_available[name] = path
        print(f"  ✅ SUCCESS: Loaded {name}")
    except Exception as e:
         print(f"  ❌ FAILED to load font '{name}' from path '{path}': {e}")
print("--- Finished Loading Fonts ---")
if not fonts_available:
    print("⚠️ WARNING: No fonts loaded successfully. Using system fallback.")
    fonts_available["Fallback"] = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# --- NEW: Load Templates ---
template_files = glob.glob("templates/*.jpg") + glob.glob("templates/*.png") + glob.glob("templates/*.jpeg")
if not template_files:
    print("⚠️ WARNING: No templates found in 'templates' folder.")
else:
    print(f"✅ Found {len(template_files)} templates.")


try:
    import replicate
    REPLICATE_AVAILABLE = True
except:
    REPLICATE_AVAILABLE = False
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
IMAGE_SIZES = { "Instagram Post (1:1)": (1080, 1080), "Instagram Story (9:16)": (1080, 1920), "YouTube Thumbnail (16:9)": (1280, 720) }
PRESETS = {
    "Bold & Readable": {"text_color": "#FFFFFF", "outline_color": "#000000", "outline_width": 10, "shadow_blur": 5, "add_shadow": True, "add_glow": False, "effect_type": "normal"},
    "Neon Glow 🌟": {"text_color": "#00FFFF", "outline_color": "#FF00FF", "outline_width": 3, "shadow_blur": 20, "add_shadow": False, "add_glow": True, "effect_type": "neon"},
    "Chrome Metal ⚙️": {"text_color": "#C0C0C0", "outline_color": "#808080", "outline_width": 4, "shadow_blur": 8, "add_shadow": True, "add_glow": False, "effect_type": "chrome"},
    "Fire Text 🔥": {"text_color": "#FF4500", "outline_color": "#FFD700", "outline_width": 5, "shadow_blur": 15, "add_shadow": True, "add_glow": True, "effect_type": "fire"},
    "Ice Frozen ❄️": {"text_color": "#B0E0E6", "outline_color": "#4682B4", "outline_width": 6, "shadow_blur": 10, "add_shadow": True, "add_glow": True, "effect_type": "normal"},
    "3D Shadow": {"text_color": "#FFFFFF", "outline_color": "#000000", "outline_width": 2, "shadow_blur": 0, "add_shadow": True, "add_glow": False, "effect_type": "3d"},
    "Gradient Rainbow 🌈": {"text_color": "#FF1493", "outline_color": "#8A2BE2", "outline_width": 3, "shadow_blur": 5, "add_shadow": False, "add_glow": False, "effect_type": "gradient"},
    "Gold Luxury 👑": {"text_color": "#FFD700", "outline_color": "#B8860B", "outline_width": 8, "shadow_blur": 10, "add_shadow": True, "add_glow": False, "effect_type": "normal"}
}


@dataclass
class TextLayer: # For Tab 2
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
    effect_type: str = "normal"

@dataclass
class SocialLayer: # For Tab 4
    id: int
    type: str # 'text' or 'logo'
    properties: Dict[str, Any]
    visible: bool = True

# ============================================
# ADVANCED RENDERING FUNCTIONS (for Tab 2 & 4)
# ============================================
def apply_neon_effect(draw, text, font, x, y, base_color, glow_color, intensity=3):
    """Create neon glow effect"""
    base_rgb = tuple(int(base_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    glow_rgb = tuple(int(glow_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    for glow_size in range(intensity*5, 0, -1):
        alpha = int(120 * (glow_size / (intensity*5)))
        for angle in range(0, 360, 30):
            gx = int(glow_size * 0.5 * np.cos(np.radians(angle)))
            gy = int(glow_size * 0.5 * np.sin(np.radians(angle)))
            draw.text((x + gx, y + gy), text, font=font, fill=glow_rgb + (alpha,))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    draw.text((x, y), text, font=font, fill=base_rgb + (200,))

def apply_chrome_effect(draw, text, font, x, y):
    """Create chrome/metallic effect"""
    for offset in range(3, -1, -1):
        gray_value = 80 + offset * 40
        draw.text((x - offset, y - offset), text, font=font, fill=(gray_value, gray_value, gray_value, 255))
    draw.text((x + 1, y + 1), text, font=font, fill=(255, 255, 255, 180))
    draw.text((x, y), text, font=font, fill=(192, 192, 192, 255))

def apply_fire_effect(draw, text, font, x, y):
    """Create fire effect"""
    fire_colors = [
        (255, 255, 0),    # Yellow core
        (255, 200, 0),    # Orange-yellow
        (255, 140, 0),    # Orange
        (255, 69, 0),     # Red-orange
        (139, 0, 0)       # Dark red
    ]
    for i, color in enumerate(fire_colors):
        offset = i * 2
        alpha = 255 - (i * 40)
        draw.text((x, y - offset), text, font=font, fill=color + (alpha,))
        if i > 0:
            draw.text((x - 1, y - offset + 1), text, font=font, fill=color + (alpha//2,))
            draw.text((x + 1, y - offset + 1), text, font=font, fill=color + (alpha//2,))

def apply_3d_shadow_effect(draw, text, font, x, y, text_color, shadow_color, depth=5):
    """Create 3D shadow effect"""
    text_rgb = tuple(int(text_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    shadow_rgb = tuple(int(shadow_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    for i in range(depth, 0, -1):
        draw.text((x + i*2, y + i*2), text, font=font, fill=shadow_rgb + (200,))
    draw.text((x, y), text, font=font, fill=text_rgb + (255,))

def apply_gradient_effect(image, draw, text, font, x, y, color1, color2):
    """Create gradient text effect"""
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    gradient = Image.new('RGBA', (text_width, text_height), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    c1_rgb = tuple(int(color1.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    c2_rgb = tuple(int(color2.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    for i in range(text_height):
        ratio = i / text_height
        r = int(c1_rgb[0] * (1 - ratio) + c2_rgb[0] * ratio)
        g = int(c1_rgb[1] * (1 - ratio) + c2_rgb[1] * ratio)
        b = int(c1_rgb[2] * (1 - ratio) + c2_rgb[2] * ratio)
        grad_draw.rectangle([0, i, text_width, i+1], fill=(r, g, b, 255))
    mask = Image.new('L', (text_width, text_height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.text((0, 0), text, font=font, fill=255)
    gradient.putalpha(mask)
    image.paste(gradient, (x, y), gradient)

def render_text_layer(draw, layer, font):
    """Basic text rendering for Tab 2"""
    text_rgb = tuple(int(layer.text_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    if layer.outline_width > 0:
        outline_rgb = tuple(int(layer.outline_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        for dx in [-layer.outline_width, 0, layer.outline_width]:
            for dy in [-layer.outline_width, 0, layer.outline_width]:
                if dx != 0 or dy != 0:
                    draw.text((layer.x + dx, layer.y + dy), layer.text, font=font, fill=outline_rgb)
    draw.text((layer.x, layer.y), layer.text, font=font, fill=text_rgb)

def render_text_layer_advanced(draw, layer, font, image=None):
    """Advanced text rendering with effects for Tab 2"""
    if layer.effect_type == "neon":
        apply_neon_effect(draw, layer.text, font, layer.x, layer.y, layer.text_color, layer.outline_color)
    elif layer.effect_type == "chrome":
        apply_chrome_effect(draw, layer.text, font, layer.x, layer.y)
    elif layer.effect_type == "fire":
        apply_fire_effect(draw, layer.text, font, layer.x, layer.y)
    elif layer.effect_type == "3d":
        apply_3d_shadow_effect(draw, layer.text, font, layer.x, layer.y, layer.text_color, layer.outline_color)
    elif layer.effect_type == "gradient" and image:
        apply_gradient_effect(image, draw, layer.text, font, layer.x, layer.y, layer.text_color, layer.outline_color)
    else:
        render_text_layer(draw, layer, font)

def render_social_text_layer(draw, props, image=None):
    """Renderer for social post text layers, using effect functions - FIXED VERSION"""
    font_path = fonts_available.get(props.get('font_key'), list(fonts_available.values())[0])
    
    # HARDCODE COLORS FOR TESTING
    if props.get('is_heading'):
        color_rgb = (255, 0, 0)  # RED for headings
    else:
        color_rgb = (0, 0, 255)  # BLUE for paragraphs

    # Use custom font size if provided, otherwise calculate based on image size
    custom_font_size = props.get('font_size')
    if custom_font_size:
        font_size = custom_font_size
    else:
        width, _ = image.size
        heading_font_size = max(30, int(width / 18))
        para_font_size = max(20, int(width / 35))
        font_size = heading_font_size if props.get('is_heading') else para_font_size
    
    font_obj = ImageFont.truetype(font_path, font_size)
    text = props.get('text', '')
    color = props.get('color', '#000000')
    alignment = props.get('align', 'Left')
    is_heading = props.get('is_heading', False)
    effect = props.get('effect_type', 'normal')
    outline_color = props.get('outline_color', '#000000')
    
    width, height = image.size
    
    # Calculate text positioning - FIXED: Use custom x,y if provided for BOTH heading and paragraph
    if 'x' in props and 'y' in props:
        # Use custom position from click for BOTH heading and paragraph
        text_x = props['x']
        text_y = props['y']
        text_anchor = "lt"  # Left top anchor for custom positioning
    else:
        # Use default positioning (fallback)
        if is_heading:
            # For heading - center at top
            bbox = draw.textbbox((0, 0), text, font=font_obj, anchor="lt")
            text_width = bbox[2] - bbox[0]
            text_x = width // 2
            text_y = int(height * 0.1)  # 10% from top
            text_anchor = "mt"  # Middle top
        else:
            # For paragraph - start higher up (15% from top instead of 25%)
            text_y = int(height * 0.15)
            
            # Handle alignment
            if alignment == "Center":
                text_anchor = "mt"
                text_x = width // 2
            elif alignment == "Right":
                text_anchor = "rt"
                text_x = int(width * 0.9)
            else:  # Left alignment
                text_anchor = "lt"
                text_x = int(width * 0.1)
    
    # Handle multi-line text for paragraphs
    if not is_heading and '\n' in text:
        lines = text.split('\n')
        line_height = font_size + 10  # Add spacing between lines
        
        for i, line in enumerate(lines):
            current_y = text_y + (i * line_height)
            
            # Call effect renderers for each line
            if effect == "neon":
                apply_neon_effect(draw, line, font_obj, text_x, current_y, color, outline_color)
            elif effect == "chrome":
                apply_chrome_effect(draw, line, font_obj, text_x, current_y)
            elif effect == "fire":
                apply_fire_effect(draw, line, font_obj, text_x, current_y)
            elif effect == "3d":
                apply_3d_shadow_effect(draw, line, font_obj, text_x, current_y, color, outline_color)
            elif effect == "gradient" and image:
                apply_gradient_effect(image, draw, line, font_obj, text_x, current_y, color, outline_color)
            else:
                # Convert hex color to RGB tuple
                if isinstance(color, str) and color.startswith('#'):
                    color_rgb = tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                else:
                    color_rgb = (0, 0, 0)
                draw.text((text_x, current_y), line, fill=color_rgb, font=font_obj, anchor=text_anchor)
        return
    
    # Single line text or heading
    if effect == "neon":
        apply_neon_effect(draw, text, font_obj, text_x, text_y, color, outline_color)
    elif effect == "chrome":
        apply_chrome_effect(draw, text, font_obj, text_x, text_y)
    elif effect == "fire":
        apply_fire_effect(draw, text, font_obj, text_x, text_y)
    elif effect == "3d":
        apply_3d_shadow_effect(draw, text, font_obj, text_x, text_y, color, outline_color)
    elif effect == "gradient" and image:
        apply_gradient_effect(image, draw, text, font_obj, text_x, text_y, color, outline_color)
    else:
        # Convert hex color to RGB tuple
        if isinstance(color, str) and color.startswith('#'):
            color_rgb = tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        else:
            color_rgb = (0, 0, 0)
        draw.text((text_x, text_y), text, fill=color_rgb, font=font_obj, anchor=text_anchor)

# --- RENDERER FOR TAB 2 ---
def render_all_layers(base_image, layers: List[TextLayer]):
    """Render all text layers onto base image with advanced effects for Tab 2"""
    if base_image is None or not layers:
        return base_image
    result = base_image.copy().convert('RGBA')
    for layer in layers:
        if not layer.visible:
            continue
        try:
            text_layer_img = Image.new('RGBA', result.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(text_layer_img)
            font_path = fonts_available.get(layer.font_style, list(fonts_available.values())[0])
            font = ImageFont.truetype(font_path, layer.font_size)
            if hasattr(layer, 'effect_type') and layer.effect_type != "normal":
                if layer.effect_type == "gradient":
                    render_text_layer_advanced(draw, layer, font, text_layer_img)
                else:
                    render_text_layer_advanced(draw, layer, font)
            else:
                render_text_layer(draw, layer, font) # Call original simple renderer
            result = Image.alpha_composite(result, text_layer_img)
        except Exception as e:
            print(f"Error rendering layer ID {layer.id}: {e}")
    return result.convert('RGB')


# --- RENDERER FOR TAB 4 (SOCIAL POST) ---
# --- MOVED post_sizes dictionary TO GLOBAL SCOPE ---
post_sizes = {
    "Instagram Square (1:1)": (1080, 1080),
    "Instagram Story (9:16)": (1080, 1920),
    "Facebook Post (1.91:1)": (1200, 630),
    "Twitter Post (16:9)": (1600, 900)
}

def render_social_post(size_key, bg_color, template_path, bg_type, social_layers: List[SocialLayer], base_image=None):
    """Renders the social post - UPDATED to accept base_image parameter"""
    try:
        width, height = post_sizes[size_key]
        
        # Use provided base image if available
        if base_image is not None:
            print("Using provided base image in render_social_post")
            img = base_image.copy().convert('RGBA') if base_image.mode != 'RGBA' else base_image.copy()
        else:
            # --- Create base image from color OR template ---
            if bg_type == "Template" and template_path:
                try:
                    # Handle dictionary responses
                    if isinstance(template_path, dict):
                        template_path = template_path.get('name') or template_path.get('data') or list(template_path.values())[0]
                    
                    if isinstance(template_path, str) and os.path.exists(template_path):
                        img = Image.open(template_path).convert('RGBA')
                        img = img.resize((width, height), Image.Resampling.LANCZOS)
                        print(f"Loaded template: {template_path}")
                    else:
                        raise FileNotFoundError("Template path is invalid")
                except Exception as e:
                    print(f"Error loading template '{template_path}': {e}, defaulting to white.")
                    if not isinstance(bg_color, str) or not bg_color.startswith('#'): 
                        bg_color = "#FFFFFF"
                    img = Image.new('RGBA', (width, height), bg_color)
            else:
                print(f"Rendering social post with bg_color: {bg_color}")
                if not isinstance(bg_color, str) or not bg_color.startswith('#'):
                    print(f"Warning: Invalid bg_color '{bg_color}', defaulting to white.")
                    bg_color = "#FFFFFF"
                img = Image.new('RGBA', (width, height), bg_color)
        
        draw = ImageDraw.Draw(img)

        for layer in social_layers:
            if not layer.visible:
                continue
            props = layer.properties
            if layer.type == 'text':
                try:
                    render_social_text_layer(draw, props, img)
                except Exception as e:
                    print(f"Error drawing text layer {layer.id}: {e}")
            elif layer.type == 'logo':
                try:
                    uploaded_logo = props.get('logo_obj')
                    if not uploaded_logo:
                        continue
                    logo_size_str = props.get('size_str', 'Medium (100px)')
                    logo_x_pos = props.get('x', 50)
                    logo_y_pos = props.get('y', 50)
                    if "Small" in logo_size_str:
                        target_size = 50
                    elif "Large" in logo_size_str:
                        target_size = 150
                    else:
                        target_size = 100
                    logo = uploaded_logo.copy()
                    logo.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                    paste_x = max(0, int(logo_x_pos) - logo.width // 2)
                    paste_y = max(0, int(logo_y_pos) - logo.height // 2)
                    paste_x = min(paste_x, width - logo.width)
                    paste_y = min(paste_y, height - logo.height)
                    if logo.mode == 'RGBA':
                        img.paste(logo, (paste_x, paste_y), logo)
                    else:
                        img.paste(logo, (paste_x, paste_y))
                except Exception as e:
                    print(f"Error drawing logo layer {layer.id}: {e}")

        final_rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        final_rgb_img.paste(img, mask=img.split()[3])
        return final_rgb_img
    except Exception as e:
        print(f"Error rendering social post: {e}")
        error_img = Image.new('RGB', (300, 100), color = 'grey')
        draw = ImageDraw.Draw(error_img)
        draw.text((10, 10), f"Render Error: {e}", fill='white')
        return error_img

# ============================================
# IMAGE GENERATION FUNCTIONS
# ============================================
def generate_image_with_auth(prompt, size_option, user_info, progress=gr.Progress()):
    if not user_info: return None, "❌ Please login first"
    can_generate, msg = increment_usage(user_info['id'])
    if not can_generate: return None, msg
    if not REPLICATE_AVAILABLE or not REPLICATE_API_TOKEN: return None, "❌ AI generation not available. Check REPLICATE_API_TOKEN."
    progress(0, desc="Generating...")
    width, height = IMAGE_SIZES[size_option]
    try:
        output = replicate.run("stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b", input={"prompt": prompt, "width": width, "height": height, "num_outputs": 1})
        response = requests.get(output[0])
        image = Image.open(io.BytesIO(response.content))
        return image, msg
    except Exception as e:
        return None, f"❌ Generation error: {str(e)}"

def process_uploaded_image(image):
    if image is None: return None, "❌ No image uploaded"
    max_size = 2048
    if image.width > max_size or image.height > max_size:
        ratio = min(max_size / image.width, max_size / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    return image, f"✅ Loaded: {image.width}x{image.height}px (FREE - no credits used!)"

# --- UPDATED save_image function ---
def save_image(image_data, format_choice):
    if image_data is None: return None, "❌ No image to save"
    pil_image = None
    if isinstance(image_data, np.ndarray):
        try:
            if image_data.dtype != np.uint8:
                if image_data.max() <= 1.0 and image_data.min() >= 0.0: image_data = (image_data * 255).astype(np.uint8)
                else: image_data = image_data.astype(np.uint8)
            pil_image = Image.fromarray(image_data)
            print("Converted NumPy array to PIL Image for saving.")
        except Exception as e:
            print(f"Error converting NumPy array to PIL Image: {e}")
            return None, f"❌ Save error: Could not convert image data - {e}"
    elif isinstance(image_data, Image.Image):
        pil_image = image_data
    else:
        if image_data is None: return None, "❌ No image data available to save."
        return None, f"❌ Save error: Unknown image data type: {type(image_data)}"
    
    if pil_image is None: return None, "❌ Failed to prepare image for saving."
    
    try:
        suffix = '.png' if "PNG" in format_choice else '.jpg'
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        img_to_save = pil_image
        if img_to_save.mode != 'RGB':
            if "JPEG" in format_choice and img_to_save.mode == 'RGBA':
                background = Image.new("RGB", img_to_save.size, (255, 255, 255))
                background.paste(img_to_save, mask=img_to_save.split()[3])
                img_to_save = background
            else:
                img_to_save = img_to_save.convert('RGB')
        
        if "PNG" in format_choice:
            img_to_save.save(temp_file.name, format="PNG")
        else:
            img_to_save.save(temp_file.name, format="JPEG", quality=95)
            
        temp_file.close()
        print(f"Image saved temporarily to: {temp_file.name}")
        return temp_file.name, "✅ Ready to download!"
    except Exception as e:
        print(f"Error during image save: {e}")
        return None, f"❌ Save error: {e}"


# --- Functions to format layer lists ---
def format_layers(layers: List[TextLayer]): # For Tab 2
    if not layers: return "No layers yet"
    lines = []
    for l in layers:
        status = "👁️" if l.visible else "🚫"
        txt = l.text[:20] + "..." if len(l.text) > 20 else l.text
        lines.append(f"{status} Layer {l.id}: {txt} ({l.effect_type})")
    return "\n".join(lines)

def format_social_layers(social_layers: List[SocialLayer]) -> str:
    """Format social post layers list for display"""
    if not social_layers:
        return "No elements added yet"
    lines = []
    for layer in social_layers:
        status = "👁️" if layer.visible else "🚫"
        layer_type = layer.type.capitalize()
        desc = ""
        if layer.type == 'text':
            text = layer.properties.get('text', '')
            desc = text[:20] + "..." if len(text) > 20 else text
        elif layer.type == 'logo':
            desc = f"Logo ({layer.properties.get('size_str', 'Unknown size')})"
        lines.append(f"{status} Layer {layer.id}: {layer_type} - {desc}")
    return "\n".join(lines)


# ============================================
# GRADIO INTERFACE
# ============================================

def create_interface():
    """Create the main Gradio interface"""
    print("in create_interface")

    with gr.Blocks(title="Sinhala Text Creator", theme=gr.themes.Soft()) as demo:

        user_state = gr.State(None)

        # --- UPDATED INTRO HTML ---
        gr.HTML("""
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&family=Noto+Sans+Sinhala:wght@400;700;800&display=swap" rel="stylesheet">
        <style>
            .hero-container {
                padding: 60px 30px;
                background: linear-gradient(120deg, #5f72bd 0%, #a4508b 100%); /* New gradient */
                border-radius: 25px; /* Softer radius */
                margin-bottom: 40px;
                text-align: center;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
                font-family: 'Poppins', sans-serif;
                overflow: hidden; /* Prevent potential overflows */
                position: relative; /* For pseudo-elements if needed later */
            }
            .hero-title {
                font-size: 60px; /* Slightly larger */
                font-weight: 800; /* Extra bold */
                color: white;
                margin-bottom: 15px;
                text-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
                letter-spacing: 0.5px;
            }
            .hero-subtitle {
                font-size: 20px;
                font-weight: 300;
                color: #e0e7ff;
                margin-bottom: 45px;
                letter-spacing: 3px;
                text-transform: uppercase; /* Uppercase for style */
                opacity: 0.85;
            }
            .content-wrapper {
                max-width: 900px; /* Slightly narrower */
                margin: 0 auto 40px auto;
                background: rgba(255, 255, 255, 1); /* Fully opaque */
                border-radius: 20px;
                padding: 40px 50px;
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
            }
            .lang-box {
                padding: 30px;
                border-radius: 15px;
                margin-bottom: 25px;
                border-left: 5px solid;
                text-align: left;
                transition: transform 0.3s ease, box-shadow 0.3s ease;
            }
            .lang-box:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.1);
            }
            .lang-box h3 {
                font-size: 26px;
                font-weight: 700;
                margin: 0 0 15px 0;
                font-family: 'Noto Sans Sinhala', 'Poppins', sans-serif;
            }
            .lang-box p {
                font-size: 17px;
                line-height: 1.7;
                margin: 0;
                font-family: 'Noto Sans Sinhala', 'Poppins', sans-serif;
            }
            .sinhala-box {
                background: #fff9e6; /* Soft yellow */
                border-color: #764ba2;
                color: #444;
            }
            .sinhala-box h3 { color: #5a3e75; }

            .english-box {
                background: #eef2ff; /* Soft blue */
                border-color: #ffc872; /* Match Sinhala border accent */
                color: #444;
                margin-bottom: 0;
            }
             .english-box h3 { color: #506aac; }

            .features-grid {
                display: flex; /* Use flexbox */
                flex-wrap: wrap; /* Allow wrapping */
                justify-content: center; /* Center items */
                gap: 15px; /* Space between tags */
                margin-top: 30px; /* Space above tags */
            }
            .feature-pill {
                background: rgba(255, 255, 255, 0.15);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2);
                color: white;
                padding: 12px 25px;
                border-radius: 50px; /* Pill shape */
                font-size: 15px;
                font-weight: 500; /* Medium weight */
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
                transition: all 0.25s ease-out;
                cursor: default; /* Indicate non-clickable */
            }
            .feature-pill:hover {
                background: rgba(255, 255, 255, 0.25);
                transform: translateY(-3px) scale(1.03);
                box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
            }
        </style>

        <div class="hero-container">
            <h1 class="hero-title">🌟 AkuruAI – අකුරුAI 🌟</h1>
            <p class="hero-subtitle">Powered by Lanka AI Nexus</p>

            <div class="content-wrapper">
                <div class="lang-box sinhala-box">
                    <h3>🇱🇰 සිංහල</h3>
                    <p>
                        <strong>AkuruAI (අකුරුAI)</strong> යනු ශ්‍රී ලංකාවේ ප්‍රථම සිංහල AI නිර්මාණාත්මක මෙවලමයි.
                        මෙය භාවිතයෙන් ඔබට AI පින්තූර නිර්මාණය කර, ඒවාට සිංහල අකුරු යොදා, සජීවීකරණ ප්‍රයෝග එක් කළ හැකිය.
                    </p>
                </div>
                <div class="lang-box english-box">
                    <h3>🌍 English</h3>
                    <p>
                        <strong>AkuruAI</strong> is Sri Lanka's first Sinhala AI creative tool that brings artificial intelligence, language, and art together.
                        With AkuruAI, you can instantly create stunning AI-generated images, add Sinhala text, and animate them with smart effects — all in one place.
                    </p>
                </div>
            </div>

            <div class="features-grid">
                <span class="feature-pill">✨ AI Image Generation</span>
                <span class="feature-pill">✍️ Sinhala Typography</span>
                <span class="feature-pill">🎨 Smart Effects</span>
                <span class="feature-pill">🆓 Free to Start</span>
            </div>
        </div>
        """)
        # --- END INTRO HTML ---

        with gr.Row():
            login_status = gr.Markdown("**Status:** Not logged in", elem_id="login_status_md")

        # --- AUTH SECTION - UPDATED WITH 2 COLUMNS ---
        with gr.Group(visible=True) as auth_section:
            with gr.Row(equal_height=True):
                with gr.Column(scale=1):
                    gr.Markdown("## 🔐 Login or Register")
                    with gr.Tabs():
                        with gr.Tab("Login"):
                            login_email = gr.Textbox(label="Email", placeholder="your@email.com")
                            login_password = gr.Textbox(label="Password", type="password")
                            login_btn = gr.Button("🔑 Login", variant="primary", size="lg")
                            login_msg = gr.Textbox(label="Message", interactive=False)
                        with gr.Tab("Register FREE"):
                            reg_email = gr.Textbox(label="Email", placeholder="your@email.com")
                            reg_password = gr.Textbox(label="Password (min 6 chars)", type="password")
                            reg_password2 = gr.Textbox(label="Confirm Password", type="password")
                            reg_btn = gr.Button("✨ Create FREE Account", variant="primary", size="lg")
                            reg_msg = gr.Textbox(label="Message", interactive=False)
                with gr.Column(scale=1):
                    gr.Image( value="login_image.jpg", label="Auth Image", show_label=False, container=False, show_download_button=False )

        # MAIN APP
        with gr.Group(visible=False) as main_app:

            with gr.Accordion("📊 Your Dashboard", open=True):
                with gr.Row():
                    stats_display = gr.Markdown("Loading...")
                    logout_btn = gr.Button("🚪 Logout", size="sm")

            # --- CORRECTED INDENTATION ---
            with gr.Tabs(): # This line should be at the same level as the Accordion

                # TAB 1 - Get Image
                with gr.Tab("1️⃣ Get Image"):
                    gr.Markdown("### Get Your Base Image")
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("#### 📤 Upload (FREE)")
                            upload_img = gr.Image(label="Upload", type="pil")
                            upload_btn = gr.Button("📤 Use Image", variant="primary")
                        with gr.Column():
                            gr.Markdown("#### 🎨 Generate AI (Uses 1 credit)")
                            prompt = gr.Textbox(label="Prompt", lines=2, placeholder="sunset over ocean...")
                            size = gr.Dropdown(list(IMAGE_SIZES.keys()), value=list(IMAGE_SIZES.keys())[0])
                            gen_btn = gr.Button("🎨 Generate", variant="secondary")
                        with gr.Column():
                            img_display = gr.Image(label="Your Image", type="pil")
                            img_status = gr.Textbox(label="Status")

                # TAB 2 - Add Text Effects
                with gr.Tab("2️⃣ Add Text Effects"):
                    gr.Markdown("### 🎨 Advanced Text Effects Studio")
                    base_image_state = gr.State(None)
                    layers_state = gr.State([]) # State for Tab 2 layers
                    next_layer_id = gr.State(1)
                    history = gr.State([])
                    with gr.Row():
                        with gr.Column():
                            load_btn = gr.Button("🔄 Load Image from Tab 1", variant="primary", size="lg")
                            preview = gr.Image(label="Click to position text", type="pil")
                            with gr.Row():
                                x_coord = gr.Number(label="X Position", value=100, precision=0)
                                y_coord = gr.Number(label="Y Position", value=100, precision=0)
                            status = gr.Textbox(label="Status", interactive=False)
                        with gr.Column():
                            text_input = gr.Textbox( label="✍️ Enter Your Text", lines=2, placeholder="Type your text here..." )
                            preset = gr.Dropdown( ["Custom"] + list(PRESETS.keys()), value="Neon Glow 🌟", label="✨ Quick Effect Presets" )
                            with gr.Row():
                                font = gr.Dropdown( list(fonts_available.keys()), value=list(fonts_available.keys())[0], label="Font Style" )
                                font_size = gr.Slider(20, 300, 80, label="Font Size", step=5)
                            gr.Markdown("### 🎨 Colors")
                            with gr.Row():
                                text_color = gr.ColorPicker( value="#FFFFFF", label="📝 Text Color", interactive=True, elem_id="text_color_picker" )
                                outline_color = gr.ColorPicker( value="#000000", label="🔲 Outline/Glow Color", interactive=True, elem_id="outline_color_picker" )
                            with gr.Accordion("⚙️ Advanced Effect Controls", open=True):
                                effect_type = gr.Dropdown( ["normal", "neon", "chrome", "fire", "3d", "gradient"], value="neon", label="Effect Style" )
                                outline_w = gr.Slider(0, 30, 3, label="Outline Width", step=1)
                                with gr.Row():
                                    add_shadow = gr.Checkbox(label="Add Shadow", value=False)
                                    add_glow = gr.Checkbox(label="Add Glow", value=True)
                                shadow_blur = gr.Slider(0, 50, 20, label="Shadow/Glow Blur", step=1)
                                opacity = gr.Slider(0, 100, 100, label="Text Opacity %", step=5)
                            add_btn = gr.Button("➕ ADD TEXT TO IMAGE", variant="primary", size="lg")
                            layers_list = gr.Textbox( label="📝 Text Layers", lines=5, value="No layers yet" )
                            with gr.Row():
                                remove_last_btn = gr.Button("🔙 Remove Last", variant="secondary")
                                undo_btn = gr.Button("↩️ Undo", variant="secondary")
                                clear_all_btn = gr.Button("🗑️ Clear All", variant="stop")
                    
                    # --- Event Handlers for Tab 2 ---
                    load_btn.click(
                        lambda x: (x, "✅ Image loaded! Click on image to position text") if x else (None, "❌ No image in Tab 1"),
                        [img_display],
                        [preview, status]
                    ).then(
                        lambda x: x,
                        [img_display],
                        [base_image_state]
                    )
                    
                    def handle_click(evt: gr.SelectData):
                        return evt.index[0], evt.index[1], f"📍 Position set: ({evt.index[0]}, {evt.index[1]})"
                    preview.select(handle_click, None, [x_coord, y_coord, status])
                    
                    def update_from_preset(preset_name):
                        if preset_name in PRESETS:
                            p = PRESETS[preset_name]
                            return ( p.get("text_color", "#FFFFFF"), p.get("outline_color", "#000000"), p.get("outline_width", 10), p.get("shadow_blur", 5), p.get("add_shadow", True), p.get("add_glow", False), p.get("effect_type", "normal") )
                        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
                    preset.change(
                        update_from_preset,
                        [preset],
                        [text_color, outline_color, outline_w, shadow_blur, add_shadow, add_glow, effect_type]
                    )
                    
                    def add_text(base, layers, next_id, hist, txt, fnt, sz, tcol, ocol, ow, shad, blur, glow, opac, x, y, effect_type):
                        if not base: return layers, next_id, hist, format_layers(layers), None, "❌ Load image first"
                        if not txt.strip(): return layers, next_id, hist, format_layers(layers), None, "❌ Enter text"
                        hist = (hist + [copy.deepcopy(layers)])[-20:]
                        new_layer = TextLayer( next_id, txt, fnt, int(sz), tcol, int(x), int(y), int(ow), ocol, shad, int(blur), glow, int(opac), True, effect_type )
                        layers = layers + [new_layer]
                        result = render_all_layers(base, layers)
                        return layers, next_id + 1, hist, format_layers(layers), result, f"✅ Added Layer {next_id} with {effect_type} effect"
                    add_btn.click(
                        add_text,
                        [base_image_state, layers_state, next_layer_id, history, text_input, font, font_size, text_color, outline_color, outline_w, add_shadow, shadow_blur, add_glow, opacity, x_coord, y_coord, effect_type],
                        [layers_state, next_layer_id, history, layers_list, preview, status]
                    )
                    
                    def remove_last(base, layers, hist):
                        if not layers: return layers, hist, format_layers(layers), None, "⚠️ No layers"
                        hist = (hist + [copy.deepcopy(layers)])[-20:]
                        layers = layers[:-1]
                        result = render_all_layers(base, layers) if base else None
                        return layers, hist, format_layers(layers) if layers else "No layers yet", result, "✅ Removed last layer"
                    remove_last_btn.click(
                        remove_last,
                        [base_image_state, layers_state, history],
                        [layers_state, history, layers_list, preview, status]
                    )
                    
                    def undo(base, layers, hist):
                        if not hist: return layers, hist, format_layers(layers), None, "⚠️ Nothing to undo"
                        layers = copy.deepcopy(hist[-1])
                        hist = hist[:-1]
                        result = render_all_layers(base, layers) if base else None
                        return layers, hist, format_layers(layers) if layers else "No layers yet", result, "↩️ Undone"
                    undo_btn.click(
                        undo,
                        [base_image_state, layers_state, history],
                        [layers_state, history, layers_list, preview, status]
                    )
                    
                    def clear_all_layers(base):
                        if base: return [], 1, [], "No layers yet", base, "✅ All layers cleared"
                        return [], 1, [], "No layers yet", None, "⚠️ No image loaded"
                    clear_all_btn.click(
                        clear_all_layers,
                        [base_image_state],
                        [layers_state, next_layer_id, history, layers_list, preview, status]
                    )
                    
                    gr.Markdown("---")
                    gr.Markdown("### 💾 Download Your Image")
                    with gr.Row():
                        format_choice = gr.Dropdown(["JPEG (Smaller File)", "PNG (Higher Quality)"], value="JPEG (Smaller File)", label="Choose Format")
                        prepare_download_btn = gr.Button("🚀 Prepare Download", variant="primary")
                    with gr.Row():
                        download_file = gr.File(label="Download Link", interactive=False)
                        download_status = gr.Textbox(label="Status", interactive=False)
                    prepare_download_btn.click(
                        fn=save_image,
                        inputs=[preview, format_choice],
                        outputs=[download_file, download_status]
                    )

                # TAB 3 - UPGRADE
                with gr.Tab("💎 Upgrade"):
                   gr.Markdown(""" ... Pricing Plans ... """) # Minified

                # --- TAB 4 - SOCIAL POST CREATOR ---
                with gr.Tab("📢 Social Post Creator"):
                    gr.Markdown("## 🖼️ Create Simple Social Media Posts")
                    
                    social_post_base_image = gr.State(None)
                    social_layers_state = gr.State([])
                    social_next_layer_id = gr.State(1)
                    social_history = gr.State([])
                    logo_image_state = gr.State(None)
                    social_effect_type_state = gr.State("normal")
                    template_selection_state = gr.State(None)
                    
                    # NEW: Add state for positioning
                    heading_x_state = gr.State(0)
                    heading_y_state = gr.State(0)
                    paragraph_x_state = gr.State(0)
                    paragraph_y_state = gr.State(0)
                    logo_x_state = gr.State(0)
                    logo_y_state = gr.State(0)
                    current_positioning_mode = gr.State("paragraph")  # Default to paragraph positioning

                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### 1. Setup")
                            post_size_dd = gr.Dropdown(list(post_sizes.keys()), label="Select Post Size", value="Instagram Square (1:1)")
                            
                            bg_type_radio = gr.Radio(["Solid Color", "Template"], label="Background Type", value="Solid Color")
                            
                            # Solid Color controls
                            with gr.Column(visible=True) as solid_color_controls:
                                bg_color_picker = gr.ColorPicker(value="#FFFFFF", label="Background Color", interactive=True)
                                create_canvas_btn = gr.Button("Set Background & Size", variant="secondary")

                            # Template controls
                            with gr.Column(visible=False) as template_controls:
                                template_gallery = gr.Gallery(value=template_files, label="Select a Template", columns=5, height=120, allow_preview=False)
                                gr.Markdown("*(Click a template to set it as the background)*")
                            
                            gr.Markdown("### 2. Add Elements")
                            
                            # Positioning Mode Selection
                            gr.Markdown("#### 🎯 Positioning Mode")
                            positioning_mode_radio = gr.Radio(
                                ["Heading", "Paragraph", "Logo"], 
                                value="Paragraph", 
                                label="Select what to position when clicking image"
                            )
                            
                            # Heading Controls - UPDATED FOR CLICK POSITIONING
                            gr.Markdown("#### Heading")
                            social_preset_dd = gr.Dropdown( ["Custom"] + list(PRESETS.keys()), value="Bold & Readable", label="✨ Text Effect Preset" )
                            heading_text = gr.Textbox(label="Heading Text", placeholder="Your Catchy Title...")
                            with gr.Row():
                                heading_font_dd = gr.Dropdown(list(fonts_available.keys()), label="Heading Font", value=list(fonts_available.keys())[0])
                                heading_font_size = gr.Slider(20, 200, 60, label="Heading Font Size", step=5)
                            heading_color_picker = gr.ColorPicker(label="Heading Color", value="#000000", interactive=True)
                            
                            # NEW: Heading positioning controls
                            with gr.Row():
                                heading_x_num = gr.Number(label="Heading X", value=100, interactive=False)
                                heading_y_num = gr.Number(label="Heading Y", value=100, interactive=False)
                            
                            add_heading_btn = gr.Button("➕ Add Heading at Position", variant="primary")
                            
                            # Paragraph Controls - UPDATED FOR CLICK POSITIONING
                            gr.Markdown("#### Paragraph")
                            paragraph_text = gr.Textbox(label="Paragraph Text", placeholder="Add more details here...", lines=3)
                            with gr.Row():
                                paragraph_font_dd = gr.Dropdown(list(fonts_available.keys()), label="Paragraph Font", value=list(fonts_available.keys())[0])
                                paragraph_font_size = gr.Slider(15, 100, 30, label="Paragraph Font Size", step=5)
                            paragraph_color_picker = gr.ColorPicker(label="Paragraph Color", value="#000000", interactive=True)
                            text_alignment_radio = gr.Radio(["Left", "Center", "Right"], label="Paragraph Alignment", value="Left")
                            
                            # NEW: Paragraph positioning controls
                            with gr.Row():
                                paragraph_x_num = gr.Number(label="Paragraph X", value=100, interactive=False)
                                paragraph_y_num = gr.Number(label="Paragraph Y", value=100, interactive=False)
                            
                            add_paragraph_btn = gr.Button("➕ Add Paragraph at Position", variant="primary")
                            
                            # Logo Controls - UPDATED FOR MULTIPLE LOGOS
                            gr.Markdown("#### Logo (Optional)")
                            logo_upload_img = gr.Image(label="Upload Logo (PNG Recommended)", type="pil", height=100)
                            logo_size_radio = gr.Radio(["Small (50px)", "Medium (100px)", "Large (150px)"], label="Logo Size", value="Medium (100px)")
                            
                            # NEW: Logo positioning controls
                            with gr.Row():
                                logo_x_num = gr.Number(label="Logo X", value=50, interactive=False)
                                logo_y_num = gr.Number(label="Logo Y", value=50, interactive=False)
                            
                            add_logo_btn = gr.Button("➕ Add Logo at Position", variant="primary")
                            
                        with gr.Column(scale=2):
                            gr.Markdown("### Preview (Click to Position Elements)")
                            post_preview_img = gr.Image(label="Post Preview")
                            post_status_text = gr.Textbox(label="Status", interactive=False)
                            social_layers_list = gr.Textbox(label="📝 Elements", lines=5, value="No elements added yet")
                            with gr.Row():
                                social_remove_last_btn = gr.Button("🔙 Remove Last Element", variant="secondary")
                                social_clear_all_btn = gr.Button("🗑️ Clear All Elements", variant="stop")
                            
                            gr.Markdown("---")
                            gr.Markdown("### 💾 Download Your Post")
                            with gr.Row():
                                social_format_choice = gr.Dropdown(["JPEG (Smaller File)", "PNG (Higher Quality)"], value="JPEG (Smaller File)", label="Choose Format")
                                social_prepare_download_btn = gr.Button("Prepare Download", variant="secondary")
                            with gr.Row():
                                social_download_file = gr.File(label="Download Link", interactive=False)
                                social_download_status = gr.Textbox(label="Status", interactive=False)
                    
                    # --- Event Handlers for Social Post Tab ---
                    
                    # Update positioning mode
                    def update_positioning_mode(mode):
                        return mode.lower()
                    positioning_mode_radio.change(
                        update_positioning_mode,
                        [positioning_mode_radio],
                        [current_positioning_mode]
                    )
                    
                    # Toggle visibility of background controls
                    def toggle_background_type(bg_type):
                        if bg_type == "Solid Color":
                            return gr.update(visible=True), gr.update(visible=False)
                        else:
                            return gr.update(visible=False), gr.update(visible=True)
                    bg_type_radio.change(toggle_background_type, [bg_type_radio], [solid_color_controls, template_controls])

                    # Store selected template path - FIXED VERSION
                    def select_template(evt: gr.SelectData):
                        print(f"Template selected: {evt.value}, type: {type(evt.value)}")
                        if isinstance(evt.value, dict):
                            selected_path = evt.value.get('name') or evt.value.get('data') or list(evt.value.values())[0]
                            print(f"Extracted path from dict: {selected_path}")
                            return selected_path
                        else:
                            return evt.value
                    template_gallery.select(select_template, None, [template_selection_state])

                    # Create base from template - FIXED VERSION
                    def create_base_canvas_template(size_key, template_path):
                        print(f"Creating canvas from template: {template_path}")
                        if not template_path:
                            return None, None, [], 1, [], "No template selected.", "No elements added yet"
                        
                        if isinstance(template_path, dict):
                            template_path = template_path.get('name') or template_path.get('data') or list(template_path.values())[0]
                            print(f"Converted dict to path: {template_path}")
                        
                        try:
                            width, height = post_sizes[size_key]
                            if not isinstance(template_path, str) or not os.path.exists(template_path):
                                print(f"Invalid template path: {template_path}")
                                img = Image.new('RGB', (width, height), "#FFFFFF")
                                return img, img, [], 1, [], "Template not found. Using white background.", "No elements added yet"
                            
                            img = Image.open(template_path).convert('RGBA')
                            img = img.resize((width, height), Image.Resampling.LANCZOS)
                            print(f"Successfully loaded template: {template_path}")
                            
                            base_img = Image.new("RGB", img.size, (255, 255, 255))
                            base_img.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                            
                            return base_img, base_img, [], 1, [], "Template set. Add elements.", "No elements added yet"
                            
                        except Exception as e:
                            print(f"Error loading template '{template_path}': {e}")
                            width, height = post_sizes[size_key]
                            img = Image.new('RGB', (width, height), "#FFFFFF")
                            return img, img, [], 1, [], f"Error loading template. Using white background.", "No elements added yet"

                    template_selection_state.change(
                        create_base_canvas_template,
                        [post_size_dd, template_selection_state],
                        [social_post_base_image, post_preview_img, social_layers_state, social_next_layer_id, social_history, post_status_text, social_layers_list]
                    )

                    # 1. Create Base Canvas (from Color)
                    def create_base_canvas_color(size_key, bg_color):
                        try:
                            width, height = post_sizes[size_key]
                            if not isinstance(bg_color, str) or not bg_color.startswith('#'): 
                                bg_color = "#FFFFFF"
                            img = Image.new('RGB', (width, height), bg_color)
                            print(f"Created base canvas: {width}x{height}, {bg_color}")
                            return img, img, [], 1, [], "Canvas set. Add elements.", "No elements added yet"
                        except Exception as e:
                            print(f"Error creating canvas: {e}")
                            return None, None, [], 1, [], f"Error: {e}", "Error"
                    create_canvas_btn.click(
                        create_base_canvas_color,
                        [post_size_dd, bg_color_picker],
                        [social_post_base_image, post_preview_img, social_layers_state, social_next_layer_id, social_history, post_status_text, social_layers_list]
                    )
                    
                    # 2. Store uploaded logo
                    def store_logo(img):
                        print("Logo uploaded and stored in state.")
                        return img
                    logo_upload_img.upload(store_logo, [logo_upload_img], [logo_image_state])
                    
                    # 3. Set element positions based on current mode
                    def set_element_pos(evt: gr.SelectData, current_mode):
                        x, y = evt.index[0], evt.index[1]
                        status_msg = f"✅ {current_mode.capitalize()} position set to ({x}, {y})"
                        
                        if current_mode == "heading":
                            return x, y, gr.update(), gr.update(), gr.update(), gr.update(), status_msg
                        elif current_mode == "paragraph":
                            return gr.update(), gr.update(), x, y, gr.update(), gr.update(), status_msg
                        elif current_mode == "logo":
                            return gr.update(), gr.update(), gr.update(), gr.update(), x, y, status_msg
                        else:
                            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), "Please select a positioning mode first"
                    
                    post_preview_img.select(
                        set_element_pos,
                        [current_positioning_mode],
                        [heading_x_num, heading_y_num, paragraph_x_num, paragraph_y_num, logo_x_num, logo_y_num, post_status_text]
                    )
                    
                    # 4. Update controls from Social Preset
                    def update_social_controls_from_preset(preset_name):
                        if preset_name in PRESETS:
                            settings = PRESETS[preset_name]
                            return ( settings.get("text_color", "#000000"), settings.get("effect_type", "normal") )
                        return gr.update(), gr.update()
                    social_preset_dd.change(update_social_controls_from_preset, [social_preset_dd], [heading_color_picker, social_effect_type_state])
                    
                    # 5. Add Heading Layer - UPDATED FOR CLICK POSITIONING
                    def add_heading_element(current_layers, next_id, head_txt, font_key, font_size, txt_color, effect_type, preset_name, x, y):
                        if not head_txt.strip(): 
                            return current_layers, next_id, "Enter heading text"
                        props = {
                            'type': 'text', 
                            'text': head_txt, 
                            'font_key': font_key, 
                            'font_size': int(font_size),
                            'color': txt_color, 
                            'is_heading': True, 
                            'effect_type': effect_type,
                            'x': x,  # Use clicked position
                            'y': y   # Use clicked position
                        }
                        if preset_name in PRESETS: 
                            props['outline_color'] = PRESETS[preset_name].get('outline_color', '#000000')
                        else:
                            props['outline_color'] = '#000000'  # Default outline color
                        new_layer = SocialLayer(id=next_id, type='text', properties=props)
                        updated_layers = current_layers + [new_layer]
                        return updated_layers, next_id + 1, f"Heading added at position ({x}, {y})"
                    add_heading_btn.click(
                        add_heading_element,
                        [social_layers_state, social_next_layer_id, heading_text, heading_font_dd, heading_font_size, heading_color_picker, social_effect_type_state, social_preset_dd, heading_x_num, heading_y_num],
                        [social_layers_state, social_next_layer_id, post_status_text]
                    )
                    
                    # 6. Add Paragraph Layer - UPDATED FOR CLICK POSITIONING
                    def add_paragraph_element(current_layers, next_id, para_txt, font_key, font_size, txt_color, align, effect_type, preset_name, x, y):
                        if not para_txt.strip(): 
                            return current_layers, next_id, "Enter paragraph text"
                        props = {
                            'type': 'text', 
                            'text': para_txt, 
                            'font_key': font_key, 
                            'font_size': int(font_size),
                            'color': txt_color, 
                            'align': align, 
                            'is_heading': False, 
                            'effect_type': effect_type,
                            'x': x,  # Use clicked position
                            'y': y   # Use clicked position
                        }
                        if preset_name in PRESETS: 
                            props['outline_color'] = PRESETS[preset_name].get('outline_color', '#000000')
                        else:
                            props['outline_color'] = '#000000'  # Default outline color
                        new_layer = SocialLayer(id=next_id, type='text', properties=props)
                        updated_layers = current_layers + [new_layer]
                        return updated_layers, next_id + 1, f"Paragraph added at position ({x}, {y})"
                    add_paragraph_btn.click(
                        add_paragraph_element,
                        [social_layers_state, social_next_layer_id, paragraph_text, paragraph_font_dd, paragraph_font_size, paragraph_color_picker, text_alignment_radio, social_effect_type_state, social_preset_dd, paragraph_x_num, paragraph_y_num],
                        [social_layers_state, social_next_layer_id, post_status_text]
                    )
                    
                    # 7. Add Logo Layer - UPDATED FOR MULTIPLE LOGOS
                    def add_logo_element(current_layers, next_id, logo_obj, size_str, x, y):
                        if logo_obj is None: 
                            return current_layers, next_id, "Upload a logo first"
                        # REMOVED: Don't filter out existing logos - allow multiple logos
                        props = {'type': 'logo', 'logo_obj': logo_obj, 'size_str': size_str, 'x': x, 'y': y}
                        new_layer = SocialLayer(id=next_id, type='logo', properties=props)
                        updated_layers = current_layers + [new_layer]
                        return updated_layers, next_id + 1, f"Logo added at position ({x}, {y})"
                    add_logo_btn.click(
                        add_logo_element,
                        [social_layers_state, social_next_layer_id, logo_image_state, logo_size_radio, logo_x_num, logo_y_num],
                        [social_layers_state, social_next_layer_id, post_status_text]
                    )
                    
                    # 8. Update preview function (triggered by .change() below)
                    def update_preview_and_layer_list(base_img, layers, size_key, bg_color, template_path, bg_type):
                        print(f"update_preview_and_layer_list - base_img: {base_img is not None}, layers: {len(layers)}")
                        
                        if base_img is not None:
                            print("Using existing base image")
                            rendered_image = render_social_post(size_key, bg_color, template_path, bg_type, layers, base_img)
                            layer_text = format_social_layers(layers)
                            return rendered_image, layer_text
                        
                        try:
                            width, height = post_sizes[size_key]
                            if bg_type == "Template" and template_path:
                                print("Creating new base from template")
                                if isinstance(template_path, dict):
                                    template_path = template_path.get('name') or template_path.get('data') or list(template_path.values())[0]
                                
                                if isinstance(template_path, str) and os.path.exists(template_path):
                                    base_img = Image.open(template_path).convert('RGBA')
                                    base_img = base_img.resize((width, height), Image.Resampling.LANCZOS)
                                    base_img_rgb = Image.new("RGB", base_img.size, (255, 255, 255))
                                    base_img_rgb.paste(base_img, mask=base_img.split()[3] if base_img.mode == 'RGBA' else None)
                                    base_img = base_img_rgb
                                else:
                                    base_img = Image.new('RGB', (width, height), "#FFFFFF")
                            else:
                                if not isinstance(bg_color, str) or not bg_color.startswith('#'): 
                                    bg_color = "#FFFFFF"
                                base_img = Image.new('RGB', (width, height), bg_color)
                            
                            rendered_image = render_social_post(size_key, bg_color, template_path, bg_type, layers, base_img)
                            layer_text = format_social_layers(layers)
                            return rendered_image, layer_text
                            
                        except Exception as e:
                            print(f"Error creating base image in update: {e}")
                            error_img = Image.new('RGB', (300, 100), color='gray')
                            draw = ImageDraw.Draw(error_img)
                            draw.text((10,10), f"Error: {str(e)[:50]}", fill="white")
                            return error_img, format_social_layers(layers)
                    
                    # FIXED: Update preview when layers change
                    def update_on_layers_change(layers, base_img, size_key, bg_color, template_path, bg_type):
                        print(f"Layers changed: {len(layers)} layers")
                        return update_preview_and_layer_list(base_img, layers, size_key, bg_color, template_path, bg_type)
                    
                    social_layers_state.change(
                         update_on_layers_change,
                         [social_layers_state, social_post_base_image, post_size_dd, bg_color_picker, template_selection_state, bg_type_radio],
                         [post_preview_img, social_layers_list]
                    )
                    
                    # 9. Remove Last Social Layer
                    def remove_last_social_layer(layers):
                        if not layers: 
                            return layers, "No elements to remove"
                        return layers[:-1], "✅ Removed last element"
                    social_remove_last_btn.click(remove_last_social_layer, [social_layers_state], [social_layers_state, post_status_text])
                    
                    # 10. Clear All Social Layers
                    def clear_all_social_layers():
                        return [], "✅ Cleared all elements"
                    social_clear_all_btn.click(clear_all_social_layers, [], [social_layers_state, post_status_text])
                    
                    # 11. Download Social Post
                    social_prepare_download_btn.click(
                        save_image,
                        [post_preview_img, social_format_choice],
                        [social_download_file, social_download_status]
                    )
                # --- END SOCIAL POST TAB ---


                # TAB 5 - ADMIN (Now after Social Post Tab)
                with gr.Tab("🔐 Admin"):
                    gr.Markdown("## 🔐 Admin Dashboard")
                    gr.Markdown("*For administrators only*")
                    with gr.Row():
                        admin_password = gr.Textbox( label="Admin Password", type="password", placeholder="Enter admin password to access" )
                        admin_login_btn = gr.Button("🔓 Access Admin Dashboard", variant="primary", size="lg")
                    admin_message = gr.Markdown("")
                    with gr.Group(visible=False) as admin_panel:
                        gr.Markdown("### 👨‍💼 Administrator Control Panel")
                        with gr.Row():
                            refresh_btn = gr.Button("🔄 Refresh Stats", variant="primary")
                            export_btn = gr.Button("📥 Export Users CSV", variant="secondary")
                            admin_logout_btn = gr.Button("🚪 Logout Admin", variant="stop")
                        admin_stats = gr.Markdown("Loading stats...")
                        with gr.Row():
                            export_file = gr.File(label="Download CSV", visible=False)
                            export_message = gr.Markdown("")
                    
                    # Admin Handlers
                    def admin_login(password):
                        if not password: return ( gr.update(visible=False), "❌ Please enter password", gr.update(), gr.update(visible=False), "" )
                        if check_admin_password(password):
                            stats = get_admin_stats()
                            return ( gr.update(visible=True), "✅ Access granted!", stats, gr.update(value=""), "" )
                        return ( gr.update(visible=False), "❌ Invalid password", "Enter password to view stats", gr.update(), "" )
                    admin_login_btn.click( admin_login, [admin_password], [admin_panel, admin_message, admin_stats, admin_password, export_message] )
                    
                    def admin_logout():
                        return ( gr.update(visible=False), "👋 Logged out from admin", "Enter password to view stats", gr.update(visible=False), "" )
                    admin_logout_btn.click( admin_logout, None, [admin_panel, admin_message, admin_stats, export_file, export_message] )
                    
                    def refresh_stats():
                        return get_admin_stats(), "🔄 Stats refreshed!"
                    refresh_btn.click( refresh_stats, None, [admin_stats, export_message] )
                    
                    def export_data():
                        file_path, message = export_user_data()
                        return (gr.update(value=file_path, visible=True), message) if file_path else (gr.update(visible=False), message)
                    export_btn.click( export_data, None, [export_file, export_message] )

        # --- UPDATED FEATURES SECTION with SINHALA TRANSLATIONS ---
        with gr.Row(elem_id="features_section"):
             gr.Markdown("""
             ---
             ### ✨ Features (විශේෂාංග)
             - 🆓 මාසිකව නොමිලේ AI උත්පාදන 5ක් (5 FREE AI generations per month)
             - 📤 අසීමිත උඩුගත කිරීම් (නොමිලේ!) (Unlimited uploads FREE!)
             - ✍️ අසීමිත පෙළ ආවරණ (නොමිලේ!) (Unlimited text overlays FREE!)
             - 🎨 නියොන්, ක්‍රෝම්, ෆයර්, 3D සහ තවත්! (Advanced text effects: Neon, Chrome, Fire, 3D & more!)
             - 🔄 මාසිකව ස්වයංක්‍රීයව යළි පිහිටුවේ (Auto-resets monthly)
             """)

        # --- FOOTER SECTION ---
        gr.Markdown("---") # Add a separator line
        with gr.Row(elem_id="footer"):
            with gr.Column(scale=1, min_width=160):
                gr.Image(
                    value="logo.JPG",
                    show_label=False,
                    height=50,
                    container=False,
                    show_download_button=False
                )
            with gr.Column(scale=3):
                terms_url = "https://lankaainexus.com/terms-and-conditions"
                privacy_url = "https://lankaainexus.com/privacy-policy"
                about_url = "https://lankaainexus.com/about-us/"
                gr.Markdown(f"""
                <div style="text-align: right; font-size: 0.9em; color: grey; line-height: 1.6;">
                    © {datetime.now().year} Lanka AI Nexus (Powered by Doctor On Care Pvt Ltd). All rights reserved. <br>
                    <a href="{about_url}" target="_blank" style="color: grey; text-decoration: none;">About Us</a> |
                    <a href="{terms_url}" target="_blank" style="color: grey; text-decoration: none;">Terms & Conditions</a> |
                    <a href="{privacy_url}" target="_blank" style="color: grey; text-decoration: none;">Privacy Policy</a>
                </div>
                """)


        # EVENT HANDLERS (Login/Register/Logout/Generate/Upload)
        
        # Register
        def handle_register(email, pwd, pwd2):
            if pwd != pwd2:
                return None, "❌ Passwords don't match", gr.update(), gr.update(), gr.update(), gr.update()
            success, msg = register_user(email, pwd)
            return None, msg, gr.update(), gr.update(), gr.update(), gr.update()

        reg_btn.click(
            handle_register,
            [reg_email, reg_password, reg_password2],
            [user_state, reg_msg, auth_section, main_app, login_msg, stats_display]
        )

        # Login
        def handle_login(email, pwd):
            success, msg, user_info = login_user(email, pwd)
            if success:
                stats = get_user_stats(user_info['id'])
                return (
                    user_info,
                    f"**Status:** ✅ {email}",
                    stats,
                    gr.update(visible=False), # auth_section
                    gr.update(visible=True),  # main_app
                    msg                      # login_msg
                )
            return None, "**Status:** Not logged in", "", gr.update(visible=True), gr.update(visible=False), msg

        login_btn.click(
            handle_login,
            [login_email, login_password],
            [user_state, login_status, stats_display, auth_section, main_app, login_msg]
        )

        # Logout
        def handle_logout():
            return (
                None,
                "**Status:** Logged out",
                "",                       # stats_display placeholder
                gr.update(visible=True),  # auth_section
                gr.update(visible=False), # main_app
                "👋 Logged out"            # login_msg placeholder
            )

        logout_btn.click(
            handle_logout,
            None,
            [user_state, login_status, stats_display, auth_section, main_app, login_msg]
        )

        # Upload (Tab 1)
        upload_btn.click(
            process_uploaded_image,
            [upload_img],
            [img_display, img_status]
        )

        # Generate (Tab 1)
        def gen_and_update_stats(prompt, size, user_info):
            img, msg = generate_image_with_auth(prompt, size, user_info)
            if user_info:
                stats = get_user_stats(user_info['id'])
                return img, msg, stats
            return img, msg, ""

        gen_btn.click(
            gen_and_update_stats,
            [prompt, size, user_state],
            [img_display, img_status, stats_display]
        )

    return demo # Return demo should be the last line in create_interface

# ============================================
# LAUNCH
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Advanced Text Creator Pro - With Effects Studio")
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
    # Updated port to 8001
    demo.launch(server_name="0.0.0.0", server_port=8000)