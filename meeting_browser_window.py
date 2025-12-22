import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk
from datetime import datetime
import os
import threading
import torch

from audio_player import AudioPlayer, load_audio

class MeetingBrowserWindow:
    def __init__(self, app):
        self.app = app
        self._window = None
        self.search_entry = None
        self.meeting_list_box = None # For meeting cards
        self.filter_options = {}
        self.stack = None # To manage different views (list, protocol)

        self.player = None
        self.playback_thread = None
        self.playback_active = False
        self.current_audio_data = None
        self.current_samplerate = None
        self.playback_position = 0
        self.current_meeting_folder = None


    def create_or_show(self):
        if self._window:
            self._window.present()
            return

        self._window = Gtk.Window(title="Meeting Browser")
        self._window.set_default_size(1200, 800) # Adjusted for better viewing
        self._window.connect("delete-event", self._on_delete_event)

        # Main Grid for header, sidebar, and content
        main_grid = Gtk.Grid()
        self._window.add(main_grid)

        # Header Bar (Row 0)
        header_bar = self._create_header_bar()
        main_grid.attach(header_bar, 0, 0, 2, 1) # Spans 2 columns

        # Sidebar (Column 0, Row 1) - visible only in list view initially
        self.sidebar = self._create_sidebar()
        main_grid.attach(self.sidebar, 0, 1, 1, 1)

        # Gtk.Stack to switch between list view and protocol view
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)
        main_grid.attach(self.stack, 1, 1, 1, 1)

        # Meeting List View
        meeting_list_view = self._create_meeting_list_view()
        self.stack.add_named(meeting_list_view, "list_view")

        # Meeting Protocol View (initially empty, populated when a card is clicked)
        meeting_protocol_view = self._create_meeting_protocol_view()
        self.stack.add_named(meeting_protocol_view, "protocol_view")

        # Load initial meetings (placeholder for now)
        self._load_meetings()

        self._window.show_all()

    def _create_header_bar(self):
        header_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_bar.set_margin_top(10)
        header_bar.set_margin_bottom(10)
        header_bar.set_margin_left(10)
        header_bar.set_margin_right(10)

        # Logo Placeholder
        logo_label = Gtk.Label(label="<b>Recass</b>", use_markup=True)
        logo_label.set_halign(Gtk.Align.START)
        header_bar.pack_start(logo_label, False, False, 0)

        # Search Bar
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search Meetings...")
        self.search_entry.set_hexpand(True)
        self.search_entry.set_halign(Gtk.Align.END)
        self.search_entry.connect("search-changed", self._on_search_changed)
        header_bar.pack_end(self.search_entry, False, False, 0)

        return header_bar

    def _create_sidebar(self):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar.get_style_context().add_class("sidebar") # For potential CSS styling
        sidebar.set_size_request(250, -1) # Fixed width for sidebar
        sidebar.set_margin_left(10)
        sidebar.set_margin_right(10)
        sidebar.set_margin_bottom(10)
        sidebar.set_halign(Gtk.Align.FILL)
        sidebar.set_valign(Gtk.Align.FILL)

        # Filter Options Title
        filter_title = Gtk.Label(label="<b>Filter Options</b>", use_markup=True)
        filter_title.set_halign(Gtk.Align.START)
        sidebar.pack_start(filter_title, False, False, 0)

        # Status Filter
        status_label = Gtk.Label(label="Status")
        status_label.set_halign(Gtk.Align.START)
        sidebar.pack_start(status_label, False, False, 0)

        self.status_filter = Gtk.ComboBoxText()
        self.status_filter.append_text("All")
        self.status_filter.append_text("Recorded")
        self.status_filter.append_text("Analyzed")
        self.status_filter.set_active(0)
        self.status_filter.connect("changed", self._on_filter_changed)
        sidebar.pack_start(self.status_filter, False, False, 0)

        # Date Range Filter
        start_date_label = Gtk.Label(label="Start Date")
        start_date_label.set_halign(Gtk.Align.START)
        sidebar.pack_start(start_date_label, False, False, 0)
        self.start_date_calendar = Gtk.Calendar()
        self.start_date_calendar.connect("day-selected", self._on_filter_changed)
        sidebar.pack_start(self.start_date_calendar, False, False, 0)

        end_date_label = Gtk.Label(label="End Date")
        end_date_label.set_halign(Gtk.Align.START)
        sidebar.pack_start(end_date_label, False, False, 0)
        self.end_date_calendar = Gtk.Calendar()
        self.end_date_calendar.connect("day-selected", self._on_filter_changed)
        sidebar.pack_start(self.end_date_calendar, False, False, 0)

        # Topic Filter
        topic_label = Gtk.Label(label="Topic")
        topic_label.set_halign(Gtk.Align.START)
        sidebar.pack_start(topic_label, False, False, 0)
        self.topic_filter = Gtk.SearchEntry()
        self.topic_filter.connect("search-changed", self._on_filter_changed)
        sidebar.pack_start(self.topic_filter, False, False, 0)

        # Attendees Filter
        attendees_label = Gtk.Label(label="Attendees")
        attendees_label.set_halign(Gtk.Align.START)
        sidebar.pack_start(attendees_label, False, False, 0)
        self.attendees_filter = Gtk.SearchEntry()
        self.attendees_filter.connect("search-changed", self._on_filter_changed)
        sidebar.pack_start(self.attendees_filter, False, False, 0)

        # Placeholder for other filters
        sidebar.pack_start(Gtk.Label(label="Media Type Filter (Coming Soon)"), False, False, 0)

        clear_filters_btn = Gtk.Button(label="Clear Filters")
        clear_filters_btn.connect("clicked", self._on_clear_filters_clicked)
        sidebar.pack_start(clear_filters_btn, False, False, 0)

        return sidebar

    def _create_meeting_list_view(self):
        main_content_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_content_vbox.set_margin_right(10)
        main_content_vbox.set_margin_bottom(10)
        main_content_vbox.set_halign(Gtk.Align.FILL)
        main_content_vbox.set_valign(Gtk.Align.FILL)

        # Page Title
        page_title = Gtk.Label(label="<big><b>Meeting Protocols</b></big>", use_markup=True)
        page_title.set_halign(Gtk.Align.START)
        main_content_vbox.pack_start(page_title, False, False, 0)

        # Meeting Cards (Placeholder)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        main_content_vbox.pack_start(scrolled_window, True, True, 0)

        self.meeting_list_box = Gtk.ListBox()
        self.meeting_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.meeting_list_box.set_css_name("meeting-cards-list") # For potential CSS styling
        scrolled_window.add(self.meeting_list_box)

        # Pagination (Placeholder)
        pagination_label = Gtk.Label(label="Pagination: 1 2 3 ... Last (Coming Soon)")
        pagination_label.set_halign(Gtk.Align.CENTER)
        main_content_vbox.pack_end(pagination_label, False, False, 0)

        return main_content_vbox

    def _create_meeting_protocol_view(self):
        protocol_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        protocol_vbox.set_margin_left(10)
        protocol_vbox.set_margin_right(10)
        protocol_vbox.set_margin_top(10)
        protocol_vbox.set_margin_bottom(10)

        # Back Button and Title
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        back_button = Gtk.Button(label="< Back")
        back_button.connect("clicked", self._on_back_to_list_clicked)
        header_box.pack_start(back_button, False, False, 0)

        self.protocol_title_label = Gtk.Label(label="<big><b>Meeting Title</b></big>", use_markup=True)
        self.protocol_title_label.set_halign(Gtk.Align.START)
        self.protocol_title_label.set_hexpand(True)
        header_box.pack_start(self.protocol_title_label, True, True, 0)
        
        self.reanalyze_button = Gtk.Button(label="Re-analyze")
        self.reanalyze_button.connect("clicked", self._on_reanalyze_clicked)
        header_box.pack_end(self.reanalyze_button, False, False, 0)

        protocol_vbox.pack_start(header_box, False, False, 0)

        # Breadcrumb Navigation
        self.breadcrumb_label = Gtk.Label(label="Home > Meeting Protocols > Meeting Title")
        self.breadcrumb_label.set_halign(Gtk.Align.START)
        protocol_vbox.pack_start(self.breadcrumb_label, False, False, 0)

        # Meeting Details (Attendees, Protocol Text)
        details_expander = Gtk.Expander.new("Meeting Details")
        details_content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        self.attendees_label = Gtk.Label(label="Attendees: John, Jane, Peter")
        self.attendees_label.set_halign(Gtk.Align.START)
        details_content_box.pack_start(self.attendees_label, False, False, 0)

        protocol_scrolled_window = Gtk.ScrolledWindow()
        protocol_scrolled_window.set_hexpand(True)
        protocol_scrolled_window.set_vexpand(True)
        
        self.protocol_text_view = Gtk.TextView()
        self.protocol_text_view.set_editable(False)
        self.protocol_text_view.set_cursor_visible(False)
        self.protocol_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        
        protocol_scrolled_window.add(self.protocol_text_view)
        details_content_box.pack_start(protocol_scrolled_window, True, True, 0)
        details_expander.add(details_content_box)
        protocol_vbox.pack_start(details_expander, True, True, 0)

        # Media Section (Audio Player, Screenshot Gallery, Download Buttons)
        media_expander = Gtk.Expander.new("Media")
        media_content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        
        # Audio Player
        audio_player_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.play_pause_button = Gtk.Button(label="▶")
        self.play_pause_button.connect("clicked", self._on_play_pause_clicked)
        audio_player_box.pack_start(self.play_pause_button, False, False, 0)

        self.playback_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.playback_slider.set_hexpand(True)
        self.playback_slider.connect("change-value", self._on_slider_changed)
        audio_player_box.pack_start(self.playback_slider, True, True, 0)
        media_content_box.pack_start(audio_player_box, False, False, 0)

        # Screenshot Gallery
        screenshot_gallery_scrolled_window = Gtk.ScrolledWindow()
        screenshot_gallery_scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        screenshot_gallery_scrolled_window.set_min_content_height(200)
        self.screenshot_flowbox = Gtk.FlowBox()
        self.screenshot_flowbox.set_valign(Gtk.Align.START)
        self.screenshot_flowbox.set_max_children_per_line(5)
        self.screenshot_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        screenshot_gallery_scrolled_window.add(self.screenshot_flowbox)
        media_content_box.pack_start(screenshot_gallery_scrolled_window, True, True, 0)
        
        download_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        download_audio_btn = Gtk.Button(label="Download Audio")
        download_screenshots_btn = Gtk.Button(label="Download Screenshots (ZIP)")
        download_button_box.pack_start(download_audio_btn, False, False, 0)
        download_button_box.pack_start(download_screenshots_btn, False, False, 0)
        media_content_box.pack_start(download_button_box, False, False, 0)
        
        media_expander.add(media_content_box)
        protocol_vbox.pack_start(media_expander, False, False, 0)

        return protocol_vbox

    def _load_meetings(self, meetings=None):
        # Clear existing cards
        for child in self.meeting_list_box.get_children():
            self.meeting_list_box.remove(child)

        if meetings is None:
            meetings = self.app.db.get_all_meetings()
        
        for meeting in meetings:
            self._add_meeting_card(meeting)
        self.meeting_list_box.show_all()

    def _add_meeting_card(self, meeting):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        card.get_style_context().add_class("meeting-card") # For potential CSS styling
        card.set_margin_bottom(10)
        card.set_margin_right(5) # For grid layout spacing
        card.set_margin_left(5)
        card.set_size_request(250, 150) # Fixed size for cards
        card.set_halign(Gtk.Align.FILL)
        card.set_valign(Gtk.Align.FILL)

        # Format created_at to a more readable date
        created_at_dt = datetime.fromisoformat(meeting['created_at'])
        formatted_date = created_at_dt.strftime("%b %d, %Y")

        date_label = Gtk.Label(label=f"<b>{formatted_date}</b>", use_markup=True)
        date_label.set_halign(Gtk.Align.START)
        card.pack_start(date_label, False, False, 0)

        title_label = Gtk.Label(label=f"<b>{meeting['title'] if meeting['title'] else meeting['folder_name']}</b>", use_markup=True)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_line_wrap(True)
        card.pack_start(title_label, False, False, 0)

        attendees_text = meeting['attendees'] if meeting['attendees'] else "N/A"
        attendees_label = Gtk.Label(label=f"Attendees: {attendees_text}")
        attendees_label.set_halign(Gtk.Align.START)
        card.pack_start(attendees_label, False, False, 0)

        status_text = meeting['status'] if meeting['status'] else "Unknown"
        status_label = Gtk.Label(label=f"Status: {status_text}")
        status_label.set_halign(Gtk.Align.START)
        card.pack_start(status_label, False, False, 0)

        # Placeholder for media summary, as it's not directly in DB yet
        media_label = Gtk.Label(label="Media: Audio & Screenshots")
        media_label.set_halign(Gtk.Align.START)
        card.pack_start(media_label, False, False, 0)

        view_button = Gtk.Button(label="View Protocol")
        view_button.get_style_context().add_class("accent-button") # For potential CSS styling
        view_button.set_halign(Gtk.Align.END)
        view_button.connect("clicked", self._show_meeting_protocol, meeting)
        card.pack_end(view_button, False, False, 0)

        row = Gtk.ListBoxRow()
        row.add(card)
        self.meeting_list_box.add(row)

    def _show_meeting_protocol(self, widget, meeting):
        self.current_meeting_folder = meeting['folder_name']
        self.protocol_title_label.set_label(f"<big><b>{meeting['title'] if meeting['title'] else meeting['folder_name']}</b></big>")
        self.breadcrumb_label.set_label(f"Home > Meeting Protocols > {meeting['title'] if meeting['title'] else meeting['folder_name']}")
        
        attendees_text = meeting['attendees'] if meeting['attendees'] else "N/A"
        self.attendees_label.set_label(f"Attendees: {attendees_text}")
        
        # Display transcript and analysis
        transcript_text = meeting['transcript'] if meeting['transcript'] else "No transcript available."
        analysis_text = meeting['analysis'] if meeting['analysis'] else "No analysis available."
        
        full_protocol_text = f"--- Transcript ---\n{transcript_text}\n\n--- Analysis ---\n{analysis_text}"
        self.protocol_text_view.get_buffer().set_text(full_protocol_text)
        
        # Load audio data
        try:
            folder_name = meeting['folder_name']
            now_str = folder_name.replace("meeting-", "")
            audio_file = os.path.join(folder_name, f"meeting-{now_str}-mixed.mp3")
            if os.path.exists(audio_file):
                self.current_audio_data, self.current_samplerate = load_audio(audio_file)
                self.playback_slider.set_range(0, len(self.current_audio_data) / self.current_samplerate)
                self.play_pause_button.set_sensitive(True)
            else:
                self.current_audio_data = None
                self.play_pause_button.set_sensitive(False)
        except Exception as e:
            print(f"Error loading audio: {e}")
            self.current_audio_data = None
            self.play_pause_button.set_sensitive(False)

        # Load screenshots
        for child in self.screenshot_flowbox.get_children():
            self.screenshot_flowbox.remove(child)
        
        try:
            folder_name = meeting['folder_name']
            screenshot_files = [f for f in os.listdir(folder_name) if f.endswith(".png")]
            for screenshot_file in screenshot_files:
                filepath = os.path.join(folder_name, screenshot_file)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filepath, 150, 100)
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                button = Gtk.Button()
                button.set_image(image)
                button.connect("clicked", self._on_screenshot_clicked, filepath)
                self.screenshot_flowbox.add(button)
        except Exception as e:
            print(f"Error loading screenshots: {e}")
        
        self.screenshot_flowbox.show_all()
        self.stack.set_visible_child_name("protocol_view")
        self.sidebar.hide() # Hide sidebar in protocol view

    def _on_reanalyze_clicked(self, widget):
        if self.current_meeting_folder:
            print(f"Re-analyzing meeting: {self.current_meeting_folder}")
            self.reanalyze_button.set_sensitive(False)
            self.reanalyze_button.set_label("Re-analyzing...")
            self.app.reprocess_meeting(self.current_meeting_folder, self._on_reanalyze_finished)

    def _on_reanalyze_finished(self):
        def re_enable_button():
            self.reanalyze_button.set_sensitive(True)
            self.reanalyze_button.set_label("Re-analyze")
            meeting = self.app.db.get_meeting_by_folder(self.current_meeting_folder)
            if meeting:
                self._show_meeting_protocol(None, meeting)
        GLib.idle_add(re_enable_button)


    def _on_screenshot_clicked(self, widget, filepath):
        win = Gtk.Window()
        win.set_title(os.path.basename(filepath))
        
        # Set a reasonable default size
        screen = Gdk.Screen.get_default()
        monitor_num = screen.get_primary_monitor()
        geometry = screen.get_monitor_geometry(monitor_num)
        win.set_default_size(int(geometry.width * 0.8), int(geometry.height * 0.8))

        scrolled_win = Gtk.ScrolledWindow()
        scrolled_win.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        win.add(scrolled_win)

        image = Gtk.Image()
        scrolled_win.add(image)

        original_pixbuf = GdkPixbuf.Pixbuf.new_from_file(filepath)

        def on_size_allocate(widget, allocation):
            scaled_pixbuf = original_pixbuf.scale_simple(
                allocation.width,
                allocation.height,
                GdkPixbuf.InterpType.BILINEAR
            )
            image.set_from_pixbuf(scaled_pixbuf)

        image.connect("size-allocate", on_size_allocate)

        win.show_all()

    def _on_back_to_list_clicked(self, button):
        self._stop_playback()
        self.stack.set_visible_child_name("list_view")
        self.sidebar.show_all() # Show sidebar again in list view

    def _on_play_pause_clicked(self, button):
        if self.playback_active:
            self._stop_playback()
        else:
            self._start_playback()

    def _on_slider_changed(self, scale, scroll_type, value):
        if self.current_audio_data is not None:
            self.playback_position = int(value * self.current_samplerate)

    def _start_playback(self):
        if self.current_audio_data is None:
            return
            
        self.playback_active = True
        self.play_pause_button.set_label("❚❚")
        self.player = AudioPlayer(samplerate=self.current_samplerate)
        self.playback_thread = threading.Thread(target=self._playback_thread_func)
        self.playback_thread.daemon = True
        self.playback_thread.start()

    def _stop_playback(self):
        self.playback_active = False
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join()
        if self.player:
            self.player.close()
            self.player = None
        self.play_pause_button.set_label("▶")

    def _playback_thread_func(self):
        chunk_size = 1024
        while self.playback_active and self.playback_position < len(self.current_audio_data):
            end_pos = self.playback_position + chunk_size
            chunk = self.current_audio_data[self.playback_position:end_pos]
            self.player.add_audio(chunk)
            self.playback_position = end_pos
            GLib.idle_add(self._update_slider_position)
        
        # When playback finishes naturally
        GLib.idle_add(self._stop_playback)

    def _update_slider_position(self):
        if self.current_audio_data is not None:
            pos_in_seconds = self.playback_position / self.current_samplerate
            self.playback_slider.set_value(pos_in_seconds)

    def _on_search_changed(self, search_entry):
        query = search_entry.get_text().strip()
        if query:
            meetings = self.app.db.search_meetings(query)
            self._load_meetings(meetings)
        else:
            self._load_meetings()

    def _on_filter_changed(self, widget):
        status = self.status_filter.get_active_text()
        
        start_date_tuple = self.start_date_calendar.get_date()
        start_date_iso = None
        if start_date_tuple[2] != 0:
            start_date = datetime(start_date_tuple[0], start_date_tuple[1] + 1, start_date_tuple[2])
            start_date_iso = start_date.isoformat()

        end_date_tuple = self.end_date_calendar.get_date()
        end_date_iso = None
        if end_date_tuple[2] != 0:
            end_date = datetime(end_date_tuple[0], end_date_tuple[1] + 1, end_date_tuple[2], 23, 59, 59)
            end_date_iso = end_date.isoformat()
        
        topic = self.topic_filter.get_text().strip()
        attendees = self.attendees_filter.get_text().strip()

        meetings = self.app.db.filter_meetings(
            status=status, 
            start_date=start_date_iso, 
            end_date=end_date_iso,
            topic=topic,
            attendees=attendees
        )
        self._load_meetings(meetings)

    def _on_clear_filters_clicked(self, button):
        self.status_filter.set_active(0)
        self.start_date_calendar.select_day(1)
        self.start_date_calendar.select_day(0)
        self.end_date_calendar.select_day(1)
        self.end_date_calendar.select_day(0)
        self.topic_filter.set_text("")
        self.attendees_filter.set_text("")
        self._load_meetings()

    def _on_delete_event(self, widget, event):
        self._stop_playback()
        self._window.hide()
        return True # Indicate that the event has been handled and the window should not be destroyed
    
    def __del__(self):
        self._stop_playback()