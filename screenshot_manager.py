"""
Monitor-focused screenshot manager for recass.
Provides monitor enumeration and periodic screenshot capture.
"""

import os
import threading
import time
import datetime
import subprocess
from PIL import ImageGrab
import cv2
import numpy as np


class ScreenshotManager:
    """Manage periodic screenshots for recordings.

    Public attributes:
    - capture_target: 'all', 'disabled', or 'monitor:<name>'
    - disabled: bool
    """

    def __init__(self, output_dir, interval_seconds=10):
        self.output_dir = output_dir
        self.interval = interval_seconds
        self.capture_target = "all"
        self.disabled = False
        self._stop_event = threading.Event()
        self._thread = None
        # monitor_map: name -> (x, y, w, h)
        self.monitor_map = {}
        # Scale factor for Wayland fractional scaling
        self._scale_factor = 1.0
        self._previous_screenshot = None

    # --- Public helpers ---
    @staticmethod
    def list_capture_screens():
        """Return a list of (id, display_name) choices.

        Example ids:
        - 'disabled'
        - 'all'
        - 'monitor:HDMI-1'
        """
        choices = [("disabled", "❌ Disabled")]
        # Always offer All Screens
        choices.append(("all", "📺 All Screens"))

        # Try xrandr first
        try:
            out = subprocess.check_output(["xrandr", "--listmonitors"], stderr=subprocess.DEVNULL)
            out = out.decode(errors="ignore")
            # Lines like: " 0: +*eDP-1 1920/344x1080/193+0+0 eDP-1"
            for line in out.splitlines():
                line = line.strip()
                if not line or line.startswith("Monitors:"):
                    continue
                parts = line.split()
                # last token is usually monitor name
                name = parts[-1]
                # find geometry token like 1920/344x1080/193+0+0
                geom = None
                for p in parts:
                    if "+" in p and "x" in p:
                        geom = p
                        break
                display = f"🖥️ {name}"
                if geom:
                    display += f" ({geom})"
                choices.append((f"monitor:{name}", display))
        except Exception:
            # xrandr unavailable or failed; fall back to primary screen size
            try:
                img = ImageGrab.grab()
                w, h = img.size
                display = f"🖥️ Primary ({w}x{h})"
                choices.append(("monitor:primary", display))
            except Exception:
                # Give up gracefully; still have All/Disabled
                pass

        return choices

    # --- Monitor geometry refresh ---
    def _refresh_monitors(self):
        """Populate `self.monitor_map` with monitor name -> (x, y, w, h).

        Uses `xrandr` to get pixel dimensions and positions.
        On Wayland with fractional scaling, adjusts coordinates accordingly.
        Falls back to a single primary monitor covering the full virtual screen.
        """
        self.monitor_map = {}
        self._scale_factor = 1.0
        
        # Try xrandr for per-monitor geometry
        try:
            out = subprocess.check_output(["xrandr"], stderr=subprocess.DEVNULL)
            out = out.decode(errors="ignore")
            
            # First pass: collect all monitor geometries to calculate scale factor
            xrandr_monitors = {}
            total_xrandr_width = 0
            for line in out.splitlines():
                if " connected" not in line:
                    continue
                
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                name = parts[0]
                
                # Find the geometry token like 3840x2160+3840+0
                geom = None
                for p in parts:
                    if "x" in p and "+" in p:
                        geom = p
                        break
                
                if geom:
                    try:
                        size_part, offset_part = geom.split('+', 1)
                        w, h = size_part.split('x')
                        w, h = int(w), int(h)
                        offset_parts = offset_part.split('+')
                        x = int(offset_parts[0])
                        y = int(offset_parts[1]) if len(offset_parts) > 1 else 0
                        
                        xrandr_monitors[name] = (x, y, w, h)
                        total_xrandr_width = max(total_xrandr_width, x + w)
                    except (ValueError, IndexError):
                        continue
            
            # Calculate scale factor by comparing with actual ImageGrab size
            if xrandr_monitors:
                try:
                    grab_test = ImageGrab.grab()
                    actual_width = grab_test.size[0]
                    if total_xrandr_width > 0:
                        self._scale_factor = actual_width / total_xrandr_width
                    print(f"📊 Scale factor calculated: {self._scale_factor:.4f} (xrandr width: {total_xrandr_width}, actual: {actual_width})")
                except Exception:
                    pass
            
            # Apply scale factor and store monitors
            for name, (x, y, w, h) in xrandr_monitors.items():
                # Scale coordinates to match actual ImageGrab output
                x_scaled = int(x * self._scale_factor)
                y_scaled = int(y * self._scale_factor)
                w_scaled = int(w * self._scale_factor)
                h_scaled = int(h * self._scale_factor)
                self.monitor_map[name] = (x_scaled, y_scaled, w_scaled, h_scaled)
                
        except Exception:
            # xrandr not available or failed; fallback to whole screen
            try:
                img = ImageGrab.grab()
                w, h = img.size
                self.monitor_map["primary"] = (0, 0, w, h)
            except Exception:
                # can't determine geometry; leave monitor_map empty
                pass

    def _compare_images(self, img1_np, img2_np, threshold=30):
        """Compares two NumPy image arrays and returns the percentage of changed pixels."""
        # Ensure images are the same size
        if img1_np.shape != img2_np.shape:
            # If sizes differ, it's a significant change (e.g., monitor resolution change)
            return 100.0

        # Convert to grayscale for simpler comparison if they are RGB
        # ImageGrab.grab() returns RGBA, so we need to handle 4 channels (or 3 if converted)
        if len(img1_np.shape) == 3 and img1_np.shape[2] >= 3: # Check for RGB or RGBA
            img1_gray = cv2.cvtColor(img1_np, cv2.COLOR_RGBA2GRAY) if img1_np.shape[2] == 4 else cv2.cvtColor(img1_np, cv2.COLOR_RGB2GRAY)
            img2_gray = cv2.cvtColor(img2_np, cv2.COLOR_RGBA2GRAY) if img2_np.shape[2] == 4 else cv2.cvtColor(img2_np, cv2.COLOR_RGB2GRAY)
        else: # Already grayscale or 1 channel
            img1_gray = img1_np
            img2_gray = img2_np

        # Calculate absolute difference
        diff = cv2.absdiff(img1_gray, img2_gray)

        # Apply threshold to find significant changes
        # Pixels with a difference greater than 'threshold' are considered changed
        _, diff_thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

        # Count changed pixels (where diff_thresh is not zero)
        changed_pixels = np.sum(diff_thresh > 0)
        total_pixels = diff_thresh.size

        percentage_changed = (changed_pixels / total_pixels) * 100
        return percentage_changed

    # --- Capture loop control ---
    def start_capture(self):
        if self.disabled:
            print("📸 Screenshot capture disabled; not starting")
            return
        # Refresh monitor geometry before starting
        self._refresh_monitors()
        if self._thread and self._thread.is_alive():
            print("📸 Screenshot capture already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"📸 Screenshot capture started (target: {self.capture_target}, interval: {self.interval}s)")

    def stop_capture(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        print("📸 Screenshot capture stopped")

    def _capture_loop(self):
        count = 0
        while not self._stop_event.is_set():
            try:
                if not self.disabled:
                    self._take_screenshot()
                    count += 1
            except Exception as e:
                # log exceptions so we can debug
                print(f"❌ Error in screenshot capture loop: {e}")
                import traceback
                traceback.print_exc()
            # sleep in small increments so stop is responsive
            slept = 0.0
            while slept < self.interval and not self._stop_event.is_set():
                time.sleep(0.25)
                slept += 0.25

    # --- Screenshot taking ---
    def _take_screenshot(self):
        target = self.capture_target or "all"
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.output_dir, f"screenshot-{timestamp}.png")

        # If disabled, do nothing
        if target == "disabled" or self.disabled:
            return

        try:
            pil_img = None
            # If monitor specific and geometry known
            if target.startswith("monitor:"):
                key = target.split(":", 1)[1]
                geom = self.monitor_map.get(key)
                if geom is None:
                    # try refreshing monitors once
                    self._refresh_monitors()
                    geom = self.monitor_map.get(key)
                if geom:
                    x, y, w, h = geom
                    # bbox format for ImageGrab: (left, top, right, bottom)
                    bbox = (x, y, x + w, y + h)
                    print(f"📸 Capturing monitor {key}: geometry=({x},{y},{w}x{h}), bbox={bbox}")
                    pil_img = ImageGrab.grab(bbox=bbox)
                else:
                    print(f"⚠️  Monitor {key} geometry not available; falling back to all screens")

            if pil_img is None: # if monitor-specific failed or target is 'all'
                # default: grab the whole virtual screen
                print(f"📸 Capturing all screens")
                pil_img = ImageGrab.grab()
            
            current_screenshot_np = np.array(pil_img)

            if self._previous_screenshot is None:
                # Always save the first screenshot
                pil_img.save(filename)
                self._previous_screenshot = current_screenshot_np
                print(f"📸 First screenshot saved: {os.path.basename(filename)}")
                return
            
            # Compare with previous screenshot
            percentage_changed = self._compare_images(self._previous_screenshot, current_screenshot_np)
            
            if percentage_changed >= 10.0: # Check if significant change (10%)
                pil_img.save(filename)
                self._previous_screenshot = current_screenshot_np
                print(f"📸 Significant change detected ({percentage_changed:.2f}%); screenshot saved: {os.path.basename(filename)}")
            else:
                print(f"📸 Insignificant change detected ({percentage_changed:.2f}%); screenshot not saved.")

        except Exception as e:
            print(f"❌ Error taking screenshot: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    # Quick test: print available screens
    print(ScreenshotManager.list_capture_screens())

