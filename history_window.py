import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

class HistoryWindow(Gtk.Window):
    def __init__(self, application):
        super().__init__(title="Transcription History")
        self.app = application

        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_resizable(True)
        self.set_default_size(400, 300)

        # Basic styling
        self.set_name("HistoryWindow")
        style_provider = Gtk.CssProvider()
        css = """
        #HistoryWindow {
            background-color: #2E2E2E;
            border-radius: 15px;
            border: 1px solid #4A4A4A;
        }
        #HistoryWindow GtkTextView {
            background-color: #1E1E1E;
            color: #E0E0E0;
            padding: 10px;
        }
        #HistoryWindow GtkScrolledWindow {
            border-radius: 15px;
        }
        """
        style_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vbox.pack_start(scrolled_window, True, True, 0)

        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textbuffer = self.textview.get_buffer()
        scrolled_window.add(self.textview)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin=5)
        vbox.pack_start(button_box, False, False, 0)

        respond_btn = Gtk.Button(label="What to respond?")
        respond_btn.connect("clicked", self._on_respond_clicked)
        button_box.pack_start(respond_btn, True, True, 0)

        summarize_btn = Gtk.Button(label="What did I miss?")
        summarize_btn.connect("clicked", self._on_summarize_clicked)
        button_box.pack_start(summarize_btn, True, True, 0)

        details_btn = Gtk.Button(label="More details")
        details_btn.connect("clicked", self._on_details_clicked)
        button_box.pack_start(details_btn, True, True, 0)

    def _on_respond_clicked(self, widget):
        self.app.get_response_suggestion()

    def _on_summarize_clicked(self, widget):
        self.app.get_summary_suggestion()

    def _on_details_clicked(self, widget):
        self.app.get_details_suggestion()


    def append_text(self, text):
        end_iter = self.textbuffer.get_end_iter()
        self.textbuffer.insert(end_iter, text + '\n')
        # auto-scroll, only if the widget is realized
        parent = self.textview.get_parent()
        if parent:
            adj = parent.get_vadjustment()
            if adj:
                adj.set_value(adj.get_upper() - adj.get_page_size())

    def set_full_history(self, history_list):
        full_text = '\n'.join(history_list)
        self.textbuffer.set_text(full_text)
        # auto-scroll, only if the widget is realized
        parent = self.textview.get_parent()
        if parent:
            adj = parent.get_vadjustment()
            if adj:
                adj.set_value(adj.get_upper() - adj.get_page_size())

    def clear(self):
        self.textbuffer.set_text("")
