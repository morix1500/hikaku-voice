# Hikaku Voice

A real-time Speech-to-Text (STT) latency comparator.
Compare multiple STT providers side-by-side with fair, VAD-based latency measurement.

## Setup

### 1. Prerequisites
- Python 3.12+ (We recommend using `uv` for package management)
- API Keys for the LiveKit-compatible STT plugins you want to test.

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
For installation of other plugins, see: [LiveKit Agents STT Plugins](https://docs.livekit.io/agents/models/stt/#plugins).

### 4. Run
Start the development server:
```bash
make run
```
Access the interface at **http://localhost:8009**.

## Usage
1. Click **Start Recording**.
2. Speak in your configured language.
3. Observe the latency (measured from the end of speech detected by the client).
