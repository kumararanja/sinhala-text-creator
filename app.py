"""
Sinhala Text Creator - COMPLETE VERSION WITH FIXED SOCIAL MEDIA TAB
====================================================================
Full working version with background color selector and outline text color for social media
"""

import gradio as gr
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in Hugging Face Secrets!")
        print("Fix: Go to Settings → Variables and secrets → New secret")
        print("Name: DATABASE_URL")
        print("Value: Your Supabase connection string")
        return None

    # Try to connect with better error messages
    try:
        # If the URL starts with postgres:// change it to postgresql://
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

        # Try Method 1: Direct connection
        conn = psycopg2.connect(DATABASE_URL)
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

def increment_user_generation(user_id: int):
    """Increment generation count for user"""
    try:
        conn = get_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET monthly_generations = monthly_generations + 1,
                total_generations = total_generations + 1
            WHERE id = %s
        ''', (user_id,))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating generation count: {e}")

def get_user_stats(user_id: int) -> str:
    """Get formatted user statistics"""
    try:
        conn = get_db_connection()
        if not conn:
            return "📊 Stats unavailable"
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT plan, monthly_generations, total_generations
            FROM users WHERE id = %s
        ''', (user_id,))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            remaining = get_remaining_generations(user['plan'], user['monthly_generations'])
            return f"""
            **Plan:** {user['plan'].upper()}  
            **This Month:** {user['monthly_generations']} used  
            **Remaining:** {remaining}  
            **Total Created:** {user['total_generations']}
            """
        return "📊 Stats unavailable"
    except Exception as e:
        return f"Error: {str(e)}"

# ============================================
# IMAGE GENERATION & PROCESSING
# ============================================

# Get Replicate API token
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

def generate_image_with_replicate(prompt: str, size: str = "1024x1024") -> Optional[Image.Image]:
    """Generate image using Replicate API (Flux model)"""
    if not REPLICATE_API_TOKEN:
        print("❌ REPLICATE_API_TOKEN not configured")
        return None
    
    try:
        # Use Flux Schnell for fast generation
        response = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {REPLICATE_API_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "version": "f2ab8a5bfe79f02f0dda1bf715a2e9bc007c0e51140c8bfa51b0e0f3511de88e",
                "input": {
                    "prompt": prompt,
                    "width": int(size.split('x')[0]),
                    "height": int(size.split('x')[1]),
                    "num_inference_steps": 4,
                    "guidance_scale": 0
                }
            }
        )
        
        if response.status_code != 201:
            print(f"Error: {response.status_code} - {response.text}")
            return None
        
        prediction = response.json()
        prediction_id = prediction['id']
        
        # Poll for result
        while True:
            response = requests.get(
                f"https://api.replicate.com/v1/predictions/{prediction_id}",
                headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"}
            )
            
            prediction = response.json()
            status = prediction['status']
            
            if status == 'succeeded':
                image_url = prediction['output'][0] if isinstance(prediction['output'], list) else prediction['output']
                img_response = requests.get(image_url)
                return Image.open(io.BytesIO(img_response.content))
            elif status == 'failed':
                print(f"Generation failed: {prediction.get('error')}")
                return None
            
            import time
            time.sleep(1)
    
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

def generate_image_with_auth(prompt: str, size: str, user_info: Optional[dict]) -> Tuple[Optional[Image.Image], str]:
    """Generate image with authentication check"""
    if not user_info:
        return None, "❌ Please login first!"
    
    if user_info['remaining'] <= 0:
        upgrade_msg = """
        ❌ Monthly limit reached!
        
        **Upgrade your plan:**
        🌟 Starter: 25 images/month - $2.99
        ⭐ Popular: 60 images/month - $5.99
        💎 Premium: 200 images/month - $15.99
        
        Contact: admin@lankaainexus.com
        """
        return None, upgrade_msg
    
    # Generate the image
    img = generate_image_with_replicate(prompt, size)
    
    if img:
        # Increment usage
        increment_user_generation(user_info['id'])
        user_info['monthly_generations'] += 1
        user_info['remaining'] -= 1
        return img, f"✅ Image generated! ({user_info['remaining']} remaining this month)"
    
    return None, "❌ Generation failed. Please try again."

def process_uploaded_image(image):
    """Process uploaded image"""
    if image is None:
        return None, "❌ No image uploaded"
    return image, "✅ Image uploaded successfully!"

# ============================================
# TEXT OVERLAY FUNCTIONS WITH ADVANCED EFFECTS
# ============================================

def get_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load font with fallback"""
    try:
        return ImageFont.truetype(font_path, size)
    except:
        return ImageFont.load_default()

def parse_color(color_str: str) -> tuple:
    """Parse color string to RGB tuple"""
    if color_str.startswith('#'):
        color_str = color_str[1:]
        return tuple(int(color_str[i:i+2], 16) for i in (0, 2, 4))
    return (255, 255, 255)

def create_text_effect(
    text: str,
    font: ImageFont.FreeTypeFont,
    effect: str,
    text_color: tuple,
    outline_color: tuple,
    shadow_color: tuple,
    image_size: tuple
) -> Image.Image:
    """Create text with advanced effects"""
    
    # Create transparent image for text
    txt_img = Image.new('RGBA', image_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_img)
    
    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Center position
    x = (image_size[0] - text_width) // 2
    y = (image_size[1] - text_height) // 2
    
    # Apply effect based on type
    if effect == "neon":
        # Create neon glow effect
        for offset in range(15, 0, -1):
            opacity = int(255 * (1 - offset / 15) * 0.3)
            glow_color = (*text_color, opacity)
            draw.text((x, y), text, font=font, fill=glow_color, 
                     stroke_width=offset, stroke_fill=glow_color)
        # Main text
        draw.text((x, y), text, font=font, fill=(*text_color, 255))
        
    elif effect == "shadow":
        # Shadow
        shadow_offset = 5
        draw.text((x + shadow_offset, y + shadow_offset), text, 
                 font=font, fill=(*shadow_color, 128))
        # Main text
        draw.text((x, y), text, font=font, fill=(*text_color, 255),
                 stroke_width=2, stroke_fill=outline_color)
        
    elif effect == "3d":
        # Create 3D effect with multiple layers
        for i in range(10, 0, -1):
            offset = i * 2
            draw.text((x + offset, y + offset), text, font=font,
                     fill=(100, 100, 100, 255 - i * 20))
        # Main text
        draw.text((x, y), text, font=font, fill=(*text_color, 255),
                 stroke_width=3, stroke_fill=outline_color)
        
    elif effect == "gradient":
        # Create gradient effect (simple version)
        for i in range(text_height):
            ratio = i / text_height
            grad_color = tuple(int(text_color[j] * (1 - ratio) + 
                                  outline_color[j] * ratio) for j in range(3))
            # Draw line by line
            line_img = Image.new('RGBA', image_size, (0, 0, 0, 0))
            line_draw = ImageDraw.Draw(line_img)
            line_draw.text((x, y), text, font=font, fill=(*grad_color, 255))
            # Crop to current line
            txt_img.paste(line_img, (0, i), line_img)
            
    elif effect == "chrome":
        # Chrome/metallic effect
        # Base layer
        draw.text((x, y), text, font=font, fill=(200, 200, 200, 255),
                 stroke_width=3, stroke_fill=(100, 100, 100))
        # Highlight
        draw.text((x - 2, y - 2), text, font=font, fill=(255, 255, 255, 100))
        
    elif effect == "fire":
        # Fire effect with orange-red gradient
        for i in range(20, 0, -1):
            offset = i
            opacity = int(255 * (1 - i / 20))
            fire_color = (255, int(200 - i * 8), 0, opacity)
            draw.text((x, y - offset), text, font=font, fill=fire_color,
                     stroke_width=max(1, i // 4), stroke_fill=fire_color)
        # Main text
        draw.text((x, y), text, font=font, fill=(255, 255, 0, 255))
        
    else:  # normal
        draw.text((x, y), text, font=font, fill=(*text_color, 255),
                 stroke_width=2, stroke_fill=outline_color)
    
    return txt_img

def add_text_overlay(
    image: Optional[Image.Image],
    text: str,
    font_size: int,
    text_color: str,
    outline_color: str,
    position: str,
    transparency: float,
    effect: str,
    shadow_color: str
) -> Tuple[Optional[Image.Image], str]:
    """Add text overlay with effects to image"""
    if not text:
        return None, "❌ Please enter text"
    
    if image is None:
        return None, "❌ Please upload or generate an image first"
    
    try:
        # Convert to RGBA
        img = image.convert('RGBA')
        
        # Parse colors
        text_rgb = parse_color(text_color)
        outline_rgb = parse_color(outline_color)
        shadow_rgb = parse_color(shadow_color)
        
        # Load font
        font = get_font("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", font_size)
        
        # Create text effect
        txt_layer = create_text_effect(
            text, font, effect, text_rgb, outline_rgb, shadow_rgb, img.size
        )
        
        # Apply transparency
        if transparency < 1.0:
            # Adjust alpha channel
            txt_array = np.array(txt_layer)
            txt_array[:, :, 3] = (txt_array[:, :, 3] * transparency).astype(np.uint8)
            txt_layer = Image.fromarray(txt_array, 'RGBA')
        
        # Adjust position if not centered
        if position != "center":
            # Create new layer with positioned text
            positioned_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            
            # Calculate position
            bbox = ImageDraw.Draw(txt_layer).textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            if position == "top":
                paste_pos = ((img.width - text_width) // 2, 50)
            elif position == "bottom":
                paste_pos = ((img.width - text_width) // 2, img.height - text_height - 50)
            elif position == "left":
                paste_pos = (50, (img.height - text_height) // 2)
            elif position == "right":
                paste_pos = (img.width - text_width - 50, (img.height - text_height) // 2)
            else:
                paste_pos = (0, 0)
            
            positioned_layer.paste(txt_layer, paste_pos, txt_layer)
            txt_layer = positioned_layer
        
        # Composite the text layer onto the image
        result = Image.alpha_composite(img, txt_layer)
        
        return result, f"✅ {effect.capitalize()} text effect applied!"
        
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

def create_social_media_post(
    template: str,
    text: str,
    font_size: int,
    text_color: str,
    bg_color: str,
    outline_color: str,
    effect: str
) -> Tuple[Optional[Image.Image], str]:
    """Create social media post with templates"""
    if not text:
        return None, "❌ Please enter text"
    
    try:
        # Social media dimensions
        dimensions = {
            "instagram_post": (1080, 1080),
            "instagram_story": (1080, 1920),
            "facebook_post": (1200, 630),
            "twitter_post": (1200, 675),
            "linkedin_post": (1200, 627),
            "youtube_thumbnail": (1280, 720)
        }
        
        size = dimensions.get(template, (1080, 1080))
        
        # Parse colors
        bg_rgb = parse_color(bg_color)
        text_rgb = parse_color(text_color)
        outline_rgb = parse_color(outline_color)
        
        # Create background
        img = Image.new('RGBA', size, (*bg_rgb, 255))
        
        # Create text effect
        font = get_font("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", font_size)
        txt_layer = create_text_effect(
            text, font, effect, text_rgb, outline_rgb, (0, 0, 0), size
        )
        
        # Composite text onto background
        result = Image.alpha_composite(img, txt_layer)
        
        template_name = template.replace('_', ' ').title()
        return result, f"✅ {template_name} created with {effect} effect!"
        
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

# ============================================
# ADMIN FUNCTIONS
# ============================================

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin2024")

def check_admin_password(password: str) -> bool:
    """Check if admin password is correct"""
    return password == ADMIN_PASSWORD

def get_admin_stats() -> str:
    """Get admin statistics"""
    try:
        conn = get_db_connection()
        if not conn:
            return "❌ Database not available"
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get user stats
        cursor.execute('''
            SELECT 
                COUNT(*) as total_users,
                COUNT(CASE WHEN plan = 'free' THEN 1 END) as free_users,
                COUNT(CASE WHEN plan = 'starter' THEN 1 END) as starter_users,
                COUNT(CASE WHEN plan = 'popular' THEN 1 END) as popular_users,
                COUNT(CASE WHEN plan = 'premium' THEN 1 END) as premium_users,
                SUM(total_generations) as total_generations
            FROM users
        ''')
        
        stats = cursor.fetchone()
        conn.close()
        
        return f"""
        ## 📊 System Statistics
        
        **Total Users:** {stats['total_users']}
        - Free: {stats['free_users']}
        - Starter: {stats['starter_users']}
        - Popular: {stats['popular_users']}
        - Premium: {stats['premium_users']}
        
        **Total Generations:** {stats['total_generations'] or 0}
        
        **Revenue Potential:**
        - Starter: ${stats['starter_users'] * 2.99:.2f}/month
        - Popular: ${stats['popular_users'] * 5.99:.2f}/month
        - Premium: ${stats['premium_users'] * 15.99:.2f}/month
        - **Total:** ${(stats['starter_users'] * 2.99 + stats['popular_users'] * 5.99 + stats['premium_users'] * 15.99):.2f}/month
        """
        
    except Exception as e:
        return f"❌ Error: {str(e)}"

def export_user_data():
    """Export user data to CSV"""
    try:
        conn = get_db_connection()
        if not conn:
            return None, "❌ Database not available"
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT email, plan, monthly_generations, total_generations, 
                   created_at, last_reset_date, is_active
            FROM users
            ORDER BY created_at DESC
        ''')
        
        users = cursor.fetchall()
        conn.close()
        
        # Create CSV
        import csv
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
        
        with open(temp_file.name, 'w', newline='') as f:
            if users:
                writer = csv.DictWriter(f, fieldnames=users[0].keys())
                writer.writeheader()
                writer.writerows(users)
        
        return temp_file.name, f"✅ Exported {len(users)} users"
        
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

# ============================================
# GRADIO INTERFACE
# ============================================

def create_interface():
    with gr.Blocks(title="Advanced Text Creator Pro", theme=gr.themes.Soft()) as demo:
        # State management
        user_state = gr.State(None)
        
        # Custom CSS
        demo.css = """
        /* Modern gradient header */
        #header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        #header h1 {
            color: white !important;
            text-align: center;
            font-size: 2.5rem;
            margin: 0 !important;
        }
        
        #header p {
            color: rgba(255,255,255,0.9) !important;
            text-align: center;
            font-size: 1.1rem;
        }
        
        /* Card style for sections */
        .card-style {
            background: white;
            padding: 1.5rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            margin-bottom: 1rem;
        }
        
        /* Effect buttons */
        .effect-btn {
            background: linear-gradient(45deg, #2196F3, #21CBF3);
            color: white !important;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: bold;
            transition: all 0.3s;
        }
        
        .effect-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(33, 150, 243, 0.4);
        }
        
        /* Premium badge */
        .premium-badge {
            background: linear-gradient(45deg, #FFD700, #FFA500);
            color: #333;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            display: inline-block;
        }
        """
        
        # HEADER SECTION
        with gr.Row(elem_id="header"):
            gr.Markdown("""
            # 🎨 Advanced Sinhala Text Creator Pro
            ### Create stunning images with professional text effects | සිංහල ටෙක්ස්ට් එෆෙක්ට්ස් සමඟ
            """)
        
        # LOGIN STATUS
        with gr.Row():
            with gr.Column(scale=3):
                login_status = gr.Markdown("**Status:** Not logged in")
            with gr.Column(scale=1):
                logout_btn = gr.Button("🚪 Logout", variant="secondary", size="sm")
        
        # AUTHENTICATION SECTION
        with gr.Group(visible=True) as auth_section:
            with gr.Tabs():
                with gr.Tab("🔐 Login"):
                    login_email = gr.Textbox(label="Email", placeholder="your@email.com")
                    login_password = gr.Textbox(label="Password", type="password", placeholder="Enter password")
                    login_btn = gr.Button("Login", variant="primary")
                    login_msg = gr.Markdown("")
                
                with gr.Tab("📝 Register"):
                    gr.Markdown("### Create Free Account")
                    reg_email = gr.Textbox(label="Email", placeholder="your@email.com")
                    reg_password = gr.Textbox(label="Password", type="password", placeholder="Min 6 characters")
                    reg_password2 = gr.Textbox(label="Confirm Password", type="password")
                    reg_btn = gr.Button("Create Account", variant="primary")
                    reg_msg = gr.Markdown("")
        
        # MAIN APPLICATION
        with gr.Group(visible=False) as main_app:
            # User stats
            stats_display = gr.Markdown("", elem_classes=["card-style"])
            
            # Main tabs
            with gr.Tabs():
                # TAB 1: AI IMAGE GENERATION
                with gr.Tab("🎨 AI Image Generation"):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Generate AI Images")
                            prompt = gr.Textbox(
                                label="Describe your image (English works best)",
                                placeholder="A beautiful sunset over mountains",
                                lines=3
                            )
                            size = gr.Radio(
                                label="Image Size",
                                choices=["1024x1024", "1024x768", "768x1024"],
                                value="1024x1024"
                            )
                            gen_btn = gr.Button("🎨 Generate Image", variant="primary", size="lg")
                        
                        with gr.Column():
                            img_display = gr.Image(label="Generated/Uploaded Image", type="pil")
                            img_status = gr.Markdown("")
                
                # TAB 2: UPLOAD IMAGE
                with gr.Tab("📤 Upload Image"):
                    gr.Markdown("### Upload Your Own Image")
                    upload_img = gr.Image(label="Upload Image", type="pil")
                    upload_btn = gr.Button("✅ Use This Image", variant="primary")
                
                # TAB 3: TEXT OVERLAY WITH EFFECTS
                with gr.Tab("✨ Text Effects Studio"):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Advanced Text Effects")
                            text_input = gr.Textbox(
                                label="Enter Text (සිංහල/English)",
                                placeholder="ආයුබෝවන්",
                                lines=2
                            )
                            
                            with gr.Row():
                                effect_type = gr.Dropdown(
                                    label="Text Effect",
                                    choices=["normal", "neon", "shadow", "3d", "gradient", "chrome", "fire"],
                                    value="normal"
                                )
                                font_size = gr.Slider(
                                    label="Font Size",
                                    minimum=20,
                                    maximum=200,
                                    value=60,
                                    step=5
                                )
                            
                            with gr.Row():
                                text_color_picker = gr.ColorPicker(
                                    label="Text Color",
                                    value="#FFFFFF"
                                )
                                outline_color_picker = gr.ColorPicker(
                                    label="Outline Color",
                                    value="#000000"
                                )
                            
                            with gr.Row():
                                shadow_color_picker = gr.ColorPicker(
                                    label="Shadow/Glow Color",
                                    value="#808080"
                                )
                                transparency = gr.Slider(
                                    label="Transparency",
                                    minimum=0.1,
                                    maximum=1.0,
                                    value=1.0,
                                    step=0.1
                                )
                            
                            position = gr.Radio(
                                label="Text Position",
                                choices=["center", "top", "bottom", "left", "right"],
                                value="center"
                            )
                            
                            apply_text_btn = gr.Button("✨ Apply Text Effect", variant="primary", size="lg")
                        
                        with gr.Column():
                            text_output = gr.Image(label="Result with Text Effect", type="pil")
                            text_status = gr.Markdown("")
                
                # TAB 4: SOCIAL MEDIA TEMPLATES - FIXED WITH BACKGROUND COLOR
                with gr.Tab("📱 Social Media"):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Create Social Media Posts")
                            
                            social_template = gr.Dropdown(
                                label="Choose Template",
                                choices=[
                                    "instagram_post",
                                    "instagram_story",
                                    "facebook_post",
                                    "twitter_post",
                                    "linkedin_post",
                                    "youtube_thumbnail"
                                ],
                                value="instagram_post"
                            )
                            
                            social_text = gr.Textbox(
                                label="Post Text",
                                placeholder="Enter your message",
                                lines=3
                            )
                            
                            social_effect = gr.Dropdown(
                                label="Text Effect",
                                choices=["normal", "neon", "shadow", "3d", "gradient", "chrome", "fire"],
                                value="shadow"
                            )
                            
                            social_font_size = gr.Slider(
                                label="Font Size",
                                minimum=20,
                                maximum=150,
                                value=48,
                                step=5
                            )
                            
                            # Color pickers for social media - NOW INCLUDING BACKGROUND COLOR
                            with gr.Row():
                                social_bg_color = gr.ColorPicker(
                                    label="Background Color",
                                    value="#1E88E5"
                                )
                                social_text_color = gr.ColorPicker(
                                    label="Text Color",
                                    value="#FFFFFF"
                                )
                            
                            with gr.Row():
                                social_outline_color = gr.ColorPicker(
                                    label="Outline Color",
                                    value="#000000"
                                )
                                # Optional: Add shadow color for social media
                                social_shadow_color = gr.ColorPicker(
                                    label="Shadow/Glow Color",
                                    value="#404040"
                                )
                            
                            create_social_btn = gr.Button("📱 Create Social Post", variant="primary", size="lg")
                        
                        with gr.Column():
                            social_output = gr.Image(label="Social Media Post", type="pil")
                            social_status = gr.Markdown("")
                
                # TAB 5: ADMIN DASHBOARD
                with gr.Tab("👤 Admin Dashboard"):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Admin Access")
                            admin_password = gr.Textbox(
                                label="Admin Password",
                                type="password",
                                placeholder="Enter admin password"
                            )
                            admin_login_btn = gr.Button("🔓 Access Dashboard", variant="primary")
                            admin_message = gr.Markdown("")
                        
                        with gr.Column():
                            admin_stats = gr.Markdown("Enter password to view stats")
                    
                    with gr.Group(visible=False) as admin_panel:
                        gr.Markdown("### 📊 Admin Controls")
                        with gr.Row():
                            refresh_btn = gr.Button("🔄 Refresh Stats", variant="secondary")
                            export_btn = gr.Button("📥 Export Users CSV", variant="secondary")
                            admin_logout_btn = gr.Button("🚪 Logout", variant="stop")
                        
                        with gr.Row():
                            export_file = gr.File(label="Download CSV", visible=False)
                            export_message = gr.Markdown("")
                    
                    def admin_login(password):
                        if not password:
                            return (
                                gr.update(visible=False),
                                "❌ Please enter password",
                                gr.update(),
                                gr.update(visible=False),
                                ""
                            )
                        if check_admin_password(password):
                            stats = get_admin_stats()
                            return (
                                gr.update(visible=True),
                                "✅ Access granted!",
                                stats,
                                gr.update(value=""),
                                ""
                            )
                        return (
                            gr.update(visible=False),
                            "❌ Invalid password",
                            "Enter password to view stats",
                            gr.update(),
                            ""
                        )
                    
                    admin_login_btn.click(
                        admin_login,
                        [admin_password],
                        [admin_panel, admin_message, admin_stats, admin_password, export_message]
                    )
                    
                    def admin_logout():
                        return (
                            gr.update(visible=False),
                            "👋 Logged out from admin",
                            "Enter password to view stats",
                            gr.update(visible=False),
                            ""
                        )
                    
                    admin_logout_btn.click(
                        admin_logout,
                        None,
                        [admin_panel, admin_message, admin_stats, export_file, export_message]
                    )
                    
                    def refresh_stats():
                        return get_admin_stats(), "🔄 Stats refreshed!"
                    
                    refresh_btn.click(
                        refresh_stats,
                        None,
                        [admin_stats, export_message]
                    )
                    
                    def export_data():
                        file_path, message = export_user_data()
                        return (gr.update(value=file_path, visible=True), message) if file_path else (gr.update(visible=False), message)
                    
                    export_btn.click(
                        export_data,
                        None,
                        [export_file, export_message]
                    )

        # FEATURES SECTION
        with gr.Row(elem_id="features_section"):
            gr.Markdown("""
            ---
            ### ✨ Features (විශේෂාංග)
            - 🆓 මාසිකව නොමිලේ AI උත්පාදන 5ක් (5 FREE AI generations per month)
            - 📤 අසීමිත උඩුගත කිරීම් (නොමිලේ!) (Unlimited uploads FREE!)
            - ✍️ අසීමිත පෙළ ආවරණ (නොමිලේ!) (Unlimited text overlays FREE!)
            - 🎨 නියොන්, ක්‍රෝම්, ෆයර්, 3D සහ තවත්! (Advanced text effects: Neon, Chrome, Fire, 3D & more!)
            - 📱 Social Media Templates with customizable backgrounds
            - 🔄 මාසිකව ස්වයංක්‍රීයව යළි පිහිටුවේ (Auto-resets monthly)
            """)

        # FOOTER SECTION
        gr.Markdown("---")
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

        # EVENT HANDLERS
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

        def handle_login(email, pwd):
            success, msg, user_info = login_user(email, pwd)
            if success:
                stats = get_user_stats(user_info['id'])
                return (
                    user_info,
                    f"**Status:** ✅ {email}",
                    stats,
                    gr.update(visible=False),
                    gr.update(visible=True),
                    msg
                )
            return None, "**Status:** Not logged in", "", gr.update(visible=True), gr.update(visible=False), msg

        login_btn.click(
            handle_login,
            [login_email, login_password],
            [user_state, login_status, stats_display, auth_section, main_app, login_msg]
        )

        def handle_logout():
            return (
                None,
                "**Status:** Logged out",
                "",
                gr.update(visible=True),
                gr.update(visible=False),
                "👋 Logged out"
            )

        logout_btn.click(
            handle_logout,
            None,
            [user_state, login_status, stats_display, auth_section, main_app, login_msg]
        )

        upload_btn.click(
            process_uploaded_image,
            [upload_img],
            [img_display, img_status]
        )

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

        apply_text_btn.click(
            add_text_overlay,
            [
                img_display, text_input, font_size, text_color_picker,
                outline_color_picker, position, transparency, effect_type, shadow_color_picker
            ],
            [text_output, text_status]
        )

        # Updated social media handler with background color
        def create_social_with_bg(template, text, font_size, text_color, bg_color, outline_color, effect):
            """Handler for social media creation with background color"""
            return create_social_media_post(
                template, text, font_size, text_color, bg_color, outline_color, effect
            )

        create_social_btn.click(
            create_social_with_bg,
            [
                social_template, social_text, social_font_size,
                social_text_color, social_bg_color, social_outline_color, social_effect
            ],
            [social_output, social_status]
        )

    return demo

# ============================================
# LAUNCH
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Advanced Text Creator Pro - With Fixed Social Media Tab")
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
    demo.launch(server_name="0.0.0.0", server_port=8000)