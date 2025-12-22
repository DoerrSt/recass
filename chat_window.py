# [file name]: chat_window.py
"""Chat window functionality for recass."""

import os
import threading
from datetime import datetime
from gi.repository import Gtk
from config import load_user_settings
from ollama_analyzer import OllamaAnalyzer


class ChatWindow:
    """Manages the chat window and Ollama interactions."""
    
    def __init__(self, application):
        """
        Initialize the chat window manager.
        
        Args:
            application: The main Application instance
        """
        self.app = application
        self.window = None
        self.chat_view = None
        self.chat_buffer = None
        self.chat_entry = None
        self.ollama_analyzer = None
    
    def create_or_show(self):
        """Create or present the chat GTK window."""
        if self.window:
            try:
                self.window.present()
                return
            except Exception:
                self.window = None
        
        # If no active session, create one
        if not self.app.chat_session_id:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.app.chat_session_id = self.app.db.create_chat_session(
                title=f"Chat Session - {now_str}"
            )
            print(f"📝 New chat session created: {self.app.chat_session_id}")
        
        self.window = Gtk.Window(title="recass Chat")
        self.window.set_default_size(600, 400)
        self.window.connect("delete-event", self._on_close)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        self.window.add(vbox)
        
        # Conversation display
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)
        self.chat_view = Gtk.TextView()
        self.chat_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.chat_view.set_editable(False)
        self.chat_buffer = self.chat_view.get_buffer()
        scrolled.add(self.chat_view)
        vbox.pack_start(scrolled, True, True, 0)
        
        # Input area
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.chat_entry = Gtk.Entry()
        self.chat_entry.set_placeholder_text("Type a message and press Send")
        self.chat_entry.connect("activate", self._on_send_clicked)
        
        upload_btn = Gtk.Button(label="Upload")
        upload_btn.connect("clicked", self._on_upload_clicked)
        
        send_btn = Gtk.Button(label="Send")
        send_btn.connect("clicked", self._on_send_clicked)
        
        hbox.pack_start(self.chat_entry, True, True, 0)
        hbox.pack_start(upload_btn, False, False, 0)
        hbox.pack_start(send_btn, False, False, 0)
        vbox.pack_start(hbox, False, False, 0)
        
        self.window.show_all()
    
    def _on_close(self, widget, event):
        """Handle the chat window closing event."""
        widget.hide()
        # Clear the chat buffer content
        if self.chat_buffer:
            self.chat_buffer.set_text("")
        # Reset window and chat_session_id to force new creation
        self.window = None
        self.app.chat_session_id = None
        print("Chat window closed, content cleared, and session reset.")
        return True
    
    def append_text(self, sender, text):
        """Append a line to the chat view in the GTK main thread."""
        try:
            if not self.chat_buffer:
                return
            end_iter = self.chat_buffer.get_end_iter()
            self.chat_buffer.insert(end_iter, f"{sender}: {text}\n\n")
            # Scroll to end
            mark = self.chat_buffer.create_mark(None, self.chat_buffer.get_end_iter(), False)
            self.chat_view.scroll_to_mark(mark, 0.0, True, 0.0, 1.0)
        except Exception:
            pass
    
    def _on_upload_clicked(self, widget):
        """Handle Upload button: show file chooser and add doc to Chroma."""
        from gi.repository import Gtk
        dialog = Gtk.FileChooserDialog(
            title="Please choose files to upload for context",
            parent=self.window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        dialog.set_select_multiple(True)
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filepaths = dialog.get_filenames()
            print(f"Files selected for upload: {filepaths}")
            for filepath in filepaths:
                # Run the processing in a background thread for each file
                thread = threading.Thread(
                    target=self.app._process_uploaded_file, 
                    args=(filepath,), 
                    daemon=True
                )
                thread.start()
        
        dialog.destroy()
    
    def _on_send_clicked(self, widget):
        """Handle Send button: spawn thread to query Ollama with Chroma context."""
        text = None
        try:
            text = self.chat_entry.get_text().strip()
        except Exception:
            return
        
        if not text:
            return
        
        # append user text locally and save to DB
        from gi.repository import GLib
        GLib.idle_add(self.append_text, "You", text)
        if self.app.chat_session_id:
            self.app.db.add_message(self.app.chat_session_id, 'user', text)
        
        try:
            self.chat_entry.set_text("")
        except Exception:
            pass
        
        # Retrieve context from ChromaDB
        context_docs = self.app._get_chroma_context(text, n_results=3)
        
        # Run Ollama query in background
        def worker(msg, ctx, session_id):
            try:
                analyzer = self.get_analyzer()
                result = analyzer.chat(msg, context_docs=ctx)
                if result.get('success'):
                    response_text = result.get('response', '')
                    GLib.idle_add(self.append_text, "Ollama", response_text)
                    if session_id:
                        self.app.db.add_message(session_id, 'assistant', response_text)
                else:
                    error_text = f"Error: {result.get('error')}"
                    GLib.idle_add(self.append_text, "Ollama", error_text)
            except Exception as e:
                GLib.idle_add(self.append_text, "Ollama", f"Exception: {e}")
        
        t = threading.Thread(
            target=worker, 
            args=(text, context_docs, self.app.chat_session_id), 
            daemon=True
        )
        t.start()
    
    def get_analyzer(self):
        """Get or create Ollama analyzer instance."""
        if not self.ollama_analyzer:
            try:
                settings = load_user_settings()
                base_url = settings.get('ollama_url', 'http://localhost:11434')
                model_name = settings.get('ollama_model_name', 'llama3')
            except Exception:
                base_url = 'http://localhost:11434'
                model_name = 'llama3'
            self.ollama_analyzer = OllamaAnalyzer(base_url=base_url, model_name=model_name)
        return self.ollama_analyzer