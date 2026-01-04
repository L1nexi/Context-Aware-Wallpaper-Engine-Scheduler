from PIL import Image, ImageDraw, ImageFilter

class IconGenerator:
    """
    Procedurally generates aesthetic icons for the system tray.
    Uses Catppuccin Macchiato palette.
    """
    
    # Catppuccin Macchiato Palette
    COLORS = {
        "bg": (36, 39, 58, 0),        # Transparent BG
        "base": (36, 39, 58, 255),    # Dark circle background
        "active": (138, 173, 244, 255), # Blue (Running)
        "paused": (147, 153, 178, 255), # Overlay2 (Paused/Gray)
        "core": (245, 189, 230, 255),   # Pink (Core center)
        "ring": (183, 189, 248, 255)    # Lavender (Outer ring)
    }

    @staticmethod
    def generate(paused=False, size=64):
        """
        Generates an icon dynamically.
        :param paused: If True, generates a desaturated/dimmed icon.
        :param size: Output size (default 64x64).
        """
        # 1. Draw at 4x resolution for anti-aliasing (Super Sampling)
        canvas_size = size * 4
        # Use RGBA for transparency
        img = Image.new('RGBA', (canvas_size, canvas_size), IconGenerator.COLORS["bg"])
        dc = ImageDraw.Draw(img)

        # Config
        center = canvas_size // 2
        radius = canvas_size // 2 - 4 # Padding
        
        main_color = IconGenerator.COLORS["paused"] if paused else IconGenerator.COLORS["active"]
        ring_color = IconGenerator.COLORS["paused"] if paused else IconGenerator.COLORS["ring"]
        core_color = IconGenerator.COLORS["paused"] if paused else IconGenerator.COLORS["core"]

        # 2. Draw Background Base (Dark Circle)
        dc.ellipse(
            [4, 4, canvas_size-4, canvas_size-4], 
            fill=IconGenerator.COLORS["base"]
        )

        # 3. Draw Outer Ring (The "Sensor" feel)
        # Thick stroke
        stroke_width = canvas_size // 10
        dc.ellipse(
            [10, 10, canvas_size-10, canvas_size-10], 
            outline=main_color, 
            width=stroke_width
        )

        # 4. Draw Inner Elements (The "Vector" feel)
        # A triangle or a smaller circle indicating direction/state
        inner_r = radius // 2.5
        
        if paused:
            # Draw a "Hollow Core" (Standby mode)
            # A thick ring in the center, instead of a solid circle or bars
            # Matches the "Circles" aesthetic
            stroke_w = canvas_size // 12
            dc.ellipse(
                [center - inner_r, center - inner_r, center + inner_r, center + inner_r],
                outline=ring_color,
                width=stroke_w
            )
        else:
            # Draw a "Core" (Solid circle) representing the active context
            dc.ellipse(
                [center - inner_r, center - inner_r, center + inner_r, center + inner_r],
                fill=core_color
            )
            # Optional: A small "Orbit" dot to show activity
            orbit_r = radius * 0.7
            orbit_dot_r = canvas_size // 16
            # Fixed position for static icon, but looks cool
            dc.ellipse(
                [center + orbit_r - orbit_dot_r, center - orbit_r - orbit_dot_r, 
                 center + orbit_r + orbit_dot_r, center - orbit_r + orbit_dot_r],
                fill=ring_color
            )

        # 5. Resize down to target size (High Quality Downsampling)
        # LANCZOS is the best filter for downscaling
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        return img