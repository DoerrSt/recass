# [file name]: timer_manager.py
"""Timer functionality for recording sessions."""

import time
import threading
from gi.repository import GLib


class TimerManager:
    """Manages recording timer functionality."""
    
    def __init__(self, application):
        """
        Initialize the timer manager.
        
        Args:
            application: The main Application instance
        """
        self.app = application
        self.timer_thread = None
        self.remaining_seconds = 0
        self.timer_enabled = False
        self.timer_seconds = 0
        self.timer_setting_str = "00:00:00"
    
    def hms_to_seconds(self, hms_str):
        """Convert hh:mm:ss string to seconds."""
        if not isinstance(hms_str, str):
            return None
        parts = hms_str.split(':')
        if len(parts) != 3:
            return None
        try:
            h = int(parts[0])
            m = int(parts[1])
            s = int(parts[2])
            return h * 3600 + m * 60 + s
        except (ValueError, IndexError):
            return None
    
    def start_timer(self):
        """Start the timer countdown if enabled and recording is active."""
        if self.timer_enabled and self.app.is_recording:
            self.remaining_seconds = self.timer_seconds
            self.timer_thread = threading.Thread(target=self._countdown, daemon=True)
            self.timer_thread.start()
    
    def stop_timer(self):
        """Stop the timer and reset state."""
        if self.timer_thread and self.timer_thread.is_alive():
            # The thread will exit on its own as is_recording is now False
            pass
    
    def reset_timer_display(self):
        """Reset the timer entry to the configured setting."""
        if hasattr(self.app, 'timer_entry') and self.app.timer_entry:
            self.app.timer_entry.set_text(self.timer_setting_str)
        return False
    
    def update_timer_display(self):
        """Update the timer entry with the remaining time."""
        if not hasattr(self.app, 'timer_entry'):
            return False
            
        h = self.remaining_seconds // 3600
        m = (self.remaining_seconds % 3600) // 60
        s = self.remaining_seconds % 60
        time_str = f"{h:02d}:{m:02d}:{s:02d}"
        
        if self.app.timer_entry and hasattr(self.app, 'timer_entry_handler_id'):
            # Temporarily block the 'changed' signal handler to prevent saving to config
            self.app.timer_entry.handler_block(self.app.timer_entry_handler_id)
            self.app.timer_entry.set_text(time_str)
            self.app.timer_entry.handler_unblock(self.app.timer_entry_handler_id)
        return False
    
    def _countdown(self):
        """The countdown logic for the timer thread."""
        while self.app.is_recording and self.timer_enabled and self.remaining_seconds > 0:
            GLib.idle_add(self.update_timer_display)
            time.sleep(1)
            self.remaining_seconds -= 1
        
        if self.app.is_recording and self.timer_enabled and self.remaining_seconds <= 0:
            print("Timer finished, stopping recording.")
            # Ensure the call is made in the GTK main thread
            GLib.idle_add(self.app._on_record_button_clicked, 
                         getattr(self.app, '_record_button', None))
    
    def on_timer_changed(self, widget):
        """Handle changes to the timer entry."""
        from config import load_user_settings, save_user_settings
        
        timer_str = widget.get_text().strip()
        new_seconds = self.hms_to_seconds(timer_str)
        if new_seconds is not None:
            self.timer_seconds = new_seconds
            self.timer_setting_str = timer_str
            self.remaining_seconds = self.timer_seconds
            settings = load_user_settings()
            settings['timer_value'] = timer_str
            save_user_settings(settings)
            print(f"Timer value set to: {timer_str} ({self.timer_seconds} seconds)")
    
    def on_timer_enabled_toggled(self, widget):
        """Handle toggling of the timer."""
        from config import load_user_settings, save_user_settings
        
        self.timer_enabled = widget.get_active()
        self.app.timer_enabled = self.timer_enabled
        settings = load_user_settings()
        settings['timer_enabled'] = self.timer_enabled
        save_user_settings(settings)
        print(f"Timer enabled set to: {self.timer_enabled}")
        
        if self.timer_enabled and self.app.is_recording:
            self.start_timer()