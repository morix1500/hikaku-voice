# Hikaku Voice

A real-time Speech-to-Text (STT) and Text-to-Speech (TTS) comparator.
Compare multiple providers side-by-side with fair latency measurement.

## Features

- **STT Comparison**: Compare transcription latency and accuracy across multiple STT providers using VAD-based measurement.
- **TTS Comparison**: Compare TTFB (Time To First Byte) and audio output quality across multiple TTS providers.

## Setup

### 1. Prerequisites
- Python 3.12+ (We recommend using `uv` for package management)
- API Keys for the LiveKit-compatible STT/TTS plugins you want to test.

### 2. Install Dependencies
```bash
make install
```

### 3. Configuration

**Environment Variables**
Create a `.env` file in the root directory.
(Example for OpenAI, Deepgram, etc.)
```bash
OPENAI_API_KEY=sk-...
DEEPGRAM_API_KEY=...
# OTHER_PROVIDER_KEY=...
```

**Plugin Configuration**
Copy the example config to enable/disable specific plugins:
```bash
cp plugins_config.py.example plugins_config.py
```
Edit `plugins_config.py` to customize models or parameters.
You can import any `livekit-plugins-*` package here.
For available plugins, see:
- [LiveKit Agents STT Plugins](https://docs.livekit.io/agents/models/stt/)
- [LiveKit Agents TTS Plugins](https://docs.livekit.io/agents/models/tts/)

### 4. Run
Start the development server:
```bash
make run
```
Access the interface at **http://localhost:8009**.

## Usage

### STT Comparison (`/`)
1. Click **Start Recording**.
2. Speak in your configured language.
3. Observe the latency (measured from the end of speech detected by the client).

### TTS Comparison (`/tts`)
1. Enter text in the input field.
2. Click **Compare TTS**.
3. Listen to audio outputs and compare TTFB across providers.
