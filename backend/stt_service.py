import asyncio
import json
import time
import logging
from livekit import agents, rtc
from livekit.agents import stt
from livekit.plugins import deepgram
import aiohttp
import ssl
import certifi
import math
import struct

logger = logging.getLogger("stt-service")

class STTManager:
    def __init__(self, websocket, stt_plugins: list[stt.STT]):
        self.websocket = websocket
        self.stt_plugins = stt_plugins
        self.streams = {} # Map provider name (or index/id) to stream
        self._tasks = set()
        self._session = None

    async def initialize(self):
        try:
            # Create SSL context using certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            # Standalone usage requires passing a client session
            self._session = aiohttp.ClientSession(connector=connector)
            
            for plugin in self.stt_plugins:
                # Inject the shared session
                # Most LiveKit STT plugins store the session in _session
                # This is a hacky but necessary workaround for standalone usage without Agent context
                if hasattr(plugin, '_session'):
                    plugin._session = self._session
                if hasattr(plugin, '_http_session'):
                    plugin._http_session = self._session
                
                # Identify the provider
                # livekit.plugins.deepgram.STT -> 'deepgram'
                # livekit.plugins.openai.STT -> 'openai'
                # We can use the module name or class name, or assume the user might want to label them?
                # For now, let's try to derive a name from the class module
                provider_name = plugin.__module__.split('.')[-2] # e.g. 'openai' from 'livekit.plugins.openai.stt'
                
                # Handle duplicates (e.g. 2 deepgram instances)
                if provider_name in self.streams:
                    provider_name = f"{provider_name}_{id(plugin)}"
                
                logger.info(f"Initializing stream for {provider_name}")
                stream = plugin.stream()
                self.streams[provider_name] = stream
                
                task = asyncio.create_task(self._read_stream(stream, provider_name))
                self._tasks.add(task)
            
            logger.info(f"STT plugins initialized: {list(self.streams.keys())}")
            
            # Notify frontend of active providers so it can render columns immediately
            await self.websocket.send_json({
                "type": "config",
                "providers": list(self.streams.keys())
            })
        except Exception as e:
            logger.error(f"Failed to initialize STT plugins: {e}")
            await self.websocket.send_json({"type": "error", "message": str(e)})

    async def process_audio(self, audio_bytes: bytes):
        # Assume 16kHz 16-bit mono PCM
        samples_per_channel = len(audio_bytes) // 2

        frame = rtc.AudioFrame(
            data=audio_bytes,
            sample_rate=16000,
            num_channels=1,
            samples_per_channel=samples_per_channel
        )
        
        # Push to all streams
        for name, stream in self.streams.items():
            try:
                stream.push_frame(frame)
            except Exception as e:
                logger.warning(f"Failed to push frame to {name}: {e}")

    async def _read_stream(self, stream, provider_name):
        logger.info(f"Started reading stream for {provider_name}")
        stream_start_time = time.time()
        last_eos_time = None
        
        try:
            async for event in stream:
                current_time = time.time()
                
                if event.type == agents.stt.SpeechEventType.END_OF_SPEECH:
                    last_eos_time = current_time
                
                # Check event type for finality
                is_final = event.type == agents.stt.SpeechEventType.FINAL_TRANSCRIPT
                
                text = event.alternatives[0].text if event.alternatives else ""
                
                # Calculate latency
                latency_ms = 0.0
                if is_final and event.alternatives:
                    alt = event.alternatives[0]
                    # Method 1: Use end_time (Deepgram)
                    if getattr(alt, 'end_time', 0) > 0:
                        # end_time is relative to stream start
                        # audio_duration_processed = alt.end_time
                        # time_since_start = current_time - stream_start_time
                        # Latency = time_since_start - audio_duration_processed
                        latency_ms = (current_time - stream_start_time - alt.end_time) * 1000
                    # Method 2: Use EOS time (OpenAI)
                    elif last_eos_time:
                        latency_ms = (current_time - last_eos_time) * 1000
                
                payload = {
                    "type": "transcription",
                    "provider": provider_name,
                    "text": text,
                    "is_final": is_final,
                    "confidence": event.alternatives[0].confidence if event.alternatives else 0.0,
                    "timestamp": current_time * 1000,
                    "latency_ms": max(0.0, latency_ms) # Ensure non-negative
                }
                
                # Filter empty updates if desired, but keeping them for activity indication
                if payload["text"]:
                    try:
                        await self.websocket.send_json(payload)
                    except Exception as e:
                        # WebSocket might be closed
                        logger.warning(f"Failed to send transcription: {e}")
                        break
            
            logger.info(f"Stream finished for {provider_name}")
                    
        except Exception as e:
            logger.error(f"Error reading stream from {provider_name}: {e}")

    async def cleanup(self):
        for name, stream in self.streams.items():
            await stream.aclose()
        
        for t in self._tasks:
            t.cancel()
            
        if self._session:
            await self._session.close()
