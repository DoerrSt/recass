import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
from history_window import HistoryWindow

class RecordingIndicatorWindow(Gtk.Window):
    def __init__(self, application):
        super().__init__(title="Recording")
        self.app = application

        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Basic styling
        self.set_name("RecordingIndicatorWindow")
        style_provider = Gtk.CssProvider()
        # A dark, rounded, modern look inspired by the image
        css = """
        #RecordingIndicatorWindow {
            background-color: #2E2E2E;
            border-radius: 20px;
            border: 1px solid #4A4A4A;
        }
        #RecordingIndicatorWindow GtkButton {
            background-color: #3B3B3B;
            border: 1px solid #555;
            border-radius: 10px;
            color: white;
            min-height: 30px;
            min-width: 30px;
        }
        #RecordingIndicatorWindow GtkButton:hover {
            background-color: #4A4A4A;
        }
        #RecordingIndicatorWindow GtkEntry {
            background-color: #1E1E1E;
            color: #E0E0E0;
            border: 1px solid #4A4A4A;
            border-radius: 10px;
            padding: 5px 10px;
        }
        """
        style_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hbox.set_margin_start(10)
        hbox.set_margin_end(10)
        hbox.set_margin_top(10)
        hbox.set_margin_bottom(10)
        self.add(hbox)

        self.mic_level_bar = Gtk.LevelBar()
        self.mic_level_bar.set_min_value(0)
        self.mic_level_bar.set_max_value(0.1)
        self.mic_level_bar.set_size_request(50, -1)
        
        self.loopback_level_bar = Gtk.LevelBar()
        self.loopback_level_bar.set_min_value(0)
        self.loopback_level_bar.set_max_value(0.1)
        self.loopback_level_bar.set_size_request(50, -1)
        
        level_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        level_box.pack_start(self.mic_level_bar, True, True, 0)
        level_box.pack_start(self.loopback_level_bar, True, True, 0)

        self._add_buttons(hbox)
        hbox.pack_start(level_box, False, False, 5)

    def update_level(self, source, level):
        if source == "MIC":
            self.mic_level_bar.set_value(level)
        elif source == "LOOPBACK":
            self.loopback_level_bar.set_value(level)

    def _on_history_clicked(self, widget):
        if not self.app.history_window:
            self.app.history_window = HistoryWindow(self.app)

        if self.app.history_window.is_visible():
            self.app.history_window.hide()
        else:
            # Position history window below recording window
            x, y = self.get_position()
            h = self.get_allocated_height()
            self.app.history_window.move(x, y + h + 10) # 10px spacing
            self.app.history_window.set_full_history(self.app.transcription_history)
            self.app.history_window.show_all()

    def _add_buttons(self, box):
        # System audio capture (headphones) - now stop button
        headphones_icon = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic", Gtk.IconSize.BUTTON)
        headphones_btn = Gtk.Button(image=headphones_icon)
        headphones_btn.connect("clicked", lambda widget: self.app._on_systray_record_clicked(None, None))
        box.pack_start(headphones_btn, False, False, 0)

        # "Ask me anything" entry
        ask_entry = Gtk.Entry()
        ask_entry.set_placeholder_text("Ask me anything...")
        ask_entry.set_size_request(250, -1)
        box.pack_start(ask_entry, True, True, 0)

        # Screenshots capture (desktop)
        screenshot_icon = Gtk.Image.new_from_icon_name("video-display-symbolic", Gtk.IconSize.BUTTON)
        screenshot_btn = Gtk.Button(image=screenshot_icon)
        screenshot_btn.connect("clicked", lambda widget: self.app._on_systray_screenshot_clicked(None, None))
        box.pack_start(screenshot_btn, False, False, 0)

        # History (clock)
        history_icon = Gtk.Image.new_from_icon_name("view-history-symbolic", Gtk.IconSize.BUTTON)
        history_btn = Gtk.Button(image=history_icon)
        history_btn.connect("clicked", self._on_history_clicked)
        box.pack_start(history_btn, False, False, 0)

        # Settings (gear)
        settings_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON)
        settings_btn = Gtk.Button(image=settings_icon)
        settings_btn.connect("clicked", lambda widget: self.app.show_window(None, None))
        box.pack_start(settings_btn, False, False, 0)
