import asyncio
import time
import logging
from livekit import agents, rtc
from livekit.agents import stt
import aiohttp
import ssl
import certifi

logger = logging.getLogger("stt-service")

class STTManager:
    def __init__(self, websocket, stt_plugins: dict[str, stt.STT], response_format: str = "json"):
        self.websocket = websocket
        self.stt_plugins = stt_plugins
        self.response_format = response_format
        self.streams = {} # Map provider name (or index/id) to stream
        self._tasks = set()
        self._session = None
        self.last_client_vad_eos = None

    def handle_control_message(self, data: dict):
        if data.get("type") == "vad_speech_end":
            # Use provided timestamp if available, otherwise fallback to current time
            timestamp = data.get("timestamp")
            if timestamp:
                self.last_client_vad_eos = float(timestamp)
            else:
                self.last_client_vad_eos = time.time()
                
            logger.info(f"Client VAD: Speech ended at {self.last_client_vad_eos}")

    async def initialize(self):
        try:
            # Create SSL context using certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            # Standalone usage requires passing a client session
            self._session = aiohttp.ClientSession(connector=connector)
            
            if not isinstance(self.stt_plugins, dict):
                 raise ValueError("stt_plugins must be a dictionary of {alias: plugin_instance}")

            for provider_name, plugin in self.stt_plugins.items():
                # Inject the shared session
                # Most LiveKit STT plugins store the session in _session
                # This is a hacky but necessary workaround for standalone usage without Agent context
                if hasattr(plugin, '_session'):
                    plugin._session = self._session # type: ignore
                if hasattr(plugin, '_http_session'):
                    plugin._http_session = self._session # type: ignore
                
                # Handle duplicates automatically only for list-based config or if user made a mistake in dict keys (unlikely for dict keys but good safety)
                # Actually for dict, keys are unique by definition.
                # For list, we might have duplicates.
                if provider_name in self.streams:
                    provider_name = f"{provider_name}_{id(plugin)}"
                
                logger.info(f"Initializing stream for {provider_name}")
                stream = plugin.stream()
                self.streams[provider_name] = stream
                
                task = asyncio.create_task(self._read_stream(stream, provider_name))
                self._tasks.add(task)
            
            logger.info(f"STT plugins initialized: {list(self.streams.keys())}")
            
            # Notify frontend of active providers so it can render columns immediately
            # Send both ID (safe for HTML) and Name (display)
            providers_config = []
            for name in self.streams.keys():
                safe_id = self._sanitize_id(name)
                providers_config.append({"id": safe_id, "name": name})

            await self.websocket.send_json({
                "type": "config",
                "providers": providers_config
            })
        except Exception as e:
            logger.error(f"Failed to initialize STT plugins: {e}")
            await self.websocket.send_json({"type": "error", "message": str(e)})

    def _sanitize_id(self, name: str) -> str:
        return name.lower().replace(" ", "-").replace("_", "-").replace(".", "-")

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
        safe_id = self._sanitize_id(provider_name)
        
        try:
            async for event in stream:
                current_time = time.time()
                
                # Debug logging (generic)
                # logger.debug(f"[{provider_name}] Event: {event.type}")

                # Check event type for finality
                is_final = event.type == agents.stt.SpeechEventType.FINAL_TRANSCRIPT
                
                text = event.alternatives[0].text if event.alternatives else ""
                
                # Calculate latency
                latency_ms = 0.0
                if is_final and event.alternatives:
                    # STRICT FAIRNESS: Only use Client VAD timestamp for ALL providers.
                    if self.last_client_vad_eos:
                         latency_ms = (current_time - self.last_client_vad_eos) * 1000
                    else:
                        logger.debug(f"[{provider_name}] No Client VAD signal yet. Skipping latency calc.")
                        latency_ms = 0.0

                    if latency_ms == 0.0:
                         logger.debug(f"[{provider_name}] Latency is 0.0. vad_eos={self.last_client_vad_eos}")

                payload = {
                    "type": "transcription",
                    "provider": provider_name,
                    "provider_id": safe_id,
                    "text": text,
                    "is_final": is_final,
                    "confidence": event.alternatives[0].confidence if event.alternatives else 0.0,
                    "timestamp": current_time * 1000,
                    "latency_ms": max(0.0, latency_ms) # Ensure non-negative
                }
                
                # Filter empty updates if desired, but keeping them for activity indication
                try:
                    if self.response_format == "html":
                        # ...
                        
                        html_content = ""
                        if is_final:
                            # logger.info(f"[{provider_name}] Generating HTML with latency: {latency_ms}")
                            html_content = f"""
                            <div id="{safe_id}-log" hx-swap-oob="beforeend">
                                <div class="segment">
                                    <span class="text">{text}</span>
                                    <div class="latency">Latency: {latency_ms:.0f}ms</div>
                                </div>
                            </div>
                            """
                        else:
                             # For interim, maybe update a placeholder? 
                             # Skipping interim for basic POC to avoid UI jitter without proper ID tracking
                             pass

                        if html_content:
                            await self.websocket.send_text(html_content)
                    else:
                        if payload["text"]:
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
