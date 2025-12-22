"""System tray icon management using pystray."""
import pystray
from PIL import Image, ImageDraw
from gi.repository import GLib

class SystemTrayManager:
    def __init__(self, app):
        self.app = app
        self.icon = None

    def create_image(self, is_recording=False):
        """Create a simple icon image, red when recording."""
        width = 64
        height = 64
        # Use a red circle to indicate recording
        bg_color = 'black'
        fg_color = 'red' if is_recording else 'white'
        
        image = Image.new('RGB', (width, height), bg_color)
        dc = ImageDraw.Draw(image)
        
        # Draw a circle
        dc.ellipse((4, 4, 60, 60), fill=fg_color)
        
        # Draw a letter 'R'
        # To keep it simple, we'll just use a colored circle as indicator.
        # You can add more complex drawing if needed.
        return image

    def update_menu(self):
        """Update the menu, including the icon image if recording state changed."""
        if self.icon:
            self.icon.menu = self.create_menu()
            self.icon.icon = self.create_image(self.app.is_recording)
            # pystray doesn't have a public method to just update the menu,
            # but changing the 'menu' attribute works for some backends.
            # The icon change should be picked up automatically.
            print("DEBUG: SystemTrayManager.update_menu() called.")

    def on_quit(self):
        """Safely quit the application."""
        print("DEBUG: Quit from systray triggered.")
        self.icon.stop()
        # Gtk operations must be done in the main thread, use GLib.idle_add
        GLib.idle_add(self.app.quit_action, None, None)

    def create_menu(self):
        """Create the systray menu based on the current app state."""
        record_label = "Stop Recording" if self.app.is_recording else "Start Recording"

        # The language submenu from the original app is complex.
        # For now, we'll omit it to ensure the app runs.
        # A real implementation would dynamically build this menu.

        menu = pystray.Menu(
            pystray.MenuItem(record_label, self.app._on_systray_record_clicked, default=True),
            pystray.MenuItem('Take Manual Screenshot', self.app._on_systray_screenshot_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Show Settings', self.app.show_window),
            pystray.MenuItem('Open Chat', self.app.open_chat_window),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self.on_quit)
        )
        return menu

    def run(self):
        """Create and run the system tray icon."""
        image = self.create_image(self.app.is_recording)
        menu = self.create_menu()
        self.icon = pystray.Icon('recass', image, 'recass', menu)
        
        print("DEBUG: SystemTrayManager.run() called, starting icon.")
        # This will run in a blocking manner.
        # UI actions in the app are triggered by callbacks from the icon menu.
        self.icon.run()

    def stop(self):
        """Stop the system tray icon."""
        if self.icon:
            print("DEBUG: SystemTrayManager.stop() called.")
            self.icon.stop()