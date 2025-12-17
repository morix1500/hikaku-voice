import asyncio
import time
import logging
import base64
from livekit.agents import tts
import aiohttp
import ssl
import certifi

logger = logging.getLogger("tts-service")

class TTSManager:
    def __init__(self, tts_plugins: dict[str, tts.TTS]):
        self.tts_plugins = tts_plugins
        self._session = None

    async def initialize(self):
        try:
            # Create SSL context using certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            # Standalone usage requires passing a client session
            self._session = aiohttp.ClientSession(connector=connector)
            
            if not isinstance(self.tts_plugins, dict):
                 raise ValueError("tts_plugins must be a dictionary of {alias: plugin_instance}")

            for provider_name, plugin in self.tts_plugins.items():
                if hasattr(plugin, '_session'):
                    plugin._session = self._session # type: ignore
                if hasattr(plugin, '_http_session'):
                    plugin._http_session = self._session # type: ignore
            
            logger.info(f"TTS plugins initialized: {list(self.tts_plugins.keys())}")

        except Exception as e:
            logger.error(f"Failed to initialize TTS plugins: {e}")
            raise e

    def get_providers(self):
        providers = []
        for name in self.tts_plugins.keys():
            safe_id = self._sanitize_id(name)
            providers.append({"id": safe_id, "name": name})
        return providers

    def _sanitize_id(self, name: str) -> str:
        return name.lower().replace(" ", "-").replace("_", "-").replace(".", "-")

    async def synthesize(self, text: str):
        results = []
        tasks = []

        for name, plugin in self.tts_plugins.items():
            tasks.append(self._synthesize_single(name, plugin, text))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def _synthesize_single(self, name: str, plugin: tts.TTS, text: str):
        safe_id = self._sanitize_id(name)
        start_time = time.time()
        ttfb_ms = 0.0
        audio_data = bytearray()
        sample_rate = 24000  # default
        
        try:
            logger.info(f"[{name}] Starting synthesis for: {text[:20]}...")
            
            # Use synthesize() for non-streaming TTS (works for both OpenAI and Deepgram)
            stream = plugin.synthesize(text)
            first_chunk_received = False
            
            async for synthesized_audio in stream:
                if not first_chunk_received:
                    ttfb_ms = (time.time() - start_time) * 1000
                    first_chunk_received = True
                    logger.debug(f"[{name}] TTFB: {ttfb_ms:.2f}ms")
                
                # SynthesizedAudio has .frame which is an AudioFrame
                if synthesized_audio.frame and synthesized_audio.frame.data:
                    audio_data.extend(synthesized_audio.frame.data)
                    sample_rate = synthesized_audio.frame.sample_rate or sample_rate

            total_time_ms = (time.time() - start_time) * 1000
            
            wav_bytes = self._create_wav_header(audio_data, sample_rate=sample_rate)
            b64_audio = base64.b64encode(wav_bytes).decode('utf-8')

            return {
                "provider": name,
                "provider_id": safe_id,
                "ttfb_ms": ttfb_ms,
                "total_time_ms": total_time_ms,
                "audio_base64": b64_audio,
                "error": None
            }

        except Exception as e:
            logger.error(f"[{name}] Synthesis failed: {e}")
            return {
                "provider": name,
                "provider_id": safe_id,
                "ttfb_ms": 0,
                "total_time_ms": 0,
                "audio_base64": None,
                "error": str(e)
            }

    def _create_wav_header(self, pcm_data: bytes | bytearray, sample_rate=24000, channels=1, bit_depth=16) -> bytes:
        # Standard WAV header creation
        # Most TT plugins output 24kHz (Deepgram Aura, OpenAI TTS-1) but we should ideally check the frame.sample_rate if accessible.
        # Since we're iterating events, we might have missed checking the first frame's rate.
        # For now, let's default to 24000 as it's common for high quality TTS, or 22050.
        # OpenAI is 24kHz by default in livekit-plugins-openai? 
        # Deepgram is 24kHz?
        # Let's try to detect or strictly hardcode 24000 for verified plugins.
        
        # NOTE: Hardcoding 24000Hz for this POC. If audio sounds slow/fast, this is why.
        
        import struct
        
        file_length = len(pcm_data) + 44 - 8
        
        header = b'RIFF' + struct.pack('<I', file_length) + b'WAVE'
        header += b'fmt ' + struct.pack('<I', 16) + struct.pack('<H', 1) # PCM
        header += struct.pack('<H', channels) + struct.pack('<I', sample_rate)
        header += struct.pack('<I', sample_rate * channels * bit_depth // 8)
        header += struct.pack('<H', channels * bit_depth // 8) + struct.pack('<H', bit_depth)
        header += b'data' + struct.pack('<I', len(pcm_data))
        
        return header + pcm_data

    async def cleanup(self):
        if self._session:
            await self._session.close()
