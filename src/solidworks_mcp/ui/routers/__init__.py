"""FastAPI router for the ``routers`` sub-package.

Import individual routers and include them in the FastAPI app:

.. code-block:: python

    from solidworks_mcp.ui.routers import session, model, preview, llm, checkpoint, docs, viewer
    app.include_router(session.router)
    ...
"""
