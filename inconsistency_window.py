import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

class InconsistencyWindow(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title="Inconsistency Detected", transient_for=parent)
        self.set_default_size(500, 400)
        self.set_modal(True)

        # Basic styling
        self.set_name("InconsistencyWindow")
        style_provider = Gtk.CssProvider()
        css = """
        #InconsistencyWindow {
            background-color: #3C3C3C;
            border-radius: 15px;
            border: 1px solid #FF5555;
        }
        #InconsistencyWindow GtkTextView {
            background-color: #1E1E1E;
            color: #E0E0E0;
            padding: 10px;
        }
        #InconsistencyWindow GtkLabel {
            color: #FFFFFF;
            font-weight: bold;
        }
        """
        style_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
        self.add(vbox)
        
        label = Gtk.Label(label="An inconsistency with past meetings may have been detected:")
        vbox.pack_start(label, False, False, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        vbox.pack_start(scrolled_window, True, True, 0)

        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textbuffer = self.textview.get_buffer()
        scrolled_window.add(self.textview)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda w: self.destroy())
        vbox.pack_start(close_btn, False, False, 0)

    def set_text(self, text):
        self.textbuffer.set_text(text)

    def show_and_present(self, text):
        self.set_text(text)
        self.show_all()
        self.present()
