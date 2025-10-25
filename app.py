<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Post Creator</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }

        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .container {
            display: flex;
            max-width: 1200px;
            width: 100%;
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .sidebar {
            width: 300px;
            background-color: #f8f9fa;
            padding: 25px;
            border-right: 1px solid #eaeaea;
            overflow-y: auto;
            height: 100%;
        }

        .preview-area {
            flex: 1;
            padding: 30px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }

        h1 {
            color: #333;
            margin-bottom: 25px;
            font-size: 24px;
            text-align: center;
        }

        h2 {
            color: #555;
            margin: 20px 0 15px 0;
            font-size: 18px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 8px;
        }

        .section {
            margin-bottom: 25px;
        }

        .size-option {
            display: flex;
            justify-content: space-between;
            background-color: white;
            border-radius: 8px;
            padding: 12px 15px;
            margin-bottom: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            border: 2px solid #e0e0e0;
            cursor: pointer;
            transition: all 0.3s;
        }

        .size-option.active {
            border-color: #405de6;
            background-color: #f0f4ff;
        }

        .size-option i {
            color: #405de6;
        }

        .color-picker {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }

        .color-option {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            cursor: pointer;
            border: 2px solid #ddd;
            transition: transform 0.2s;
        }

        .color-option:hover {
            transform: scale(1.1);
        }

        .color-option.active {
            border-color: #333;
            transform: scale(1.1);
        }

        .bg-patterns {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }

        .pattern {
            width: 40px;
            height: 40px;
            border-radius: 5px;
            cursor: pointer;
            border: 2px solid #ddd;
        }

        .pattern.active {
            border-color: #405de6;
        }

        input, textarea, select {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #ddd;
            margin-bottom: 15px;
            font-size: 14px;
        }

        textarea {
            height: 100px;
            resize: vertical;
        }

        button {
            background-color: #405de6;
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: background-color 0.3s;
            width: 100%;
            margin-bottom: 10px;
        }

        button:hover {
            background-color: #304ac9;
        }

        .btn-secondary {
            background-color: #6c757d;
        }

        .btn-secondary:hover {
            background-color: #5a6268;
        }

        .btn-danger {
            background-color: #dc3545;
        }

        .btn-danger:hover {
            background-color: #c82333;
        }

        .post-preview {
            width: 400px;
            height: 400px;
            background: linear-gradient(45deg, #405de6, #5851db, #833ab4, #c13584, #e1306c, #fd1d1d);
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 25px;
        }

        .post-content {
            padding: 30px;
            text-align: center;
            color: white;
            width: 100%;
        }

        .post-title {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 15px;
            text-shadow: 1px 1px 3px rgba(0,0,0,0.3);
        }

        .post-text {
            font-size: 16px;
            line-height: 1.5;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        }

        .logo-placeholder {
            position: absolute;
            bottom: 20px;
            right: 20px;
            width: 50px;
            height: 50px;
            background-color: rgba(255, 255, 255, 0.2);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 20px;
            cursor: pointer;
        }

        .upload-area {
            border: 2px dashed #ddd;
            border-radius: 8px;
            padding: 30px;
            text-align: center;
            margin-bottom: 20px;
            cursor: pointer;
            transition: background-color 0.3s;
        }

        .upload-area:hover {
            background-color: #f8f9fa;
        }

        .upload-area i {
            font-size: 40px;
            color: #6c757d;
            margin-bottom: 10px;
        }

        .elements-list {
            background-color: white;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            min-height: 100px;
            border: 1px solid #eaeaea;
        }

        .element-item {
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .element-item i {
            color: #6c757d;
            cursor: pointer;
        }

        .action-buttons {
            display: flex;
            gap: 10px;
        }

        .action-buttons button {
            flex: 1;
        }

        .download-options {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }

        .download-options select {
            flex: 2;
            margin-bottom: 0;
        }

        .download-options button {
            flex: 1;
            margin-bottom: 0;
        }

        .status {
            margin-top: 20px;
            padding: 15px;
            background-color: #e7f3ff;
            border-radius: 8px;
            border-left: 4px solid #405de6;
        }

        @media (max-width: 900px) {
            .container {
                flex-direction: column;
            }
            .sidebar {
                width: 100%;
            }
            .post-preview {
                width: 300px;
                height: 300px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="sidebar">
            <h1>Instagram Post Creator</h1>
            
            <div class="section">
                <h2>1. Setup</h2>
                <div class="size-option active">
                    <span>Instagram Post</span>
                    <i class="fas fa-check-circle"></i>
                </div>
                <div class="size-option">
                    <span>Instagram Story</span>
                    <i class="far fa-circle"></i>
                </div>
            </div>

            <div class="section">
                <h2>Set Background & Size</h2>
                <div class="color-picker">
                    <div class="color-option active" style="background: linear-gradient(45deg, #405de6, #5851db, #833ab4, #c13584, #e1306c, #fd1d1d);"></div>
                    <div class="color-option" style="background-color: #4A90E2;"></div>
                    <div class="color-option" style="background-color: #50E3C2;"></div>
                    <div class="color-option" style="background-color: #B8E986;"></div>
                    <div class="color-option" style="background-color: #F5A623;"></div>
                    <div class="color-option" style="background-color: #D0021B;"></div>
                    <div class="color-option" style="background-color: #9013FE;"></div>
                    <div class="color-option" style="background-color: #ffffff; border: 1px solid #ccc;"></div>
                </div>
                
                <h3 style="margin-top: 15px; font-size: 14px;">Background Patterns</h3>
                <div class="bg-patterns">
                    <div class="pattern active" style="background: linear-gradient(45deg, #405de6, #5851db, #833ab4);"></div>
                    <div class="pattern" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"></div>
                    <div class="pattern" style="background: linear-gradient(120deg, #a1c4fd 0%, #c2e9fb 100%);"></div>
                    <div class="pattern" style="background: linear-gradient(120deg, #f6d365 0%, #fda085 100%);"></div>
                    <div class="pattern" style="background: linear-gradient(120deg, #84fab0 0%, #8fd3f4 100%);"></div>
                    <div class="pattern" style="background: linear-gradient(120deg, #ff9a9e 0%, #fecfef 100%);"></div>
                </div>
                
                <div style="margin-top: 15px;">
                    <label>Custom Background Color:</label>
                    <input type="color" id="custom-color" value="#405de6" style="height: 40px;">
                </div>
            </div>

            <div class="section">
                <h2>2. Add Elements</h2>
                <select>
                    <option>Text Effect Preset</option>
                    <option>Shadow Effect</option>
                    <option>Gradient Text</option>
                    <option>3D Text</option>
                    <option>Outline Text</option>
                </select>
                
                <input type="text" placeholder="Heading Text - Your Catch: Title...">
                <textarea placeholder="Paragraph Text - Add more details here..."></textarea>
                
                <button><i class="fas fa-plus"></i> Add Heading</button>
                <button class="btn-secondary"><i class="fas fa-plus"></i> Add Paragraph</button>
            </div>

            <div class="section">
                <h2>Font Style</h2>
                <select>
                    <option>Abhaya Regular (Sinhala)</option>
                    <option>Arial</option>
                    <option>Helvetica</option>
                    <option>Times New Roman</option>
                    <option>Georgia</option>
                    <option>Verdana</option>
                </select>
                
                <h2>Text Color</h2>
                <div class="color-picker">
                    <div class="color-option active" style="background-color: #ffffff;"></div>
                    <div class="color-option" style="background-color: #000000;"></div>
                    <div class="color-option" style="background-color: #405de6;"></div>
                    <div class="color-option" style="background-color: #e1306c;"></div>
                    <div class="color-option" style="background-color: #ffdc80;"></div>
                </div>
                
                <div style="margin-top: 15px;">
                    <label>Custom Text Color:</label>
                    <input type="color" id="custom-text-color" value="#ffffff" style="height: 40px;">
                </div>
            </div>
            
            <div class="section">
                <h2>Upload Logo/Image</h2>
                <div class="upload-area">
                    <i class="fas fa-cloud-upload-alt"></i>
                    <p>Drop Image Here</p>
                    <p>- or -</p>
                    <p>Click to Upload</p>
                </div>
            </div>
        </div>

        <div class="preview-area">
            <h2>Post Preview</h2>
            <p style="margin-bottom: 20px; color: #666; text-align: center;">Click on the image to set logo position</p>
            
            <div class="post-preview" id="post-preview">
                <div class="post-content">
                    <div class="post-title">Your Catchy Title Here</div>
                    <div class="post-text">Add your engaging content here to attract your audience and convey your message effectively.</div>
                </div>
                <div class="logo-placeholder">
                    <i class="fas fa-plus"></i>
                </div>
            </div>
            
            <div class="status">
                <h2>Status</h2>
                <p><strong>Elements List</strong></p>
                <p>Current Elements</p>
                <div class="elements-list">
                    <div class="element-item">
                        <span>Heading: Your Catchy Title Here</span>
                        <i class="fas fa-times"></i>
                    </div>
                    <div class="element-item">
                        <span>Paragraph: Add your engaging content...</span>
                        <i class="fas fa-times"></i>
                    </div>
                </div>
                
                <div class="action-buttons">
                    <button class="btn-secondary"><i class="fas fa-undo"></i> Remove Last</button>
                    <button class="btn-danger"><i class="fas fa-trash"></i> Clear All</button>
                </div>
                
                <div class="download-options">
                    <select>
                        <option>PNG</option>
                        <option>JPG</option>
                        <option>SVG</option>
                    </select>
                    <button><i class="fas fa-download"></i> Download</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Color picker functionality
        const colorOptions = document.querySelectorAll('.color-option');
        const customColor = document.getElementById('custom-color');
        const postPreview = document.getElementById('post-preview');
        
        colorOptions.forEach(option => {
            option.addEventListener('click', function() {
                // Remove active class from all options
                colorOptions.forEach(opt => opt.classList.remove('active'));
                // Add active class to clicked option
                this.classList.add('active');
                
                // Apply background to preview
                const bgColor = window.getComputedStyle(this).backgroundColor;
                const bgImage = window.getComputedStyle(this).backgroundImage;
                
                if (bgImage !== 'none') {
                    postPreview.style.backgroundImage = bgImage;
                    postPreview.style.backgroundColor = '';
                } else {
                    postPreview.style.backgroundColor = bgColor;
                    postPreview.style.backgroundImage = '';
                }
            });
        });
        
        // Custom color picker
        customColor.addEventListener('input', function() {
            postPreview.style.background = this.value;
            
            // Update active state
            colorOptions.forEach(opt => opt.classList.remove('active'));
        });
        
        // Pattern selection
        const patterns = document.querySelectorAll('.pattern');
        
        patterns.forEach(pattern => {
            pattern.addEventListener('click', function() {
                patterns.forEach(p => p.classList.remove('active'));
                this.classList.add('active');
                
                const bgImage = window.getComputedStyle(this).backgroundImage;
                postPreview.style.backgroundImage = bgImage;
            });
        });
        
        // Text color selection
        const textColorOptions = document.querySelectorAll('.color-picker:last-of-type .color-option');
        const customTextColor = document.getElementById('custom-text-color');
        const postTitle = document.querySelector('.post-title');
        const postText = document.querySelector('.post-text');
        
        textColorOptions.forEach(option => {
            option.addEventListener('click', function() {
                textColorOptions.forEach(opt => opt.classList.remove('active'));
                this.classList.add('active');
                
                const textColor = window.getComputedStyle(this).backgroundColor;
                postTitle.style.color = textColor;
                postText.style.color = textColor;
            });
        });
        
        customTextColor.addEventListener('input', function() {
            postTitle.style.color = this.value;
            postText.style.color = this.value;
            
            textColorOptions.forEach(opt => opt.classList.remove('active'));
        });
        
        // Logo positioning
        const logoPlaceholder = document.querySelector('.logo-placeholder');
        
        postPreview.addEventListener('click', function(e) {
            const rect = postPreview.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // Position logo at click location
            logoPlaceholder.style.left = `${x - 25}px`;
            logoPlaceholder.style.top = `${y - 25}px`;
            logoPlaceholder.style.right = 'auto';
            logoPlaceholder.style.bottom = 'auto';
        });
        
        // Upload area functionality
        const uploadArea = document.querySelector('.upload-area');
        
        uploadArea.addEventListener('click', function() {
            alert('Upload functionality would be implemented here in a real application.');
        });
        
        // Remove element functionality
        const removeIcons = document.querySelectorAll('.element-item i');
        
        removeIcons.forEach(icon => {
            icon.addEventListener('click', function() {
                this.parentElement.remove();
            });
        });
        
        // Button functionality
        document.querySelector('.btn-secondary').addEventListener('click', function() {
            const elements = document.querySelectorAll('.element-item');
            if (elements.length > 0) {
                elements[elements.length - 1].remove();
            }
        });
        
        document.querySelector('.btn-danger').addEventListener('click', function() {
            const elements = document.querySelectorAll('.element-item');
            elements.forEach(el => el.remove());
        });
    </script>
</body>
</html>
