"""Query SQLite to inspect generated checkpoint payloads."""

import sqlite3
import json

db_path = ".solidworks_mcp/agent_memory.sqlite3"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get latest session
cursor.execute("SELECT session_id FROM designsession ORDER BY created_at DESC LIMIT 1")
session = cursor.fetchone()
if not session:
    print("No sessions found")
    conn.close()
    exit(1)

session_id = session["session_id"]
print(f"Latest session: {session_id}\n")

# Get all checkpoints for this session
cursor.execute(
    """
    SELECT checkpoint_index, title, planned_action_json, executed, result_json
    FROM plancheckpoint 
    WHERE session_id = ?
    ORDER BY checkpoint_index ASC
""",
    (session_id,),
)

checkpoints = cursor.fetchall()
print(f"Found {len(checkpoints)} checkpoints:\n")

for checkpoint in checkpoints:
    idx = checkpoint["checkpoint_index"]
    title = checkpoint["title"]
    executed = checkpoint["executed"]
    print(f"{'=' * 80}")
    print(f"Checkpoint {idx}: {title}")
    print(f"Executed: {executed}")

    if checkpoint["planned_action_json"]:
        try:
            planned = json.loads(checkpoint["planned_action_json"])
            print(f"\nPlanned Action Payload:")
            print(json.dumps(planned, indent=2))
        except Exception as e:
            print(f"Error parsing payload: {e}")
    print()

conn.close()
