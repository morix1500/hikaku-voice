class PCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 4096;
        this.buffer = new Float32Array(this.bufferSize);
        this.bytesWritten = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (!input || !input[0]) return true;

        const inputChannel = input[0];

        // Simple downsampling (assuming input is 44.1 or 48kHz, target 16kHz)
        // For robust implementation, we should use a proper resampling algorithm.
        // However, for this MVP, we'll let the AudioContext handle sample rate if possible,
        // or just pass through and let the backend handle it if we set context to 16k.

        // Better approach: User creates AudioContext with sampleRate: 16000.
        // Then we just pass the float data as Int16.

        this.port.postMessage(inputChannel);
        return true;
    }
}

registerProcessor('pcm-processor', PCMProcessor);
