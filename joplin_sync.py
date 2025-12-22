# [file name]: joplin_sync.py
"""Joplin note synchronization functionality."""

import requests
from datetime import datetime


class JoplinSync:
    """Handles synchronization with Joplin notes app."""
    
    def __init__(self, application):
        """
        Initialize Joplin sync manager.
        
        Args:
            application: The main Application instance
        """
        self.app = application
        self.joplin_url = "http://localhost:41184"  # Default Joplin Web Clipper port
    
    def sync_analysis(self, analysis, meeting_folder, final_inconsistencies_note: str = ""):
        """
        Sync meeting analysis to Joplin.
        
        Args:
            analysis: The analysis text to sync
            meeting_folder: The meeting folder name
            final_inconsistencies_note: Any consistency check notes to append to the analysis.
        """
        if not self.app.joplin_sync_enabled:
            return
            
        print(" Joplin sync is enabled. Preparing to send note...")
        
        if not self.app.joplin_api_key:
            print("❌ Joplin sync failed: API key is not configured.")
            return
        
        if not meeting_folder:
            print("❌ Joplin sync failed: Meeting folder not set.")
            return
        
        try:
            # Get or create the Joplin folder
            joplin_folder_name = self.app.joplin_destination_folder if self.app.joplin_destination_folder else "Recass"
            folder_id = self._get_or_create_folder(joplin_folder_name)
            if not folder_id:
                # Error message is printed inside the helper method
                return
                
            # Extract timestamp from folder name like 'meeting-2025-12-11-00-50-12'
            folder_timestamp_str = meeting_folder.replace('meeting-', '')
            dt_obj = datetime.strptime(folder_timestamp_str, '%Y-%m-%d-%H-%M-%S')
            note_title = f"Meeting minutes {dt_obj.strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Append final inconsistency note if present
            full_analysis_body = analysis
            if final_inconsistencies_note:
                full_analysis_body += f"\n\n{final_inconsistencies_note}" # Add a couple newlines for separation

            # Note data
            note_data = {
                "title": note_title,
                "body": full_analysis_body,
                "parent_id": folder_id,
            }
            
            # Make the request
            print(f"  - Sending note titled '{note_title}' to Joplin folder '{joplin_folder_name}'...")
            response = requests.post(
                f"{self.joplin_url}/notes",
                params={"token": self.app.joplin_api_key},
                json=note_data
            )
            
            response.raise_for_status()  # Raise an exception for bad status codes
            print("✅ Note successfully synced to Joplin!")
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Joplin sync failed: An error occurred while communicating with the Joplin API: {e}")
        except Exception as e:
            print(f"❌ Joplin sync failed: An unexpected error occurred: {e}")
    
    def _get_or_create_folder(self, folder_name):
        """
        Get the ID of a Joplin folder, creating it if it doesn't exist.
        
        Args:
            folder_name: Name of the folder to find/create
            
        Returns:
            str: Folder ID or None if error
        """
        folders_endpoint = f"{self.joplin_url}/folders"
        page = 1
        
        try:
            # 1. List all folders to find the folder, handling pagination
            print(f"  - Searching for Joplin folder '{folder_name}'...")
            while True:
                response = requests.get(
                    folders_endpoint,
                    params={"token": self.app.joplin_api_key, "page": page}
                )
                response.raise_for_status()
                result = response.json()
                folders = result.get('items', [])
                
                for folder in folders:
                    if folder['title'] == folder_name:
                        print(f"  - Found Joplin folder '{folder_name}' with ID: {folder['id']}")
                        return folder['id']
                
                if not result.get('has_more', False):
                    break
                page += 1
            
            # 2. If not found, create it
            print(f"  - Joplin folder '{folder_name}' not found. Creating it...")
            create_response = requests.post(
                folders_endpoint,
                params={"token": self.app.joplin_api_key},
                json={"title": folder_name}
            )
            create_response.raise_for_status()
            new_folder = create_response.json()
            print(f"  - Created Joplin folder '{folder_name}' with ID: {new_folder['id']}")
            return new_folder['id']
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Joplin folder handling failed: An error occurred while communicating with the Joplin API: {e}")
            return None
        except Exception as e:
            print(f"❌ Joplin folder handling failed: An unexpected error occurred: {e}")
            return None