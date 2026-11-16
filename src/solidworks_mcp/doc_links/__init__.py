"""The docs' own ``llms.txt``, and a check of every link in the docs.

Run from a checkout::

    python -m solidworks_mcp.doc_links build           # write docs/llms.txt
    python -m solidworks_mcp.doc_links check           # offline: llms.txt and project links
    python -m solidworks_mcp.doc_links check-external  # online: every link to another site

``llms.txt`` is built from the mkdocs nav: each entry's title and summary
are copied word for word from the page it links to, so nothing in it is
written by hand. Specs: ``docs/llms-txt`` and ``docs/link-check``.
"""
