# [file name]: audio_device_manager.py
"""Audio device management and selection for recass."""

import sounddevice as sd
from gi.repository import Gtk


class AudioDeviceManager:
    """Manages audio device selection and configuration."""
    
    def __init__(self, application):
        """
        Initialize audio device manager.
        
        Args:
            application: The main Application instance
        """
        self.app = application
        self.devices = []
        self.mic_dev_name = None
        self.loopback_dev_name = None
    
    def _refresh_devices(self):
        """Internal method to refresh sounddevice list."""
        print("DEBUG: Re-scanning audio devices")
        sd._terminate()
        sd._initialize()
        self.devices = sd.query_devices()
        print("DEBUG: Full device list from sounddevice:")
        print(self.devices)

    def get_device_ids_from_names(self, mic_name, loopback_name):
        """Get device IDs from their names, refreshing the device list."""
        if not mic_name or not loopback_name:
            print("Warning: Microphone or loopback device name not specified.")
            return None, None
        
        self._refresh_devices()
        mic_id, loopback_id = None, None
        
        try:
            mic_id = next(dev['index'] for dev in self.devices if dev['name'] == mic_name and dev['max_input_channels'] > 0)
        except StopIteration:
            print(f"Error: Could not find microphone device named '{mic_name}'.")

        try:
            loopback_id = next(dev['index'] for dev in self.devices if dev['name'] == loopback_name and dev['max_input_channels'] > 0)
        except StopIteration:
            print(f"Error: Could not find loopback device named '{loopback_name}'.")
            
        return mic_id, loopback_id
    
    def populate_audio_devices(self, widget=None):
        """(Re)populate audio device comboboxes."""
        if not self.app.mic_combo or not self.app.loopback_combo:
            return  # UI not initialized

        try:
            if self.app.mic_combo and hasattr(self.app, 'mic_combo_handler_id'):
                self.app.mic_combo.handler_block(self.app.mic_combo_handler_id)
            if self.app.loopback_combo and hasattr(self.app, 'loopback_combo_handler_id'):
                self.app.loopback_combo.handler_block(self.app.loopback_combo_handler_id)
            
            # Get saved device names to set them as active
            current_mic_name = self.mic_dev_name
            current_loopback_name = self.loopback_dev_name

            # Get all devices and separate them into mics and loopbacks
            self._refresh_devices()
            all_input_devices = [dev for dev in self.devices
                                 if dev.get('max_input_channels', 0) > 0]
            all_input_names = sorted([dev['name'] for dev in all_input_devices])

            # For loopback, show all available input devices to ensure that application
            # audio sources that don't contain 'monitor' in their name are selectable.
            loopback_devices = all_input_names

            # For microphones, filter out devices that are likely to be loopback devices.
            mic_devices = [name for name in all_input_names if 'monitor' not in name.lower()]

            # Fallback: If filtering left the mic list empty, populate it with all devices
            # as a safeguard.
            if not mic_devices:
                mic_devices = all_input_names

            # Populate mic combo
            self.app.mic_combo.remove_all()
            for dev_name in mic_devices:
                self.app.mic_combo.append_text(dev_name)
            if current_mic_name and current_mic_name in mic_devices:
                for i, item in enumerate(self.app.mic_combo.get_model()):
                    if item[0] == current_mic_name:
                        self.app.mic_combo.set_active(i)
                        break
            elif len(mic_devices) > 0:
                self.app.mic_combo.set_active(0)


            # Populate loopback combo
            self.app.loopback_combo.remove_all()
            for dev_name in loopback_devices:
                self.app.loopback_combo.append_text(dev_name)
            if current_loopback_name and current_loopback_name in loopback_devices:
                for i, item in enumerate(self.app.loopback_combo.get_model()):
                    if item[0] == current_loopback_name:
                        self.app.loopback_combo.set_active(i)
                        break
            elif len(loopback_devices) > 0:
                self.app.loopback_combo.set_active(0)

            print("Audio device list refreshed and separated.")
        except Exception as e:
            print(f"Fehler beim Aktualisieren der Audiogeräteliste: {e}")
        finally:
            if self.app.mic_combo and hasattr(self.app, 'mic_combo_handler_id'):
                self.app.mic_combo.handler_unblock(self.app.mic_combo_handler_id)
            if self.app.loopback_combo and hasattr(self.app, 'loopback_combo_handler_id'):
                self.app.loopback_combo.handler_unblock(self.app.loopback_combo_handler_id)
    
    def on_device_changed(self, widget):
        """Handle audio device change and restart audio processing."""
        if not self.app.mic_combo or not self.app.loopback_combo:
            return  # UI not initialized
        
        # This check is important to avoid acting on transient states during UI buildup
        if (self.app.mic_combo.get_active() == -1 or 
            self.app.loopback_combo.get_active() == -1):
            return
        
        new_mic_name = self.app.mic_combo.get_active_text()
        new_loopback_name = self.app.loopback_combo.get_active_text()
        
        if not new_mic_name or not new_loopback_name:
            return
        
        # --- Find device IDs ---
        try:
            # It's better to refresh the device list here to get fresh IDs
            self._refresh_devices()
            new_mic_id = next(dev['index'] for dev in self.devices if dev['name'] == new_mic_name)
            new_loopback_id = next(dev['index'] for dev in self.devices if dev['name'] == new_loopback_name)
        except (StopIteration, Exception) as e:
            print(f"Error finding new device IDs: {e}")
            return
            
        # --- Prevent unnecessary restarts ---
        if (self.app.mic_dev_id == new_mic_id and 
            self.app.loopback_dev_id == new_loopback_id):
            return

        # --- NEW VALIDATION LOGIC ---
        try:
            print(f"Validating mic device: '{new_mic_name}' (ID: {new_mic_id})...")
            with sd.InputStream(device=new_mic_id, channels=1, dtype='int16'):
                pass
            print(f"Validating loopback device: '{new_loopback_name}' (ID: {new_loopback_id})...")
            with sd.InputStream(device=new_loopback_id, channels=1, dtype='int16'):
                pass
            print("✅ Audio devices validated successfully.")
        except Exception as e:
            print(f"❌ Error: Failed to open one or more selected audio devices: {e}")
            print("   Please select different devices. Reverting selection.")
            
            # Revert the comboboxes
            self.app.mic_combo.handler_block(self.app.mic_combo_handler_id)
            self.app.loopback_combo.handler_block(self.app.loopback_combo_handler_id)

            try:
                # Find and set previous mic
                if self.mic_dev_name:
                    for i, item in enumerate(self.app.mic_combo.get_model()):
                        if item[0] == self.mic_dev_name:
                            self.app.mic_combo.set_active(i)
                            break
                else:
                    self.app.mic_combo.set_active(-1)

                # Find and set previous loopback
                if self.loopback_dev_name:
                    for i, item in enumerate(self.app.loopback_combo.get_model()):
                        if item[0] == self.loopback_dev_name:
                            self.app.loopback_combo.set_active(i)
                            break
                else:
                    self.app.loopback_combo.set_active(-1)
            finally:
                self.app.mic_combo.handler_unblock(self.app.mic_combo_handler_id)
                self.app.loopback_combo.handler_unblock(self.app.loopback_combo_handler_id)
            
            return # Stop processing
        
        # --- Start Audio Thread and Save Settings ---
        print("Audio devices changed. Restarting audio processing...")
        self.app._start_audio_processing_thread(new_mic_id, new_loopback_id)
        
        # Save the now-validated device names
        self.save_device_names(new_mic_name, new_loopback_name)
    
    def save_device_names(self, mic_name, loopback_name):
        """Save selected device names to settings."""
        from config import load_user_settings, save_user_settings
        
        try:
            if mic_name and loopback_name:
                settings = load_user_settings()
                settings['mic_dev_name'] = mic_name
                settings['loopback_dev_name'] = loopback_name
                save_user_settings(settings)
                
                # Update the manager's internal state as well
                self.mic_dev_name = mic_name
                self.loopback_dev_name = loopback_name
                print(f"Saved device names: Mic='{mic_name}', Loopback='{loopback_name}'")
        except Exception as e:
            print(f"Error saving device names: {e}")