"""Show the generated checkpoint script for L-bracket."""

import sqlite3
import json

db_path = ".solidworks_mcp/agent_memory.sqlite3"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get the most recent session
cursor.execute("SELECT session_id FROM designsession ORDER BY created_at DESC LIMIT 1")
session = cursor.fetchone()
if not session:
    print("No sessions found")
    conn.close()
    exit(1)

session_id = session["session_id"]
print(f"Session: {session_id}\n")

# Get checkpoint 1
cursor.execute(
    """
    SELECT checkpoint_index, title, planned_action_json
    FROM plancheckpoint 
    WHERE session_id = ? AND checkpoint_index = 1
""",
    (session_id,),
)

checkpoint = cursor.fetchone()
if checkpoint:
    print(f"Checkpoint {checkpoint['checkpoint_index']}: {checkpoint['title']}\n")

    if checkpoint["planned_action_json"]:
        planned = json.loads(checkpoint["planned_action_json"])
        print("GENERATED EXECUTION PAYLOAD:\n")
        print(json.dumps(planned, indent=2))
else:
    print("Checkpoint 1 not found")

conn.close()
