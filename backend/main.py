import asyncio
import os
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from stt_service import STTManager

load_dotenv()

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hikaku-voice")

@app.on_event("startup")
async def startup_event():
    openai_key = os.getenv("OPENAI_API_KEY")
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    soniox_key = os.getenv("SONIOX_API_KEY")
    
    if not openai_key:
        logger.error("OPENAI_API_KEY is missing in environment!")
    else:
        logger.info(f"OPENAI_API_KEY loaded (starts with {openai_key[:3]}...)")
        
    if not deepgram_key:
        logger.error("DEEPGRAM_API_KEY is missing in environment!")
    else:
        logger.info(f"DEEPGRAM_API_KEY loaded (starts with {deepgram_key[:3]}...)")
    
    if not soniox_key:
        logger.error("SONIOX_API_KEY is missing in environment!")
    else:
        logger.info(f"SONIOX_API_KEY loaded (starts with {soniox_key[:3]}...)")

from livekit.plugins import deepgram, openai, soniox
# import other plugins as needed

# ...

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected")
    
    # Configure STT Plugins here
    # You can easily add more plugins to this list
    stt_plugins = [
        deepgram.STT(model="nova-2-general", language="ja"),
        openai.STT(language="ja", use_realtime=True),
        soniox.STT(
            api_key=os.getenv("SONIOX_API_KEY"),
            params=soniox.STTOptions(
                model="stt-rt-v3",
                language_hints=["ja"],
                enable_language_identification=False,
                context="日本の飲食店の商品名、注文商品の希望受け取り時間",
            ),
        ),
    ]
    
    stt_manager = STTManager(websocket, stt_plugins)
    await stt_manager.initialize()

    try:
        while True:
            # Receive message from client
            # It can be JSON (config) or bytes (audio)
            message = await websocket.receive()
            
            if "bytes" in message and message["bytes"]:
                # logger.info(f"Received bytes: {len(message['bytes'])}")
                await stt_manager.process_audio(message["bytes"])
            elif "text" in message and message["text"]:
                # Handle control messages if any
                data = json.loads(message["text"])
                logger.info(f"Received control message: {data}")
                
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await stt_manager.cleanup()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
