"""``solidworks-mcp-python selftest``: check a SolidWorks setup and report it.

With SolidWorks running, the selftest builds a small part, an assembly, a
drawing view and a STEP export through the same MCP tools an agent calls,
checks each against a hand calculation (``expected.py``), and prints a
report to paste into a compatibility issue. It never touches a document
that was open before it started (``documents.py``).
"""
