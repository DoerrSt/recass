import sqlite3
import uuid
from datetime import datetime
import json

class Database:
    """Handles all database operations for chat sessions and messages."""

    def __init__(self, db_file="chats.db"):
        """
        Initializes the database connection.

        Args:
            db_file (str): The name of the SQLite database file.
        """
        self.db_file = db_file
        self.conn = None
        try:
            self.conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            # Enable foreign key support
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.create_tables()
        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def create_tables(self):
        """Creates the necessary tables if they don't exist."""
        try:
            cursor = self.conn.cursor()

            # Schema version table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    id INTEGER PRIMARY KEY,
                    version INTEGER NOT NULL
                )
            """)

            # Check and set schema version
            cursor.execute("SELECT version FROM schema_version WHERE id = 1")
            result = cursor.fetchone()
            if result is None:
                cursor.execute("INSERT INTO schema_version (id, version) VALUES (1, 3)") # Bump version for new schema
            
            # Update to version 2 (already handled)
            if result and result['version'] < 2:
                # Indexed files table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS indexed_files (
                        filepath TEXT PRIMARY KEY,
                        size INTEGER NOT NULL,
                        modified_time REAL NOT NULL,
                        file_hash TEXT NOT NULL,
                        chunk_ids TEXT
                    )
                """)
                cursor.execute("UPDATE schema_version SET version = 2 WHERE id = 1")

            # Update to version 3 (for meetings table)
            if result and result['version'] < 3:
                # Meetings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS meetings (
                        id TEXT PRIMARY KEY,
                        folder_name TEXT NOT NULL UNIQUE,
                        title TEXT,
                        created_at TEXT NOT NULL,
                        duration INTEGER,
                        attendees TEXT,
                        status TEXT,
                        transcript TEXT,
                        analysis TEXT
                    )
                """)
                cursor.execute("UPDATE schema_version SET version = 3 WHERE id = 1")

            # Chats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chats (id) ON DELETE CASCADE
                )
            """)
            
            # Indexed files table (for fresh dbs and previous version)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS indexed_files (
                    filepath TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    modified_time REAL NOT NULL,
                    file_hash TEXT NOT NULL,
                    chunk_ids TEXT
                )
            """)

            self.conn.commit()
            print("Database tables checked/created successfully.")
        except sqlite3.Error as e:
            print(f"Error creating tables: {e}")

    def get_indexed_file(self, filepath: str):
        """Retrieves indexing information for a single file."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM indexed_files WHERE filepath = ?", (filepath,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Error getting indexed file {filepath}: {e}")
            return None
            
    def update_indexed_file(self, filepath: str, size: int, modified_time: float, file_hash: str, chunk_ids: list):
        """Inserts or updates the indexing information for a file."""
        try:
            cursor = self.conn.cursor()
            chunk_ids_json = json.dumps(chunk_ids)
            cursor.execute("""
                INSERT OR REPLACE INTO indexed_files (filepath, size, modified_time, file_hash, chunk_ids)
                VALUES (?, ?, ?, ?, ?)
            """, (filepath, size, modified_time, file_hash, chunk_ids_json))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating indexed file {filepath}: {e}")

    def delete_indexed_file(self, filepath: str):
        """Deletes indexing information for a single file."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM indexed_files WHERE filepath = ?", (filepath,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error deleting indexed file {filepath}: {e}")
            
    def get_indexed_files_by_folder(self, folder_path: str):
        """Retrieves all indexed files within a given folder path."""
        try:
            cursor = self.conn.cursor()
            # Use LIKE to find all files starting with the folder path
            cursor.execute("SELECT * FROM indexed_files WHERE filepath LIKE ?", (folder_path + '%',))
            return {row['filepath']: dict(row) for row in cursor.fetchall()}
        except sqlite3.Error as e:
            print(f"Error getting indexed files for folder {folder_path}: {e}")
            return {}

    def create_chat_session(self, title: str) -> str:
        """
        Creates a new chat session.

        Args:
            title (str): The title of the chat session.

        Returns:
            str: The ID of the newly created chat session.
        """
        session_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO chats (id, title, created_at) VALUES (?, ?, ?)",
                (session_id, title, created_at)
            )
            self.conn.commit()
            return session_id
        except sqlite3.Error as e:
            print(f"Error creating chat session: {e}")
            return None

    def add_message(self, session_id: str, role: str, content: str) -> str:
        """
        Adds a message to a specific chat session.

        Args:
            session_id (str): The ID of the chat session.
            role (str): The role of the message sender (e.g., 'user', 'assistant').
            content (str): The content of the message.

        Returns:
            str: The ID of the newly created message.
        """
        message_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (message_id, session_id, role, content, created_at)
            )
            self.conn.commit()
            return message_id
        except sqlite3.Error as e:
            print(f"Error adding message: {e}")
            return None

    def get_chat_sessions(self):
        """
        Retrieves all chat sessions, ordered by creation date.

        Returns:
            list: A list of dictionaries representing chat sessions.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM chats ORDER BY created_at DESC")
            sessions = [dict(row) for row in cursor.fetchall()]
            return sessions
        except sqlite3.Error as e:
            print(f"Error getting chat sessions: {e}")
            return []

    def get_chat_session(self, session_id: str):
        """
        Retrieves a single chat session by its ID.

        Args:
            session_id (str): The ID of the chat session.

        Returns:
            dict: A dictionary representing the chat session, or None if not found.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM chats WHERE id = ?", (session_id,))
            session = cursor.fetchone()
            return dict(session) if session else None
        except sqlite3.Error as e:
            print(f"Error getting chat session: {e}")
            return None

    def get_messages_for_session(self, session_id: str):
        """
        Retrieves all messages for a given session, ordered by creation date.

        Args:
            session_id (str): The ID of the chat session.

        Returns:
            list: A list of dictionaries representing messages.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,)
            )
            messages = [dict(row) for row in cursor.fetchall()]
            return messages
        except sqlite3.Error as e:
            print(f"Error getting messages for session: {e}")
            return []

    def create_meeting(self, folder_name: str, title: str = None, duration: int = None, attendees: str = None, status: str = "Recorded", transcript: str = None, analysis: str = None) -> str:
        """
        Creates a new meeting record.

        Args:
            folder_name (str): The name of the folder where meeting data is stored.
            title (str): The title of the meeting. Defaults to folder_name if None.
            duration (int): Duration of the meeting in seconds.
            attendees (str): Comma-separated string of attendees.
            status (str): Current status of the meeting (e.g., "Recorded", "Analyzed").
            transcript (str): The full transcript text of the meeting.
            analysis (str): The AI analysis summary of the meeting.

        Returns:
            str: The ID of the newly created meeting.
        """
        meeting_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        if title is None:
            title = folder_name
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO meetings (id, folder_name, title, created_at, duration, attendees, status, transcript, analysis)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (meeting_id, folder_name, title, created_at, duration, attendees, status, transcript, analysis)
            )
            self.conn.commit()
            return meeting_id
        except sqlite3.Error as e:
            print(f"Error creating meeting: {e}")
            return None

    def update_meeting(self, folder_name: str, title: str = None, duration: int = None, attendees: str = None, status: str = None, transcript: str = None, analysis: str = None):
        """
        Updates an existing meeting record based on folder_name.

        Args:
            folder_name (str): The name of the folder where meeting data is stored.
            title (str): The new title of the meeting.
            duration (int): New duration of the meeting in seconds.
            attendees (str): New comma-separated string of attendees.
            status (str): New status of the meeting.
            transcript (str): The new full transcript text of the meeting.
            analysis (str): The new AI analysis summary of the meeting.
        """
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if duration is not None:
            updates.append("duration = ?")
            params.append(duration)
        if attendees is not None:
            updates.append("attendees = ?")
            params.append(attendees)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if transcript is not None:
            updates.append("transcript = ?")
            params.append(transcript)
        if analysis is not None:
            updates.append("analysis = ?")
            params.append(analysis)

        if not updates:
            return # Nothing to update

        query = f"UPDATE meetings SET {', '.join(updates)} WHERE folder_name = ?"
        params.append(folder_name)
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, tuple(params))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Error updating meeting {folder_name}: {e}")

    def get_meeting_by_folder(self, folder_name: str):
        """
        Retrieves a single meeting by its folder name.

        Args:
            folder_name (str): The folder name of the meeting.

        Returns:
            dict: A dictionary representing the meeting, or None if not found.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM meetings WHERE folder_name = ?", (folder_name,))
            meeting = cursor.fetchone()
            return dict(meeting) if meeting else None
        except sqlite3.Error as e:
            print(f"Error getting meeting by folder {folder_name}: {e}")
            return None
            
    def get_all_meetings(self):
        """
        Retrieves all meeting records, ordered by creation date.

        Returns:
            list: A list of dictionaries representing meeting records.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM meetings ORDER BY created_at DESC")
            meetings = [dict(row) for row in cursor.fetchall()]
            return meetings
        except sqlite3.Error as e:
            print(f"Error getting all meetings: {e}")
            return []

    def filter_meetings(self, status: str = None, start_date: str = None, end_date: str = None, topic: str = None, attendees: str = None):
        """
        Filters meetings by various criteria.

        Args:
            status (str): The status to filter by.
            start_date (str): The start of the date range (ISO format).
            end_date (str): The end of the date range (ISO format).
            topic (str): A topic to search for in the title, transcript, and analysis.
            attendees (str): An attendee to search for in the title, transcript, and analysis.

        Returns:
            list: A list of dictionaries representing matching meeting records.
        """
        try:
            cursor = self.conn.cursor()
            query = "SELECT * FROM meetings"
            conditions = []
            params = []

            if status and status != "All":
                conditions.append("status = ?")
                params.append(status)
            
            if start_date:
                conditions.append("created_at >= ?")
                params.append(start_date)

            if end_date:
                conditions.append("created_at <= ?")
                params.append(end_date)
            
            if topic:
                conditions.append("(title LIKE ? OR transcript LIKE ? OR analysis LIKE ?)")
                term = f"%{topic}%"
                params.extend([term, term, term])
            
            if attendees:
                conditions.append("(title LIKE ? OR transcript LIKE ? OR analysis LIKE ?)")
                term = f"%{attendees}%"
                params.extend([term, term, term])

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY created_at DESC"

            cursor.execute(query, tuple(params))
            meetings = [dict(row) for row in cursor.fetchall()]
            return meetings
        except sqlite3.Error as e:
            print(f"Error filtering meetings: {e}")
            return []

    def search_meetings(self, query: str):
        """
        Searches for meetings where the query appears in the title, transcript, or analysis.

        Args:
            query (str): The search term.

        Returns:
            list: A list of dictionaries representing matching meeting records.
        """
        try:
            cursor = self.conn.cursor()
            search_query = f"%{query}%"
            cursor.execute("""
                SELECT * FROM meetings
                WHERE title LIKE ? OR transcript LIKE ? OR analysis LIKE ?
                ORDER BY created_at DESC
            """, (search_query, search_query, search_query))
            meetings = [dict(row) for row in cursor.fetchall()]
            return meetings
        except sqlite3.Error as e:
            print(f"Error searching meetings: {e}")
            return []

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            print("Database connection closed.")

if __name__ == '__main__':
    # Example usage:
    db = Database()

    # Create a new chat session
    print("Creating new chat session...")
    session_id = db.create_chat_session(title="My First Chat")
    if session_id:
        print(f"Session created with ID: {session_id}")

        # Add messages to the session
        print("Adding messages...")
        db.add_message(session_id, "user", "Hello, world!")
        db.add_message(session_id, "assistant", "Hi there! How can I help you?")

        # Retrieve and print all sessions
        print("\nAll chat sessions:")
        sessions = db.get_chat_sessions()
        for session in sessions:
            print(session)

        # Retrieve and print messages for the new session
        print(f"\nMessages for session {session_id}:")
        messages = db.get_messages_for_session(session_id)
        for message in messages:
            print(message)
    
    # --- Example for indexed_files ---
    print("\n--- Testing indexed_files ---")
    db.update_indexed_file("/path/to/file.txt", 1024, 1678886400.0, "hash123", ["chunk1", "chunk2"])
    file_info = db.get_indexed_file("/path/to/file.txt")
    print("Retrieved file info:", file_info)
    
    folder_files = db.get_indexed_files_by_folder("/path/to/")
    print("Files in folder:", folder_files)

    db.delete_indexed_file("/path/to/file.txt")
    print("File info deleted.")
    file_info = db.get_indexed_file("/path/to/file.txt")
    print("Retrieved file info after delete:", file_info)

    # --- Example for meetings ---
    print("\n--- Testing meetings ---")
    meeting_id = db.create_meeting(
        folder_name="meeting-2023-10-26-09-00-00",
        title="Project Alpha Kickoff",
        duration=3600,
        attendees="John Doe, Jane Smith",
        status="Analyzed",
        transcript="This is a test transcript.",
        analysis="This is a test analysis."
    )
    if meeting_id:
        print(f"Meeting created with ID: {meeting_id}")
    
    meetings = db.get_all_meetings()
    print("\nAll meetings:")
    for meeting in meetings:
        print(meeting)

    updated_title = "Revised Project Alpha Kickoff"
    db.update_meeting(folder_name="meeting-2023-10-26-09-00-00", title=updated_title)
    updated_meeting = db.get_meeting_by_folder("meeting-2023-10-26-09-00-00")
    print("\nUpdated meeting:", updated_meeting)

    db.close()
