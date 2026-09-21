import sqlite3
import json

class TelemetryDB:
    def __init__(self, db_path="edge_buffer.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telemetry_buffer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT,
                    timestamp TEXT,
                    ocr_text TEXT,
                    vector_blob BLOB,
                    synced BOOLEAN DEFAULT 0
                )
            ''')
            conn.commit()

    def insert_event(self, camera_id, timestamp, ocr_text, vector_list):
        # Convert vector_list (list of floats) to bytes for BLOB storage
        vector_blob = json.dumps(vector_list).encode('utf-8')
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO telemetry_buffer (camera_id, timestamp, ocr_text, vector_blob, synced)
                VALUES (?, ?, ?, ?, ?)
            ''', (camera_id, timestamp, ocr_text, vector_blob, 0))
            conn.commit()
