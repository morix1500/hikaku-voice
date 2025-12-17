import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from stt_service import STTManager
from tts_service import TTSManager

load_dotenv()

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hikaku-voice")

# Mount backend/static for worklet.js & other static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# --- STT Configuration ---
try:
    from plugins_config import stt_plugins
except ImportError:
    logger.error("plugins_config.py not found (STT).")
    stt_plugins = {}

# --- TTS Configuration ---
try:
    from plugins_config import tts_plugins
except ImportError:
    # Optional: might not exist yet if user hasn't updated config
    logger.warning("plugins_config.py not found or tts_plugins missing.")
    tts_plugins = {}

@app.get("/")
@app.get("/stt")
async def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/tts")
async def tts_page(request: Request):
    return templates.TemplateResponse("tts.html", {"request": request})

@app.websocket("/ws/stt")
async def websocket_endpoint(websocket: WebSocket, response_format: str = "json"):
    await websocket.accept()
    logger.info(f"Client connected to STT (format: {response_format})")
    
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
        logger.info("Client disconnected from STT")
    except Exception as e:
        logger.error(f"Error in STT connection: {e}")
    finally:
        await stt_manager.cleanup()

@app.websocket("/ws/tts")
async def websocket_tts_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected to TTS")
    
    tts_manager = TTSManager(tts_plugins)
    await tts_manager.initialize()

    # Send initial config (available providers)
    await websocket.send_json({
        "type": "config",
        "providers": tts_manager.get_providers()
    })

    try:
        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                if data.get("type") == "tts_request":
                    text = data.get("text")
                    if text:
                        logger.info(f"Received TTS request: {text}")
                        # Run synthesis
                        results = await tts_manager.synthesize(text)
                        
                        # Send back results
                        await websocket.send_json({
                            "type": "tts_response",
                            "results": results
                        })
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Error processing TTS request: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("Client disconnected from TTS")
    except Exception as e:
        logger.error(f"Error in TTS connection: {e}")
    finally:
        await tts_manager.cleanup()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
