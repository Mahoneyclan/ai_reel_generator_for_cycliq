# source/steps/splash_builders/collage_builder.py
"""
Collage image builder for splash sequences.
Handles grid layout calculation and tile composition.
"""

from __future__ import annotations
import math
from pathlib import Path
from typing import Tuple, List
from PIL import Image

from ...utils.log import setup_logger

log = setup_logger("steps.splash_builders.collage_builder")


class CollageBuilder:
    """Builds collage images from frame tiles using optimal grid layout."""
    
    def __init__(self, canvas_width: int, canvas_height: int):
        """
        Args:
            canvas_width: Output canvas width in pixels
            canvas_height: Output canvas height in pixels
        """
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
    
    def calculate_grid(self, num_images: int) -> Tuple[int, int, int, int]:
        """
        Calculate optimal grid layout for N images.
        
        Args:
            num_images: Number of images to tile
            
        Returns:
            Tuple of (cols, rows, tile_width, tile_height)
        """
        if num_images <= 0:
            return 1, 1, self.canvas_width, self.canvas_height
        
        # Calculate optimal aspect-ratio-preserving grid
        ratio = self.canvas_width / self.canvas_height
        cols = max(1, int(round(math.sqrt(num_images * ratio))))
        rows = max(1, math.ceil(num_images / cols))
        
        # Ensure we have enough slots
        while cols * rows < num_images:
            cols += 1
            rows = math.ceil(num_images / cols)
        
        tile_w = self.canvas_width // cols
        tile_h = self.canvas_height // rows
        
        log.debug(f"[collage] Grid: {cols}x{rows} for {num_images} images ({tile_w}x{tile_h} tiles)")
        
        return cols, rows, tile_w, tile_h
    
    def build_collage(self, image_paths: List[Path]) -> Image.Image:
        """
        Build collage from image file paths.
        
        Args:
            image_paths: List of paths to image files
            
        Returns:
            PIL Image containing the collage
        """
        if not image_paths:
            log.warning("[collage] No images provided, returning black canvas")
            return Image.new("RGB", (self.canvas_width, self.canvas_height), (20, 20, 20))
        
        cols, rows, tile_w, tile_h = self.calculate_grid(len(image_paths))
        
        # Create canvas with dark background
        canvas = Image.new("RGB", (self.canvas_width, self.canvas_height), (8, 8, 8))
        
        # Paste tiles
        idx = 0
        for row in range(rows):
            for col in range(cols):
                if idx >= len(image_paths):
                    break
                
                try:
                    # Load and resize image
                    src = Image.open(image_paths[idx]).convert("RGB")
                    tile = src.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
                    
                    # Paste at grid position
                    x = col * tile_w
                    y = row * tile_h
                    canvas.paste(tile, (x, y))
                    
                except Exception as e:
                    log.warning(f"[collage] Failed to load {image_paths[idx].name}: {e}")
                    # Fill with black tile on error
                    black_tile = Image.new("RGB", (tile_w, tile_h), (0, 0, 0))
                    canvas.paste(black_tile, (col * tile_w, row * tile_h))
                
                idx += 1
        
        log.info(f"[collage] Built {cols}x{rows} collage from {len(image_paths)} images")
        return canvas
    
    def extract_tile_regions(self, grid_info: Tuple[int, int, int, int]) -> List[Tuple[int, int, int, int]]:
        """
        Extract tile bounding boxes for animation purposes.
        
        Args:
            grid_info: (cols, rows, tile_w, tile_h) from calculate_grid()
            
        Returns:
            List of (x, y, width, height) tuples for each tile
        """
        cols, rows, tile_w, tile_h = grid_info
        regions = []
        
        for row in range(rows):
            for col in range(cols):
                x = col * tile_w
                y = row * tile_h
                regions.append((x, y, tile_w, tile_h))
        
        return regions