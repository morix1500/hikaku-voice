"use client";

import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Activity, AlertCircle } from "lucide-react";
import { clsx } from "clsx";

type TranscriptionEvent = {
    type: "transcription";
    provider: string;
    text: string;
    is_final: boolean;
    timestamp: number;
    latency_ms: number;
};

type TranscriptSegment = {
    text: string;
    latency: number;
};

type ProviderState = {
    segments: TranscriptSegment[];
    partialText: string;
    latency: number; // Current/Latest latency
    lastUpdate: number;
};

const VoiceComparison = () => {
    const [isRecording, setIsRecording] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [states, setStates] = useState<Record<string, ProviderState>>({});

    const websocketRef = useRef<WebSocket | null>(null);
    const audioContextRef = useRef<AudioContext | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const lastSpeechTimeRef = useRef<number>(0);

    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const ws = new WebSocket("ws://localhost:8009/ws");

        ws.onopen = () => {
            console.log("Connected to backend");
            setError(null);
        };

        ws.onerror = (e) => {
            console.error("WebSocket error", e);
            setError("Failed to connect to backend. Is it running?");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "transcription") {
                    handleTranscription(data);
                } else if (data.type === "config") {
                    setStates(prev => {
                        const next = { ...prev };
                        data.providers.forEach((p: string) => {
                            if (!next[p]) {
                                next[p] = { segments: [], partialText: "", latency: 0, lastUpdate: 0 };
                            }
                        });
                        return next;
                    });
                } else if (data.type === "error") {
                    setError(data.message);
                }
            } catch (e) {
                console.error("Failed to parse message", e);
            }
        };

        websocketRef.current = ws;

        return () => {
            ws.close();
        };
    }, []);

    const handleTranscription = (event: TranscriptionEvent) => {
        const now = Date.now();

        setStates((prev) => {
            const provider = event.provider;
            const current = prev[provider] || { segments: [], partialText: "", latency: 0, lastUpdate: 0 };

            let newSegments = [...current.segments];
            let newPartial = event.text;
            let latency = current.latency;

            if (event.is_final) {
                if (event.text.trim()) {
                    // Calculate latency: Time since last detected speech activity
                    // If the user is still speaking, this might be very small, which is technically correct (streaming)
                    // But usually this measures "Silence to Text" latency
                    const timeSinceSpeech = Math.max(0, now - lastSpeechTimeRef.current);
                    latency = timeSinceSpeech;

                    newSegments.push({ text: event.text, latency: latency });
                }
                newPartial = "";
            }

            return {
                ...prev,
                [provider]: {
                    segments: newSegments,
                    partialText: newPartial,
                    latency: latency,
                    lastUpdate: now,
                },
            };
        });
    };

    // ...

    const startRecording = async () => {
        try {
            setError(null);
            // Request raw audio without processing to avoid silence gating
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false,
                    channelCount: 1
                }
            });
            streamRef.current = stream;

            // Create AudioContext with 16kHz sample rate
            const ctx = new AudioContext({ sampleRate: 16000 });
            audioContextRef.current = ctx;

            await ctx.audioWorklet.addModule("/worklet.js");

            const source = ctx.createMediaStreamSource(stream);
            const worklet = new AudioWorkletNode(ctx, "pcm-processor");

            if (ctx.state === 'suspended') {
                ctx.resume();
            }

            worklet.port.onmessage = (event) => {
                const float32Array = event.data;

                // Calculate Amplitude for VAD
                let maxAmp = 0;
                // Convert Float32 to Int16 and find max
                const int16Array = new Int16Array(float32Array.length);
                for (let i = 0; i < float32Array.length; i++) {
                    const s = Math.max(-1, Math.min(1, float32Array[i]));
                    int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;

                    const absVal = Math.abs(int16Array[i]);
                    if (absVal > maxAmp) maxAmp = absVal;
                }

                // Simple VAD: If amplitude > threshold, update lastSpeechTime
                // Threshold 500 (out of 32768) is roughly 1.5% - generous enough for silence
                if (maxAmp > 500) {
                    lastSpeechTimeRef.current = Date.now();
                }



                if (websocketRef.current?.readyState === WebSocket.OPEN) {
                    // Send raw bytes
                    websocketRef.current.send(int16Array.buffer);
                }
            };

            // ... (rest unchanged) ...

            source.connect(worklet);
            worklet.connect(ctx.destination); // Mute locally? If connected to destination, it plays back. 
            // Actually, don't connect to destination if we don't want echo.
            // But WebAudio requires connection to destination or keeps alive? 
            // AudioWorklet usually keeps working if referenced. Let's try not connecting to destination first (to avoid loopback echo).
            // source.connect(worklet); 
            // Note: Chrome might GC the node if not connected to destination. 
            // Safest is to connect to a GainNode with gain 0, then destination.
            const gain = ctx.createGain();
            gain.gain.value = 0;
            worklet.connect(gain);
            gain.connect(ctx.destination);

            setIsRecording(true);
        } catch (e) {
            console.error("Failed to start recording", e);
            setError("Could not access microphone.");
        }
    };

    const stopRecording = () => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
        }
        if (audioContextRef.current) {
            audioContextRef.current.close();
        }
        setIsRecording(false);
    };

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-8">
            <div className="flex flex-col items-center space-y-4">
                <h1 className="text-4xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
                    Hikaku Voice
                </h1>
                <p className="text-slate-500">Real-time STT Comparison</p>

                {error && (
                    <div className="flex items-center gap-2 p-4 text-red-600 bg-red-50 rounded-lg">
                        <AlertCircle className="w-5 h-5" />
                        <span>{error}</span>
                    </div>
                )}

                <button
                    onClick={isRecording ? stopRecording : startRecording}
                    className={clsx(
                        "flex items-center gap-2 px-8 py-4 rounded-full font-semibold transition-all shadow-lg",
                        isRecording
                            ? "bg-red-500 hover:bg-red-600 text-white animate-pulse"
                            : "bg-indigo-600 hover:bg-indigo-700 text-white"
                    )}
                >
                    {isRecording ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                    {isRecording ? "Stop Recording" : "Start Microphone"}
                </button>
            </div>

            {/* Dynamic Grid: Auto-fit columns based on provider count */}
            <div
                className="grid gap-6"
                style={{
                    gridTemplateColumns: `repeat(${Math.max(1, Object.keys(states).length)}, 1fr)`
                }}
            >
                {Object.keys(states).length === 0 && (
                    <div className="col-span-full text-center text-slate-400 py-10">
                        Waiting for transcription providers...
                    </div>
                )}
                {Object.keys(states).map((provider) => (
                    <div key={provider} className="flex flex-col bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm h-[400px]">
                        <div className="flex items-center justify-between p-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
                            <div className="flex items-center gap-3">
                                <div className={clsx(
                                    "w-2 h-2 rounded-full",
                                    states[provider]?.lastUpdate > Date.now() - 1000 ? "bg-green-500 animate-pulse" : "bg-slate-300"
                                )} />
                                <h2 className="text-lg font-bold capitalize">{provider}</h2>
                            </div>
                            <div className="text-xs font-mono text-slate-500 flex items-center gap-2">
                                <Activity className="w-4 h-4" />
                                {states[provider]?.latency.toFixed(3)}ms
                            </div>
                        </div>

                        <div className="flex-1 p-6 overflow-y-auto space-y-2 font-normal text-lg leading-relaxed text-slate-700 dark:text-slate-300">
                            {/* Render segments */}
                            {states[provider]?.segments.map((seg, idx) => (
                                <div key={idx} className="flex items-baseline gap-2 border-b border-slate-100 dark:border-slate-800 pb-2 last:border-0 last:pb-0">
                                    <span className="text-slate-800 dark:text-slate-200">{seg.text}</span>
                                    <span className="text-xs font-mono text-slate-400 whitespace-nowrap">
                                        ({seg.latency.toFixed(3)}ms)
                                    </span>
                                </div>
                            ))}

                            {/* Render partial */}
                            {states[provider]?.partialText && (
                                <div className="text-indigo-600 dark:text-indigo-400 font-medium animate-pulse">
                                    {states[provider].partialText}
                                </div>
                            )}

                            {!states[provider]?.segments.length && !states[provider]?.partialText && (
                                <span className="text-slate-400 italic">Waiting for speech...</span>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default VoiceComparison;
