from __future__ import annotations

import io
import asyncio
from PIL import Image, ImageFilter, ImageEnhance

class ImageConverter:
    TARGET_SIZE = (1080, 1080)  # Square 1:1

    async def convert_to_square(
        self, 
        image_bytes: bytes, 
        style: str  # "black" | "blur" | "white"
    ) -> bytes:
        """
        Convert any image to 1080x1080 square.
        
        Steps:
        1. Open image
        2. Calculate aspect ratio
        3. Resize to fit within 1080x1080 (keep ratio)
        4. Create 1080x1080 background
        5. Paste resized image centered
        6. Apply background style
        7. Return as JPEG bytes
        """
        def _process():
            # Open the original image
            original = Image.open(io.BytesIO(image_bytes))
            # Convert to RGB mode if not already
            if original.mode != "RGB":
                original = original.convert("RGB")

            # 1. Create background based on style
            if style == "blur":
                bg = self._create_blur_bg(original, self.TARGET_SIZE)
            elif style == "white":
                bg = self._create_white_bg(self.TARGET_SIZE)
            else:  # default to black
                bg = self._create_black_bg(self.TARGET_SIZE)

            # 2. Resize original to fit within 1080x1080 (contain)
            w, h = original.size
            aspect = w / h
            if w > h:
                new_w = self.TARGET_SIZE[0]
                new_h = int(new_w / aspect)
            else:
                new_h = self.TARGET_SIZE[1]
                new_w = int(new_h * aspect)

            resized = original.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # 3. Paste centered
            offset_x = (self.TARGET_SIZE[0] - new_w) // 2
            offset_y = (self.TARGET_SIZE[1] - new_h) // 2
            bg.paste(resized, (offset_x, offset_y))

            # 4. Save to bytes
            out_io = io.BytesIO()
            bg.save(out_io, format="JPEG", quality=90)
            return out_io.getvalue()

        return await asyncio.to_thread(_process)

    def _create_black_bg(self, size: tuple) -> Image.Image:
        """Pure black background RGB(0,0,0)"""
        return Image.new("RGB", size, (0, 0, 0))

    def _create_blur_bg(self, original: Image.Image, size: tuple) -> Image.Image:
        """
        Steps:
        1. Resize original to fill 1080x1080 (cover, not contain)
        2. Apply GaussianBlur radius=20
        3. Reduce brightness by 40%
        4. Return as background
        """
        w, h = original.size
        aspect = w / h
        target_w, target_h = size

        if aspect > 1:  # original is wider than square
            # Match height to target, scale width larger
            new_h = target_h
            new_w = int(target_h * aspect)
            resized = original.resize((new_w, new_h), Image.Resampling.BILINEAR)
            # Crop width centered
            left = (new_w - target_w) // 2
            cropped = resized.crop((left, 0, left + target_w, target_h))
        else:  # original is taller than square
            # Match width to target, scale height larger
            new_w = target_w
            new_h = int(target_w / aspect)
            resized = original.resize((new_w, new_h), Image.Resampling.BILINEAR)
            # Crop height centered
            top = (new_h - target_h) // 2
            cropped = resized.crop((0, top, target_w, top + target_h))

        # Apply blur
        blurred = cropped.filter(ImageFilter.GaussianBlur(radius=20))
        # Reduce brightness by 40% (factor = 0.6)
        enhancer = ImageEnhance.Brightness(blurred)
        bg = enhancer.enhance(0.6)
        return bg

    def _create_white_bg(self, size: tuple) -> Image.Image:
        """Pure white background RGB(255,255,255)"""
        return Image.new("RGB", size, (255, 255, 255))
