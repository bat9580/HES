import uvicorn
import webapp
import os 

if __name__ == "__main__":
    try:
        uvicorn.run(webapp.app, host="0.0.0.0", port=8000, reload=False)
    except Exception as e:
        print("Error:", e)
        input("Press Enter to exit...")