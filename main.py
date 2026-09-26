import sys

# Windows consoles default to cp1252, which cannot print the emoji logs in webapp.py
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import uvicorn
import webapp
import os

if __name__ == "__main__":
    try:
        uvicorn.run(webapp.app, host="0.0.0.0", port=8000, reload=False)
    except Exception as e:
        print("Error:", e)
        input("Press Enter to exit...")