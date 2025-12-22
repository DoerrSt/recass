# [file name]: folder_manager.py
"""Folder management and indexing for recass."""

import threading
import time
from gi.repository import Gtk


class FolderManager:
    """Manages source folders and file indexing."""
    
    def __init__(self, application):
        """
        Initialize folder manager.
        
        Args:
            application: The main Application instance
        """
        self.app = application
        self.watcher_thread = None
        self.watcher_stop_event = None
    
    def on_add_folder_clicked(self, widget):
        """Handle Add Folder button click."""
        dialog = Gtk.FileChooserDialog(
            title="Please choose a folder",
            parent=self.app._window,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            "Select", Gtk.ResponseType.OK
        )
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            folder_path = dialog.get_filename()
            if folder_path and folder_path not in self.app.source_folders:
                # Add to UI
                label = Gtk.Label(label=folder_path)
                label.set_xalign(0)
                self.app.folders_listbox.add(label)
                self.app.folders_listbox.show_all()
                
                # Update settings
                self.app.source_folders.append(folder_path)
                from config import load_user_settings, save_user_settings
                settings = load_user_settings()
                settings['source_folders'] = self.app.source_folders
                save_user_settings(settings)
                print(f"Source folder added: {folder_path}")
                
                if self.app.folder_indexer:
                    # run in background thread to not block UI
                    threading.Thread(
                        target=self.app.folder_indexer.index_folder, 
                        args=(folder_path,), 
                        daemon=True
                    ).start()
        
        dialog.destroy()
    
    def on_remove_folder_clicked(self, widget):
        """Handle Remove folder button click."""
        selected_row = self.app.folders_listbox.get_selected_row()
        if selected_row:
            label = selected_row.get_child()
            folder_to_remove = label.get_label()
            self.app.folders_listbox.remove(selected_row)
            
            # Update settings
            if folder_to_remove in self.app.source_folders:
                self.app.source_folders.remove(folder_to_remove)
                from config import load_user_settings, save_user_settings
                settings = load_user_settings()
                settings['source_folders'] = self.app.source_folders
                save_user_settings(settings)
                print(f"Source folder removed: {folder_to_remove}")
                
                if self.app.folder_indexer:
                    self.app.folder_indexer.remove_folder_from_index(folder_to_remove)
    
    def start_folder_watcher(self):
        """Starts the background thread for folder watching if not already running."""
        if self.watcher_thread is None:
            self.watcher_stop_event = threading.Event()
            self.watcher_thread = threading.Thread(
                target=self._watcher_loop,
                args=(self.watcher_stop_event,),
                daemon=True
            )
            self.watcher_thread.start()
            print("Folder watcher started.")
    
    def stop_folder_watcher(self):
        """Stop the folder watcher thread."""
        if self.watcher_thread:
            self.watcher_stop_event.set()
            # The thread will time out from wait() and exit
    
    def _watcher_loop(self, stop_event):
        """Periodically checks source folders for file changes."""
        while not stop_event.is_set():
            print("Checking source folders for updates...")
            source_folders_copy = self.app.source_folders[:]  # work on a copy
            for folder in source_folders_copy:
                if self.app.folder_indexer:
                    self.app.folder_indexer.index_folder(folder)
            
            # Wait for 5 minutes or until stop event is set
            stop_event.wait(300)