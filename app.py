"""
Sinhala Text Creator - ROBUST FONT & COLOR HANDLING
===================================================
This version includes a fallback font to prevent startup crashes
and uses the correct state-based color logic.
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
import numpy as np
import glob

# ============================================
# DATABASE SETUP (Keep your existing database code)
# ============================================
# [Your existing database functions here...]

# ============================================
# FONTS & CONFIG (MODIFIED FOR ROBUSTNESS)
# ============================================
FONT_PATHS = {
    "Abhaya Regular (Sinhala)": "fonts/AbhayaLibre-Regular.ttf", 
    "Abhaya Bold (Sinhala)": "fonts/AbhayaLibre-Bold.ttf", 
    "Noto Sans (Sinhala)": "fonts/NotoSansSinhala_Condensed-Regular.ttf", 
    "Montserrat Bold": "fonts/Montserrat-Bold.ttf"
}
fonts_available = {}

# Try to load custom fonts
for name, path in FONT_PATHS.items():
    try:
        if os.path.exists(path):
            # Test if font file is valid
            ImageFont.truetype(path, 20) 
            fonts_available[name] = path
            print(f"Loaded font: {name}")
    except Exception as e:
        print(f"Could not load font {name}: {e}")

# **NEW FALLBACK**
if not fonts_available:
    print("WARNING: No custom fonts found in 'fonts/' folder.")
    try:
        # Try to load a very basic built-in font as a last resort
        ImageFont.load_default()
        fonts_available["Default (Fallback)"] = "DEFAULT"
        print("Using basic fallback font.")
    except Exception as e:
        print(f"CRITICAL: Could not load any fonts, not even default. {e}")
        # If this fails, the app truly cannot run.

# Load Templates
template_files = glob.glob("templates/*.jpg") + glob.glob("templates/*.png") + glob.glob("templates/*.jpeg")
if not template_files:
    print("WARNING: No templates found in 'templates/' folder.")

# ============================================
# SIMPLIFIED COLOR SYSTEM
# ============================================

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple"""
    if not hex_color or not isinstance(hex_color, str):
        return (0, 0, 0)
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        try:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        except:
            return (0, 0, 0)
    return (0, 0, 0)

@dataclass
class SocialLayer:
    id: int
    type: str
    properties: Dict[str, Any]
    visible: bool = True

# ============================================
# DIRECT COLOR RENDERING SYSTEM (MODIFIED FOR ROBUSTNESS)
# ============================================

post_sizes = {
    "Instagram Square (1:1)": (1080, 1080),
    "Instagram Story (9:16)": (1080, 1920),
    "Facebook Post (1.91:1)": (1200, 630),
    "Twitter Post (16:9)": (1600, 900)
}

def render_text_direct(draw, props, image=None):
    """DIRECT TEXT RENDERER - Handles default font"""
    try:
        # Get font
        font_key = props.get('font_key', list(fonts_available.keys())[0])
        font_path = fonts_available.get(font_key, list(fonts_available.values())[0])
        
        # Get font size
        font_size = props.get('font_size', 40)
        
        # **NEW FONT LOADING LOGIC**
        font_obj = None
        if font_path == "DEFAULT":
            try:
                # load_default() doesn't really support size, but we try
                font_obj = ImageFont.load_default(size=font_size)
            except TypeError:
                font_obj = ImageFont.load_default() # Fallback for older PIL
        else:
            try:
                font_obj = ImageFont.truetype(font_path, font_size)
            except Exception as e:
                print(f"Error loading font {font_path}, using default: {e}")
                font_obj = ImageFont.load_default()
        
        # Get text and color - DIRECT FROM PROPS
        text = props.get('text', 'Sample Text')
        color_hex = props.get('color', '#000000')
        
        print(f"🎨 RENDERING TEXT: '{text}' with color '{color_hex}'")
        
        # Convert color to RGB
        color_rgb = hex_to_rgb(color_hex)
        
        # Get positioning
        width, height = image.size if image else (1080, 1080)
        is_heading = props.get('is_heading', False)
        
        # Simple positioning
        if is_heading:
            x = width // 2
            y = int(height * 0.2)
            anchor = "ma"
        else:
            alignment = props.get('align', 'Left')
            if alignment == "Center":
                x = width // 2
                anchor = "ma"
            elif alignment == "Right":
                x = int(width * 0.9)
                anchor = "ra"
            else:
                x = int(width * 0.1)
                anchor = "la"
            y = int(height * 0.4)
        
        # Use custom position if provided
        if 'x' in props and 'y' in props:
            x = props['x']
            y = props['y']
            anchor = "la" # Custom XY implies left-anchor
        
        # Handle multi-line text
        if '\n' in text:
            lines = text.split('\n')
            # Get line height from font
            try:
                # This is a robust way to get line height
                bbox = draw.textbbox((0, 0), "Agy", font=font_obj)
                line_height = bbox[3] - bbox[1] + (font_size // 4) # Add 1/4th font size as spacing
            except:
                line_height = font_size + 10 # Fallback
                
            for i, line in enumerate(lines):
                current_y = y + (i * line_height)
                draw.text((x, current_y), line, fill=color_rgb, font=font_obj, anchor=anchor)
        else:
            draw.text((x, y), text, fill=color_rgb, font=font_obj, anchor=anchor)
            
    except Exception as e:
        print(f"Rendering error: {e}")

def render_social_post_direct(size_key, bg_color, template_path, bg_type, social_layers: List[SocialLayer], base_image=None):
    """DIRECT POST RENDERER"""
    try:
        width, height = post_sizes[size_key]
        
        # Create base image
        if base_image is not None:
            img = base_image.copy().convert('RGBA') if base_image.mode != 'RGBA' else base_image.copy()
        else:
            if bg_type == "Template" and template_path:
                try:
                    if isinstance(template_path, dict):
                        template_path = template_path.get('name') or template_path.get('data') or list(template_path.values())[0]
                    
                    if isinstance(template_path, str) and os.path.exists(template_path):
                        img = Image.open(template_path).convert('RGBA')
                        img = img.resize((width, height), Image.Resampling.LANCZOS)
                    else:
                        raise FileNotFoundError("Template path is invalid")
                except Exception as e:
                    print(f"Template load error: {e}")
                    img = Image.new('RGBA', (width, height), bg_color)
            else:
                if not isinstance(bg_color, str) or not bg_color.startswith('#'): 
                    bg_color = "#FFFFFF"
                img = Image.new('RGBA', (width, height), bg_color)
        
        draw = ImageDraw.Draw(img)

        # Render layers
        for layer in social_layers:
            if not layer.visible:
                continue
            props = layer.properties
            if layer.type == 'text':
                try:
                    render_text_direct(draw, props, img)
                except Exception as e:
                    print(f"Text layer error: {e}")
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
                    print(f"Logo layer error: {e}")

        # Convert to RGB for final output
        final_rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        final_rgb_img.paste(img, mask=img.split()[3])
        return final_rgb_img
    except Exception as e:
        print(f"Post render error: {e}")
        error_img = Image.new('RGB', (300, 100), color = 'grey')
        draw = ImageDraw.Draw(error_img)
        draw.text((10, 10), f"Render Error: {e}", fill='white')
        return error_img

# ============================================
# GRADIO INTERFACE (NO CHANGES NEEDED HERE)
# ============================================

def create_interface():
    """Create the main Gradio interface with fixed color handling"""
    with gr.Blocks(title="Sinhala Text Creator - Fixed Colors", theme=gr.themes.Soft()) as demo:

        user_state = gr.State(None)

        # Header
        gr.HTML("""
        <div style="text-align: center; padding: 20px; background: linear-gradient(120deg, #5f72bd 0%, #a4508b 100%); border-radius: 15px; margin-bottom: 20px;">
            <h1 style="color: white; margin: 0;">🌟 AkuruAI – අකුරුAI 🌟</h1>
            <p style="color: #e0e7ff; margin: 10px 0 0 0;">Powered by Lanka AI Nexus</p>
        </div>
        """)

        with gr.Row():
            login_status = gr.Markdown("**Status:** Not logged in")

        # Auth Section (keep your existing auth code)
        with gr.Group(visible=True) as auth_section:
            with gr.Row():
                with gr.Column():
                    gr.Markdown("## 🔐 Login or Register")
                    with gr.Tabs():
                        with gr.Tab("Login"):
                            login_email = gr.Textbox(label="Email", placeholder="your@email.com")
                            login_password = gr.Textbox(label="Password", type="password")
                            login_btn = gr.Button("🔑 Login", variant="primary")
                            login_msg = gr.Textbox(label="Message", interactive=False)
                        with gr.Tab("Register FREE"):
                            reg_email = gr.Textbox(label="Email", placeholder="your@email.com")
                            reg_password = gr.Textbox(label="Password (min 6 chars)", type="password")
                            reg_password2 = gr.Textbox(label="Confirm Password", type="password")
                            reg_btn = gr.Button("✨ Create FREE Account", variant="primary")
                            reg_msg = gr.Textbox(label="Message", interactive=False)

        # Main App
        with gr.Group(visible=False) as main_app:
            with gr.Accordion("📊 Your Dashboard", open=True):
                with gr.Row():
                    stats_display = gr.Markdown("Loading...")
                    logout_btn = gr.Button("🚪 Logout", size="sm")

            with gr.Tabs():
                # Tab 1 - Get Image (keep your existing code)
                with gr.Tab("1️⃣ Get Image"):
                    gr.Markdown("### Get Your Base Image")
                    with gr.Row():
                        with gr.Column():
                            upload_img = gr.Image(label="Upload", type="pil")
                            upload_btn = gr.Button("📤 Use Image", variant="primary")
                        with gr.Column():
                            prompt = gr.Textbox(label="Prompt", lines=2, placeholder="sunset over ocean...")
                            size = gr.Dropdown(list(post_sizes.keys()), value=list(post_sizes.keys())[0])
                            gen_btn = gr.Button("🎨 Generate", variant="secondary")
                        with gr.Column():
                            img_display = gr.Image(label="Your Image", type="pil")
                            img_status = gr.Textbox(label="Status")

                # FIXED SOCIAL POST CREATOR TAB
                with gr.Tab("🎨 Social Post Creator (Fixed Colors)"):
                    gr.Markdown("## 🎨 Social Media Post Creator with Fixed Color Handling")
                    
                    # States - SIMPLIFIED
                    social_post_base_image = gr.State(None)
                    social_layers_state = gr.State([])
                    social_next_layer_id = gr.State(1)
                    logo_image_state = gr.State(None)
                    template_selection_state = gr.State(None)
                    
                    # COLOR STATES - These will track the current colors
                    current_heading_color = gr.State("#FF0000")  # Start with RED
                    current_paragraph_color = gr.State("#0000FF")  # Start with BLUE
                    
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### 1. Setup Canvas")
                            post_size_dd = gr.Dropdown(list(post_sizes.keys()), label="Post Size", value="Instagram Square (1:1)")
                            
                            bg_type_radio = gr.Radio(["Solid Color", "Template"], label="Background Type", value="Solid Color")
                            
                            with gr.Column(visible=True) as solid_color_controls:
                                bg_color_picker = gr.ColorPicker(value="#FFFFFF", label="Background Color")
                                create_canvas_btn = gr.Button("🆕 Create Canvas", variant="secondary")

                            with gr.Column(visible=False) as template_controls:
                                template_gallery = gr.Gallery(value=template_files, label="Templates", columns=3, height=120, allow_preview=False, object_fit="contain")
                            
                            gr.Markdown("### 2. Add Text Elements")
                            
                            # HEADING SECTION
                            gr.Markdown("#### Heading Text")
                            heading_text = gr.Textbox(label="Heading", placeholder="Your main title...", value="Sample Heading")
                            with gr.Row():
                                heading_font_dd = gr.Dropdown(list(fonts_available.keys()), label="Font", value=list(fonts_available.keys())[0])
                                heading_font_size = gr.Slider(20, 200, 60, label="Size", step=5)
                            
                            # HEADING COLOR PICKER WITH LIVE UPDATE
                            gr.Markdown("**Heading Color**")
                            heading_color_picker = gr.ColorPicker(
                                value="#FF0000", 
                                label="Choose Color",
                                interactive=True
                            )
                            
                            # Display current heading color
                            heading_color_display = gr.HTML("""
                            <div style="padding: 10px; background: #f0f0f0; border-radius: 5px; margin: 10px 0;">
                                <strong>Current Heading Color:</strong> <span style="color: #FF0000;">#FF0000 (Red)</span>
                                <div style="width: 100%; height: 20px; background: #FF0000; margin-top: 5px; border: 1px solid #000;"></div>
                            </div>
                            """)
                            
                            add_heading_btn = gr.Button("➕ Add Heading", variant="primary")

                            # PARAGRAPH SECTION  
                            gr.Markdown("#### Paragraph Text")
                            paragraph_text = gr.Textbox(label="Paragraph", placeholder="Your description...", value="Sample paragraph text", lines=2)
                            with gr.Row():
                                paragraph_font_dd = gr.Dropdown(list(fonts_available.keys()), label="Font", value=list(fonts_available.keys())[0])
                                paragraph_font_size = gr.Slider(15, 100, 30, label="Size", step=5)
                            
                            text_alignment_radio = gr.Radio(["Left", "Center", "Right"], label="Alignment", value="Left")
                            
                            # PARAGRAPH COLOR PICKER WITH LIVE UPDATE
                            gr.Markdown("**Paragraph Color**")
                            paragraph_color_picker = gr.ColorPicker(
                                value="#0000FF", 
                                label="Choose Color",
                                interactive=True
                            )
                            
                            # Display current paragraph color
                            paragraph_color_display = gr.HTML("""
                            <div style="padding: 10px; background: #f0f0f0; border-radius: 5px; margin: 10px 0;">
                                <strong>Current Paragraph Color:</strong> <span style="color: #0000FF;">#0000FF (Blue)</span>
                                <div style="width: 100%; height: 20px; background: #0000FF; margin-top: 5px; border: 1px solid #000;"></div>
                            </div>
                            """)
                            
                            with gr.Row():
                                paragraph_x_num = gr.Number(label="X Position", value=100, visible=False)
                                paragraph_y_num = gr.Number(label="Y Position", value=100, visible=False)
                            
                            add_paragraph_btn = gr.Button("➕ Add Paragraph", variant="primary")

                            # LOGO SECTION
                            gr.Markdown("#### Logo")
                            logo_upload_img = gr.Image(label="Upload Logo", type="pil", height=100)
                            logo_size_radio = gr.Radio(["Small (50px)", "Medium (100px)", "Large (150px)"], label="Logo Size", value="Medium (100px)")
                            with gr.Row():
                                logo_x_num = gr.Number(label="Logo X", value=50)
                                logo_y_num = gr.Number(label="Logo Y", value=50)
                            add_logo_btn = gr.Button("➕ Add Logo")

                        with gr.Column(scale=2):
                            gr.Markdown("### 👀 Live Preview")
                            post_preview_img = gr.Image(label="Post Preview", interactive=True, height=500, tool="select")
                            post_status_text = gr.Textbox(label="Status", interactive=False)
                            
                            gr.Markdown("### 📋 Current Elements")
                            social_layers_list = gr.Textbox(label="Elements List", lines=4, value="No elements added yet")
                            
                            with gr.Row():
                                social_remove_last_btn = gr.Button("🗑️ Remove Last", variant="secondary")
                                social_clear_all_btn = gr.Button("💥 Clear All", variant="stop")
                            
                            gr.Markdown("---")
                            gr.Markdown("### 💾 Download")
                            with gr.Row():
                                social_format_choice = gr.Dropdown(["JPEG", "PNG"], value="JPEG", label="Format")
                                social_prepare_download_btn = gr.Button("📥 Prepare Download", variant="primary")
                            with gr.Row():
                                social_download_file = gr.File(label="Download Link", interactive=False)
                                social_download_status = gr.Textbox(label="Status", interactive=False)

                        # ============================================
                        # FIXED COLOR HANDLING EVENT SYSTEM
                        # ============================================

                        # Update color states when pickers change
                        def update_heading_color_state(color):
                            print(f"🔄 UPDATING HEADING COLOR STATE: {color}")
                            # Update the display
                            display_html = f"""
                            <div style="padding: 10px; background: #f0f0f0; border-radius: 5px; margin: 10px 0;">
                                <strong>Current Heading Color:</strong> <span style="color: {color};">{color}</span>
                                <div style="width: 100%; height: 20px; background: {color}; margin-top: 5px; border: 1px solid #000;"></div>
                            </div>
                            """
                            return color, display_html

                        def update_paragraph_color_state(color):
                            print(f"🔄 UPDATING PARAGRAPH COLOR STATE: {color}")
                            # Update the display
                            display_html = f"""
                            <div style="padding: 10px; background: #f0f0f0; border-radius: 5px; margin: 10px 0;">
                                <strong>Current Paragraph Color:</strong> <span style="color: {color};">{color}</span>
                                <div style="width: 100%; height: 20px; background: {color}; margin-top: 5px; border: 1px solid #000;"></div>
                            </div>
                            """
                            return color, display_html

                        # Connect color pickers to state updates
                        heading_color_picker.change(
                            update_heading_color_state,
                            [heading_color_picker],
                            [current_heading_color, heading_color_display]
                        )

                        paragraph_color_picker.change(
                            update_paragraph_color_state,
                            [paragraph_color_picker],
                            [current_paragraph_color, paragraph_color_display]
                        )

                        # Background type toggle
                        def toggle_background_type(bg_type):
                            if bg_type == "Solid Color":
                                return gr.update(visible=True), gr.update(visible=False)
                            else:
                                return gr.update(visible=False), gr.update(visible=True)
                        bg_type_radio.change(toggle_background_type, [bg_type_radio], [solid_color_controls, template_controls])

                        # Template selection
                        def select_template(evt: gr.SelectData):
                            # This handles the gallery's output format
                            template_path = evt.value
                            if isinstance(template_path, dict):
                                # Use 'name' if available, otherwise 'data'
                                template_path = template_path.get('name') or template_path.get('data') or list(template_path.values())[0]
                            
                            print(f"Template selected: {template_path}")
                            return template_path
                        template_gallery.select(select_template, None, [template_selection_state], queue=False)

                        # Create canvas from template
                        def create_base_canvas_template(size_key, template_path):
                            if not template_path:
                                return None, None, [], 1, "No template selected.", "No elements added yet"
                            
                            try:
                                width, height = post_sizes[size_key]
                                
                                if not (isinstance(template_path, str) and os.path.exists(template_path)):
                                    print(f"Invalid template path: {template_path}")
                                    raise FileNotFoundError("Template file not found or path is invalid")

                                img = Image.open(template_path).convert('RGBA')
                                img = img.resize((width, height), Image.Resampling.LANCZOS)
                                # Create a white background and paste the RGBA image onto it
                                base_img = Image.new("RGB", img.size, (255, 255, 255))
                                base_img.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
                                
                                return base_img, base_img, [], 1, "Template loaded!", "No elements added yet"
                            except Exception as e:
                                print(f"Error loading template: {e}")
                                width, height = post_sizes.get(size_key, (1080, 1080))
                                img = Image.new('RGB', (width, height), "#FFFFFF")
                                return img, img, [], 1, f"Error: {e}", "Error"

                        # This event is triggered when the *state* changes, which happens *after* gallery.select
                        template_selection_state.change(
                            create_base_canvas_template,
                            [post_size_dd, template_selection_state],
                            [social_post_base_image, post_preview_img, social_layers_state, social_next_layer_id, post_status_text, social_layers_list]
                        )

                        # Create canvas from color
                        def create_base_canvas_color(size_key, bg_color):
                            try:
                                width, height = post_sizes[size_key]
                                if not isinstance(bg_color, str) or not bg_color.startswith('#'): 
                                    bg_color = "#FFFFFF"
                                img = Image.new('RGB', (width, height), bg_color)
                                return img, img, [], 1, "Canvas created!", "No elements added yet"
                            except Exception as e:
                                return None, None, [], 1, f"Error: {e}", "Error"
                        create_canvas_btn.click(
                            create_base_canvas_color,
                            [post_size_dd, bg_color_picker],
                            [social_post_base_image, post_preview_img, social_layers_state, social_next_layer_id, post_status_text, social_layers_list]
                        )

                        # Store logo
                        def store_logo(img):
                            return img
                        logo_upload_img.upload(store_logo, [logo_upload_img], [logo_image_state])

                        # Position setting
                        def set_element_pos(evt: gr.SelectData):
                            return evt.index[0], evt.index[1], f"Position set: ({evt.index[0]}, {evt.index[1]})"
                        post_preview_img.select(set_element_pos, None, [paragraph_x_num, paragraph_y_num, post_status_text])

                        # ============================================
                        # FIXED ELEMENT ADDING FUNCTIONS
                        # ============================================

                        # ADD HEADING - Uses current_heading_color state
                        def add_heading_element_fixed(current_layers, next_id, head_txt, font_key, font_size, heading_color_state):
                            if not head_txt.strip(): 
                                return current_layers, next_id, "Enter heading text"
                            
                            print(f"🎯 ADDING HEADING: '{head_txt}' with ACTUAL COLOR: '{heading_color_state}'")
                            
                            props = {
                                'type': 'text', 
                                'text': head_txt, 
                                'font_key': font_key, 
                                'font_size': int(font_size),
                                'color': heading_color_state,  # Use the state value directly
                                'is_heading': True
                            }
                            
                            new_layer = SocialLayer(id=next_id, type='text', properties=props)
                            updated_layers = current_layers + [new_layer]
                            return updated_layers, next_id + 1, f"✅ Heading added with color {heading_color_state}"

                        add_heading_btn.click(
                            add_heading_element_fixed,
                            [social_layers_state, social_next_layer_id, heading_text, heading_font_dd, heading_font_size, current_heading_color],
                            [social_layers_state, social_next_layer_id, post_status_text]
                        )

                        # ADD PARAGRAPH - Uses current_paragraph_color state
                        def add_paragraph_element_fixed(current_layers, next_id, para_txt, font_key, font_size, paragraph_color_state, align, x, y):
                            if not para_txt.strip(): 
                                return current_layers, next_id, "Enter paragraph text"
                            
                            print(f"🎯 ADDING PARAGRAPH: '{para_txt}' with ACTUAL COLOR: '{paragraph_color_state}'")
                            
                            props = {
                                'type': 'text', 
                                'text': para_txt, 
                                'font_key': font_key, 
                                'font_size': int(font_size),
                                'color': paragraph_color_state,  # Use the state value directly
                                'align': align, 
                                'is_heading': False,
                                'x': int(x),  
                                'y': int(y)   
                            }
                            
                            new_layer = SocialLayer(id=next_id, type='text', properties=props)
                            updated_layers = current_layers + [new_layer]
                            return updated_layers, next_id + 1, f"✅ Paragraph added with color {paragraph_color_state}"

                        add_paragraph_btn.click(
                            add_paragraph_element_fixed,
                            [social_layers_state, social_next_layer_id, paragraph_text, paragraph_font_dd, paragraph_font_size, current_paragraph_color, text_alignment_radio, paragraph_x_num, paragraph_y_num],
                            [social_layers_state, social_next_layer_id, post_status_text]
                        )

                        # Add logo
                        def add_logo_element(current_layers, next_id, logo_obj, size_str, x, y):
                            if logo_obj is None: 
                                return current_layers, next_id, "Upload a logo first"
                            # This removes any existing logo, as we only allow one
                            current_layers = [lyr for lyr in current_layers if lyr.type != 'logo']
                            props = {'type': 'logo', 'logo_obj': logo_obj, 'size_str': size_str, 'x': x, 'y': y}
                            new_layer = SocialLayer(id=next_id, type='logo', properties=props)
                            updated_layers = current_layers + [new_layer]
                            return updated_layers, next_id + 1, "✅ Logo added"
                        add_logo_btn.click(
                            add_logo_element,
                            [social_layers_state, social_next_layer_id, logo_image_state, logo_size_radio, logo_x_num, logo_y_num],
                            [social_layers_state, social_next_layer_id, post_status_text]
                        )

                        # ============================================
                        # FIXED PREVIEW UPDATE
                        # ============================================

                        def update_preview_fixed(base_img, layers, size_key, bg_color, template_path, bg_type):
                            print(f"🔄 UPDATING PREVIEW with {len(layers)} layers")
                            
                            # Debug: Print all layer colors
                            for i, layer in enumerate(layers):
                                if layer.type == 'text':
                                    props = layer.properties
                                    print(f"    📝 Layer {i}: '{props.get('text')}' with color '{props.get('color')}'")
                            
                            # If we have a base image in state, use it
                            if base_img is not None:
                                rendered_image = render_social_post_direct(size_key, bg_color, template_path, bg_type, layers, base_img)
                                layer_text = format_social_layers(layers)
                                return rendered_image, layer_text
                            
                            # If no base_img, create one (e.g., on first load)
                            try:
                                width, height = post_sizes[size_key]
                                if bg_type == "Template" and template_path:
                                    if isinstance(template_path, dict):
                                        template_path = template_path.get('name') or template_path.get('data') or list(template_path.values())[0]
                                    
                                    if isinstance(template_path, str) and os.path.exists(template_path):
                                        base_img_pil = Image.open(template_path).convert('RGBA')
                                        base_img_pil = base_img_pil.resize((width, height), Image.Resampling.LANCZOS)
                                        base_img_rgb = Image.new("RGB", base_img_pil.size, (255, 255, 255))
                                        base_img_rgb.paste(base_img_pil, mask=base_img_pil.split()[3] if base_img_pil.mode == 'RGBA' else None)
                                        base_img = base_img_rgb
                                    else:
                                        base_img = Image.new('RGB', (width, height), "#FFFFFF")
                                else:
                                    if not isinstance(bg_color, str) or not bg_color.startswith('#'): 
                                        bg_color = "#FFFFFF"
                                    base_img = Image.new('RGB', (width, height), bg_color)
                                
                                rendered_image = render_social_post_direct(size_key, bg_color, template_path, bg_type, layers, base_img)
                                layer_text = format_social_layers(layers)
                                return rendered_image, layer_text
                                
                            except Exception as e:
                                print(f"Preview error: {e}")
                                error_img = Image.new('RGB', (300, 100), color='gray')
                                draw = ImageDraw.Draw(error_img)
                                draw.text((10,10), f"Error: {str(e)[:50]}", fill="white")
                                return error_img, format_social_layers(layers)
                        
                        # A list of all components that should trigger a preview refresh
                        preview_triggers = [
                            social_post_base_image, 
                            social_layers_state, 
                            post_size_dd, 
                            bg_color_picker, 
                            template_selection_state, 
                            bg_type_radio
                        ]
                        
                        # Update preview on ANY change to the triggers
                        for trigger in preview_triggers:
                            trigger.change(
                                 update_preview_fixed,
                                 preview_triggers,
                                 [post_preview_img, social_layers_list]
                            )

                        # Layer management
                        def remove_last_social_layer(layers):
                            if not layers: 
                                return layers, "No elements to remove"
                            return layers[:-1], "✅ Removed last element"
                        social_remove_last_btn.click(remove_last_social_layer, [social_layers_state], [social_layers_state, post_status_text])
                        
                        def clear_all_social_layers():
                            return [], "✅ Cleared all elements"
                        social_clear_all_btn.click(clear_all_social_layers, [], [social_layers_state, post_status_text])
                        
                        # Download
                        def save_image_fixed(image_data, format_choice):
                            if image_data is None: return None, "❌ No image to save"
                            try:
                                suffix = '.png' if format_choice == "PNG" else '.jpg'
                                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                                
                                if isinstance(image_data, Image.Image):
                                    img_to_save = image_data
                                elif isinstance(image_data, np.ndarray):
                                    img_to_save = Image.fromarray(image_data)
                                else:
                                    return None, "❌ Invalid image data"
                                
                                if img_to_save.mode != 'RGB':
                                    img_to_save = img_to_save.convert('RGB')
                                
                                if format_choice == "PNG":
                                    img_to_save.save(temp_file.name, format="PNG")
                                else:
                                    img_to_save.save(temp_file.name, format="JPEG", quality=95)
                                    
                                temp_file.close()
                                return temp_file.name, "✅ Ready to download!"
                            except Exception as e:
                                return None, f"❌ Save error: {e}"

                        social_prepare_download_btn.click(
                            save_image_fixed,
                            [post_preview_img, social_format_choice],
                            [social_download_file, social_download_status]
                        )

        # Format layers function
        def format_social_layers(social_layers: List[SocialLayer]) -> str:
            if not social_layers:
                return "No elements added yet"
            lines = []
            for layer in social_layers:
                status = "👁️" if layer.visible else "🚫"
                layer_type = layer.type.capitalize()
                desc = ""
                if layer.type == 'text':
                    text = layer.properties.get('text', '')
                    color = layer.properties.get('color', '#000000')
                    desc = f"'{text[:20]}...' Color: {color}"
                elif layer.type == 'logo':
                    desc = f"Logo"
                lines.append(f"{status} {layer_type}: {desc}")
            return "\n".join(lines)

        # [Rest of your existing event handlers for auth, etc.]
        # You would paste your login_btn.click, reg_btn.click, etc. here

    return demo

# ============================================
# LAUNCH
# ============================================

if __name__ == "__main__":
    # Ensure fonts and templates folders exist, or at least warn the user
    if not os.path.exists("fonts"):
        print("INFO: 'fonts' directory not found. Only default font will be available.")
    if not os.path.exists("templates"):
        print("INFO: 'templates' directory not found. No templates will be available.")
        
    demo = create_interface()
    demo.launch(server_name="0.0.0.0", server_port=8000)