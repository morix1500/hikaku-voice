import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from stt_service import STTManager

load_dotenv()

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hikaku-voice")

# Mount backend/static for worklet.js
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

@app.get("/")
async def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})



# ...

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, response_format: str = "json"):
    await websocket.accept()
    logger.info(f"Client connected (format: {response_format})")
    
    # Configure STT Plugins
    # Loaded from plugins_config.py (gitignored)
    try:
        from plugins_config import stt_plugins
    except ImportError:
        logger.error("plugins_config.py not found. Please copy plugins_config.py.example to plugins_config.py")
        stt_plugins = {}
    
    stt_manager = STTManager(websocket, stt_plugins, response_format=response_format)
    await stt_manager.initialize()

    try:
        while True:
            # Receive message from client
            # It can be JSON (config) or bytes (audio)
            message = await websocket.receive()
            
            if "bytes" in message and message["bytes"]:
                #logger.info(f"Received bytes: {len(message['bytes'])}")
                await stt_manager.process_audio(message["bytes"])
            elif "text" in message and message["text"]:
                # Handle control messages if any
                try:
                    data = json.loads(message["text"])
                    # logger.info(f"Received control message: {data}")
                    stt_manager.handle_control_message(data)
                except json.JSONDecodeError:
                    # Might be raw text or other format
                    pass
                
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await stt_manager.cleanup()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
