
"""
Hotkey Manager for KDE Plasma on Wayland
Uses KDE's GlobalShortcuts portal via D-Bus

Requirements:
    pip install dbus-python PyGObject
"""

import threading
import os
from typing import Callable, Dict, Optional
from gi.repository import GLib

try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
except ImportError:
    raise ImportError("Please install dbus-python and PyGObject: pip install dbus-python PyGObject")


class HotkeyManager:
    """
    A class to manage global hotkeys on KDE Plasma with Wayland.
    
    Uses the org.freedesktop.portal.GlobalShortcuts D-Bus interface.
    """
    
    def __init__(self, app_name: str = "PythonHotkeyApp"):
        """
        Initialize the Hotkey Manager.
        
        Args:
            app_name: A unique identifier for your application
        """
        self.app_name = app_name
        self._callbacks: Dict[str, Callable] = {}
        self._shortcuts: Dict[str, dict] = {}
        self._running = False
        self._loop: Optional[GLib.MainLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session_handle: Optional[str] = None
        self._request_counter = 0
        
        # Initialize D-Bus
        DBusGMainLoop(set_as_default=True)
        self._session_bus = dbus.SessionBus()
        
        # Get unique connection name for handle paths
        self._sender_name = self._session_bus.get_unique_name().replace('.', '_').replace(':', '')
        
        self._init_portal()
    
    def _get_request_token(self) -> str:
        """Generate a unique request token."""
        self._request_counter += 1
        return f"request{self._request_counter}"
    
    def _get_session_token(self) -> str:
        """Generate a unique session token."""
        return f"session_{os.getpid()}"
    
    def _init_portal(self):
        """Initialize using XDG Desktop Portal GlobalShortcuts."""
        try:
            self._portal = self._session_bus.get_object(
                'org.freedesktop.portal.Desktop',
                '/org/freedesktop/portal/desktop'
            )
            self._shortcuts_interface = dbus.Interface(
                self._portal,
                'org.freedesktop.portal.GlobalShortcuts'
            )
            
            # Connect to the Activated signal
            self._session_bus.add_signal_receiver(
                self._on_shortcut_activated,
                signal_name='Activated',
                dbus_interface='org.freedesktop.portal.GlobalShortcuts',
                path_keyword='path'
            )
            
            # Connect to the Deactivated signal
            self._session_bus.add_signal_receiver(
                self._on_shortcut_deactivated,
                signal_name='Deactivated',
                dbus_interface='org.freedesktop.portal.GlobalShortcuts',
                path_keyword='path'
            )
            
        except dbus.exceptions.DBusException as e:
            raise RuntimeError(f"Failed to connect to GlobalShortcuts portal: {e}")
    
    def _create_session(self) -> bool:
        """Create a GlobalShortcuts session."""
        if self._session_handle:
            return True
        
        try:
            request_token = self._get_request_token()
            session_token = self._get_session_token()
            
            # Expected request object path
            request_path = f"/org/freedesktop/portal/desktop/request/{self._sender_name}/{request_token}"
            
            # Set up response handler before making the call
            response_received = threading.Event()
            session_result = {'handle': None, 'success': False}
            
            def on_response(response, results):
                if response == 0:  # Success
                    session_result['handle'] = results.get('session_handle', '')
                    session_result['success'] = True
                response_received.set()
            
            self._session_bus.add_signal_receiver(
                on_response,
                signal_name='Response',
                dbus_interface='org.freedesktop.portal.Request',
                path=request_path
            )
            
            options = dbus.Dictionary({
                'handle_token': dbus.String(request_token),
                'session_handle_token': dbus.String(session_token),
            }, signature='sv')
            
            self._shortcuts_interface.CreateSession(options)
            
            # Wait for response (with timeout)
            if response_received.wait(timeout=5.0):
                if session_result['success']:
                    self._session_handle = session_result['handle']
                    if not self._session_handle:
                        # Construct session handle if not returned
                        self._session_handle = f"/org/freedesktop/portal/desktop/session/{self._sender_name}/{session_token}"
                    return True
            
            print("Failed to create session: timeout or error")
            return False
            
        except dbus.exceptions.DBusException as e:
            print(f"Failed to create session: {e}")
            return False
    
    def register_hotkey(
        self, 
        shortcut_id: str, 
        key_combination: str, 
        callback: Callable,
        description: str = ""
    ) -> bool:
        """
        Register a global hotkey.
        
        Args:
            shortcut_id: Unique identifier for this shortcut (e.g., "toggle_window")
            key_combination: Key combination string (e.g., "Meta+Shift+A", "Ctrl+Alt+T")
            callback: Function to call when the hotkey is triggered
            description: Human-readable description of what the shortcut does
            
        Returns:
            True if registration was successful, False otherwise
        """
        # Ensure session exists
        if not self._create_session():
            print("Failed to create session for hotkey registration")
            return False
        
        self._callbacks[shortcut_id] = callback
        self._shortcuts[shortcut_id] = {
            'key': key_combination,
            'description': description
        }
        
        return self._bind_shortcuts()
    
    def _bind_shortcuts(self) -> bool:
        """Bind all registered shortcuts via the portal."""
        if not self._session_handle:
            return False
        
        try:
            request_token = self._get_request_token()
            request_path = f"/org/freedesktop/portal/desktop/request/{self._sender_name}/{request_token}"
            
            response_received = threading.Event()
            bind_result = {'success': False}
            
            def on_response(response, results):
                bind_result['success'] = (response == 0)
                if response == 0:
                    # Print bound shortcuts info
                    shortcuts = results.get('shortcuts', [])
                    for shortcut in shortcuts:
                        print(f"Bound shortcut: {shortcut}")
                response_received.set()
            
            self._session_bus.add_signal_receiver(
                on_response,
                signal_name='Response',
                dbus_interface='org.freedesktop.portal.Request',
                path=request_path
            )
            
            # Build shortcuts array
            shortcuts_array = dbus.Array([], signature='(sa{sv})')
            for shortcut_id, info in self._shortcuts.items():
                shortcut_dict = dbus.Dictionary({
                    'description': dbus.String(info['description'] or shortcut_id),
                    'preferred_trigger': dbus.String(info['key']),
                }, signature='sv')
                shortcuts_array.append(
                    dbus.Struct((dbus.String(shortcut_id), shortcut_dict), signature='sa{sv}')
                )
            
            options = dbus.Dictionary({
                'handle_token': dbus.String(request_token),
            }, signature='sv')
            
            self._shortcuts_interface.BindShortcuts(
                dbus.ObjectPath(self._session_handle),
                shortcuts_array,
                dbus.String(""),  # parent_window
                options
            )
            
            # Wait for response
            if response_received.wait(timeout=5.0):
                return bind_result['success']
            
            print("Bind shortcuts timeout")
            return False
            
        except dbus.exceptions.DBusException as e:
            print(f"Failed to bind shortcuts: {e}")
            return False
    
    def unregister_hotkey(self, shortcut_id: str) -> bool:
        """
        Unregister a previously registered hotkey.
        
        Args:
            shortcut_id: The identifier of the shortcut to remove
            
        Returns:
            True if successful, False otherwise
        """
        if shortcut_id in self._callbacks:
            del self._callbacks[shortcut_id]
        if shortcut_id in self._shortcuts:
            del self._shortcuts[shortcut_id]
        
        # Re-bind remaining shortcuts (effectively removing the unregistered one)
        if self._shortcuts:
            return self._bind_shortcuts()
        return True
    
    def _on_shortcut_activated(self, session_handle, shortcut_id, timestamp, options, path=None):
        """Handle shortcut activation from XDG Portal."""
        print(f"Shortcut activated: {shortcut_id}")
        if shortcut_id in self._callbacks:
            try:
                self._callbacks[shortcut_id]()
            except Exception as e:
                print(f"Error in hotkey callback for '{shortcut_id}': {e}")
    
    def _on_shortcut_deactivated(self, session_handle, shortcut_id, timestamp, options, path=None):
        """Handle shortcut deactivation from XDG Portal."""
        print(f"Shortcut deactivated: {shortcut_id}")
    
    def start(self, blocking: bool = False):
        """
        Start listening for hotkey events.
        
        Args:
            blocking: If True, blocks the current thread. 
                     If False, runs in a background thread.
        """
        if self._running:
            return
        
        self._running = True
        self._loop = GLib.MainLoop()
        
        if blocking:
            self._loop.run()
        else:
            self._thread = threading.Thread(target=self._loop.run, daemon=True)
            self._thread.start()
    
    def stop(self):
        """Stop listening for hotkey events."""
        self._running = False
        if self._loop:
            self._loop.quit()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
    
    def list_shortcuts(self) -> None:
        """List all currently bound shortcuts (for debugging)."""
        if not self._session_handle:
            print("No active session")
            return
        
        try:
            request_token = self._get_request_token()
            request_path = f"/org/freedesktop/portal/desktop/request/{self._sender_name}/{request_token}"
            
            response_received = threading.Event()
            
            def on_response(response, results):
                if response == 0:
                    shortcuts = results.get('shortcuts', [])
                    print("Currently bound shortcuts:")
                    for shortcut in shortcuts:
                        print(f"  - {shortcut}")
                response_received.set()
            
            self._session_bus.add_signal_receiver(
                on_response,
                signal_name='Response',
                dbus_interface='org.freedesktop.portal.Request',
                path=request_path
            )
            
            options = dbus.Dictionary({
                'handle_token': dbus.String(request_token),
            }, signature='sv')
            
            self._shortcuts_interface.ListShortcuts(
                dbus.ObjectPath(self._session_handle),
                options
            )
            
            response_received.wait(timeout=5.0)
            
        except dbus.exceptions.DBusException as e:
            print(f"Failed to list shortcuts: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.start(blocking=False)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


# Example usage
if __name__ == "__main__":
    import time
    
    def on_hotkey_1():
        print("🎉 Hotkey 1 triggered! (Meta+Shift+H)")
    
    def on_hotkey_2():
        print("🎉 Hotkey 2 triggered! (Ctrl+Alt+P)")
    
    # Create manager
    manager = HotkeyManager(app_name="MyPythonApp")
    
    # Start the event loop first (needed for D-Bus signals)
    manager.start(blocking=False)
    
    # Register hotkeys
    print("Registering hotkeys...")
    
    success1 = manager.register_hotkey(
        shortcut_id="my_action_1",
        key_combination="Meta+Shift+H",
        callback=on_hotkey_1,
        description="Trigger action 1"
    )
    print(f"Hotkey 1 registration: {'success' if success1 else 'failed'}")
    
    success2 = manager.register_hotkey(
        shortcut_id="my_action_2", 
        key_combination="Ctrl+Alt+P",
        callback=on_hotkey_2,
        description="Trigger action 2"
    )
    print(f"Hotkey 2 registration: {'success' if success2 else 'failed'}")
    
    print("\nHotkey manager started. Press Ctrl+C to exit.")
    print("Registered hotkeys:")
    print("  - Meta+Shift+H: Trigger action 1")
    print("  - Ctrl+Alt+P: Trigger action 2")
    print("\nNote: KDE may show a dialog to configure these shortcuts.")
    
    # List shortcuts
    time.sleep(1)
    manager.list_shortcuts()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        manager.stop()
