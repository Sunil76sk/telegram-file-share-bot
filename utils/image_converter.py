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

    async def fit_image(
        self,
        image_bytes: bytes,
        ratio: str,  # "1:1" | "9:16" | "16:9" | "4:5" | "original"
        style: str,  # "crop" | "blur"
    ) -> bytes:
        """
        Resize, crop, or blur-fit an image to a target aspect ratio.
        """
        def _process():
            original = Image.open(io.BytesIO(image_bytes))
            if original.mode != "RGB":
                original = original.convert("RGB")

            if ratio == "original":
                out_io = io.BytesIO()
                original.save(out_io, format="JPEG", quality=90)
                return out_io.getvalue()

            # Target dimensions
            dimensions = {
                "1:1": (1080, 1080),
                "9:16": (1080, 1920),
                "16:9": (1920, 1080),
                "4:5": (1080, 1350)
            }
            target_w, target_h = dimensions.get(ratio, (1080, 1080))
            target_ratio = target_w / target_h

            w, h = original.size
            orig_ratio = w / h

            if style == "crop":
                # Crop to fill the target container
                if orig_ratio > target_ratio:
                    new_h = target_h
                    new_w = int(target_h * orig_ratio)
                    resized = original.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    left = (new_w - target_w) // 2
                    bg = resized.crop((left, 0, left + target_w, target_h))
                else:
                    new_w = target_w
                    new_h = int(target_w / orig_ratio)
                    resized = original.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    top = (new_h - target_h) // 2
                    bg = resized.crop((0, top, target_w, top + target_h))
            else:
                # Blur background and contain original image inside target container
                if orig_ratio > target_ratio:
                    new_h = target_h
                    new_w = int(target_h * orig_ratio)
                    resized = original.resize((new_w, new_h), Image.Resampling.BILINEAR)
                    left = (new_w - target_w) // 2
                    cropped = resized.crop((left, 0, left + target_w, target_h))
                else:
                    new_w = target_w
                    new_h = int(target_w / orig_ratio)
                    resized = original.resize((new_w, new_h), Image.Resampling.BILINEAR)
                    top = (new_h - target_h) // 2
                    cropped = resized.crop((0, top, target_w, top + target_h))
                
                blurred = cropped.filter(ImageFilter.GaussianBlur(radius=25))
                enhancer = ImageEnhance.Brightness(blurred)
                bg = enhancer.enhance(0.5)

                # Fit original inside target container
                if orig_ratio > target_ratio:
                    fit_w = target_w
                    fit_h = int(target_w / orig_ratio)
                else:
                    fit_h = target_h
                    fit_w = int(target_h * orig_ratio)
                
                resized_orig = original.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
                
                # Paste centered
                offset_x = (target_w - fit_w) // 2
                offset_y = (target_h - fit_h) // 2
                bg.paste(resized_orig, (offset_x, offset_y))

            out_io = io.BytesIO()
            bg.save(out_io, format="JPEG", quality=90)
            return out_io.getvalue()

        return await asyncio.to_thread(_process)

    def _create_black_bg(self, size: tuple) -> Image.Image:
        """Pure black background RGB(0,0,0)"""
        return Image.new("RGB", size, (0, 0, 0))

    def _create_blur_bg(self, original: Image.Image, size: tuple) -> Image.Image:
        w, h = original.size
        aspect = w / h
        target_w, target_h = size

        if aspect > 1:
            new_h = target_h
            new_w = int(target_h * aspect)
            resized = original.resize((new_w, new_h), Image.Resampling.BILINEAR)
            left = (new_w - target_w) // 2
            cropped = resized.crop((left, 0, left + target_w, target_h))
        else:
            new_w = target_w
            new_h = int(target_w / aspect)
            resized = original.resize((new_w, new_h), Image.Resampling.BILINEAR)
            top = (new_h - target_h) // 2
            cropped = resized.crop((0, top, target_w, top + target_h))

        blurred = cropped.filter(ImageFilter.GaussianBlur(radius=20))
        enhancer = ImageEnhance.Brightness(blurred)
        bg = enhancer.enhance(0.6)
        return bg

    def _create_white_bg(self, size: tuple) -> Image.Image:
        """Pure white background RGB(255,255,255)"""
        return Image.new("RGB", size, (255, 255, 255))
