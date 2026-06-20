"""Service layer — pure Python functions the GUI calls directly.

These mirror what the old FastAPI endpoints did, minus the HTTP envelope.
The Qt app imports from here on background threads; nothing here touches
the network unless explicitly noted (Gemini lookup, MFC crawl, fx).
"""
