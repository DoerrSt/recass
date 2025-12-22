import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from datetime import datetime

class ChatBrowserWindow:
    def __init__(self, app):
        self.app = app
        self._window = None
        self.search_entry = None
        self.chat_list_box = None
        self.stack = None
        self.protocol_text_view = None
        self.all_chats = []

    def create_or_show(self):
        if self._window:
            self._window.present()
            return

        self._window = Gtk.Window(title="Chat Browser")
        self._window.set_default_size(1000, 700)
        self._window.connect("delete-event", self._on_delete_event)

        main_grid = Gtk.Grid()
        self._window.add(main_grid)

        header_bar = self._create_header_bar()
        main_grid.attach(header_bar, 0, 0, 1, 1)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        main_grid.attach(self.stack, 0, 1, 1, 1)

        chat_list_view = self._create_chat_list_view()
        self.stack.add_named(chat_list_view, "list_view")

        chat_protocol_view = self._create_chat_protocol_view()
        self.stack.add_named(chat_protocol_view, "protocol_view")

        self._load_chats()

        self._window.show_all()

    def _create_header_bar(self):
        header_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_bar.set_margin_top(10)
        header_bar.set_margin_bottom(10)
        header_bar.set_margin_left(10)
        header_bar.set_margin_right(10)

        logo_label = Gtk.Label(label="<b>Recass Chats</b>", use_markup=True)
        header_bar.pack_start(logo_label, False, False, 0)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search Chats...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        header_bar.pack_start(self.search_entry, True, True, 10)

        return header_bar

    def _create_chat_list_view(self):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_vbox.set_margin_right(10)
        main_vbox.set_margin_left(10)
        main_vbox.set_margin_bottom(10)

        page_title = Gtk.Label(label="<big><b>Chat Protocols</b></big>", use_markup=True)
        page_title.set_halign(Gtk.Align.START)
        main_vbox.pack_start(page_title, False, False, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        main_vbox.pack_start(scrolled_window, True, True, 0)

        self.chat_list_box = Gtk.ListBox()
        self.chat_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled_window.add(self.chat_list_box)

        return main_vbox

    def _create_chat_protocol_view(self):
        protocol_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        protocol_vbox.set_margin_left(10)
        protocol_vbox.set_margin_right(10)
        protocol_vbox.set_margin_top(10)
        protocol_vbox.set_margin_bottom(10)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        back_button = Gtk.Button(label="< Back to List")
        back_button.connect("clicked", self._on_back_to_list_clicked)
        header_box.pack_start(back_button, False, False, 0)

        self.protocol_title_label = Gtk.Label(label="", use_markup=True)
        self.protocol_title_label.set_halign(Gtk.Align.START)
        header_box.pack_start(self.protocol_title_label, True, True, 0)
        protocol_vbox.pack_start(header_box, False, False, 0)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        protocol_vbox.pack_start(scrolled_window, True, True, 0)

        self.protocol_text_view = Gtk.TextView()
        self.protocol_text_view.set_editable(False)
        self.protocol_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled_window.add(self.protocol_text_view)
        
        # Add tags for styling
        tag_table = self.protocol_text_view.get_buffer().get_tag_table()
        tag_user = Gtk.TextTag.new("user")
        tag_user.set_property("weight", 700) # Bold
        tag_table.add(tag_user)
        
        tag_assistant = Gtk.TextTag.new("assistant")
        tag_assistant.set_property("foreground", "blue")
        tag_table.add(tag_assistant)
        
        tag_system = Gtk.TextTag.new("system")
        tag_system.set_property("style", "italic")
        tag_system.set_property("foreground", "gray")
        tag_table.add(tag_system)

        return protocol_vbox

    def _load_chats(self, filter_text=None):
        for child in self.chat_list_box.get_children():
            self.chat_list_box.remove(child)

        all_chats_from_db = self.app.db.get_chat_sessions()
        
        chats_to_display = []
        if not filter_text:
            chats_to_display = all_chats_from_db
        else:
            filter_text_lower = filter_text.lower()
            for chat in all_chats_from_db:
                # Check if filter_text is in chat title
                if filter_text_lower in chat['title'].lower():
                    chats_to_display.append(chat)
                    continue # Move to next chat if title matches

                # Check if filter_text is in any message content
                messages = self.app.db.get_messages_for_session(chat['id'])
                for message in messages:
                    if filter_text_lower in message['content'].lower():
                        chats_to_display.append(chat)
                        break # Found a match, move to next chat
        
        # Sort chats by creation date (most recent first) after filtering
        chats_to_display.sort(key=lambda c: c['created_at'], reverse=True)

        for chat in chats_to_display:
            self._add_chat_card(chat)
        self.chat_list_box.show_all()

    def _add_chat_card(self, chat):
        card = Gtk.Button()
        card.set_relief(Gtk.ReliefStyle.NONE)
        card.connect("clicked", self._show_chat_protocol, chat)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        card.add(hbox)

        try:
            created_at_dt = datetime.fromisoformat(chat['created_at'])
            formatted_date = created_at_dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            formatted_date = "Unknown Date"
            
        date_label = Gtk.Label(label=f"{formatted_date}", use_markup=True)
        date_label.set_halign(Gtk.Align.START)
        
        title_label = Gtk.Label(label=f"<b>{chat['title']}</b>", use_markup=True)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_line_wrap(True)

        hbox.pack_start(date_label, False, False, 0)
        hbox.pack_start(title_label, True, True, 0)
        
        row = Gtk.ListBoxRow()
        row.add(card)
        self.chat_list_box.add(row)

    def _show_chat_protocol(self, widget, chat):
        self.protocol_title_label.set_label(f"<big><b>{chat['title']}</b></big>")
        
        messages = self.app.db.get_messages_for_session(chat['id'])
        
        buffer = self.protocol_text_view.get_buffer()
        buffer.set_text("")
        
        for msg in messages:
            try:
                created_at_dt = datetime.fromisoformat(msg['created_at'])
                timestamp = created_at_dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                timestamp = "Unknown Time"
            
            role = msg.get('role', 'unknown').lower()
            
            # Insert timestamp
            buffer.insert_with_tags_by_name(buffer.get_end_iter(), f"[{timestamp}] ", "system")
            
            # Insert role and content
            if role == 'user':
                buffer.insert_with_tags_by_name(buffer.get_end_iter(), "User: ", "user")
            elif role == 'assistant':
                buffer.insert_with_tags_by_name(buffer.get_end_iter(), "Assistant: ", "assistant")
            
            buffer.insert(buffer.get_end_iter(), msg.get('content', '') + "\n\n")

        self.stack.set_visible_child_name("protocol_view")

    def _on_back_to_list_clicked(self, button):
        self.stack.set_visible_child_name("list_view")

    def _on_search_changed(self, search_entry):
        query = search_entry.get_text().strip()
        self._load_chats(filter_text=query)

    def _on_delete_event(self, widget, event):
        self._window.hide()
        return True
