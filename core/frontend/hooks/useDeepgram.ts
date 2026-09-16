import { fetchWithAuth } from "@/lib/apiClient"
import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * useDeepgram - Browser-native WebSocket implementation.
 *
 * We bypass @deepgram/sdk entirely here because the v5 SDK is
 * auto-generated for Node.js and causes Vite bundling errors in the browser.
 *
 * Deepgram's own docs recommend native WebSocket for browser implementations:
 * https://developers.deepgram.com/docs/getting-started-with-live-streaming-audio
 *
 * Flow:
 *   1. Fetch API key from our backend (never exposed in the bundle)
 *   2. Open a native WebSocket to wss://api.deepgram.com/v1/listen
 *   3. Capture audio via getDisplayMedia (tab audio) or getUserMedia (mic)
 *   4. Stream MediaRecorder chunks to the WebSocket
 *   5. Parse incoming JSON messages for transcripts
 */
export function useDeepgram(onTranscript: (text: string, isFinal: boolean) => void) {
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const startListening = useCallback(async () => {
    try {
      setError(null);

      // 1. Fetch API key securely from backend
      const res = await fetchWithAuth('/api/system/keys');
      if (!res.ok) throw new Error('Could not reach backend');
      const keys = await res.json();
      const apiKey = keys.DEEPGRAM_API_KEY;

      if (!apiKey) {
        throw new Error('Deepgram API Key not configured in backend .env');
      }

      // 2. Capture audio — tab audio for meeting listening
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getDisplayMedia({
          video: false,
          audio: true,
        });
      } catch {
        // Fallback to microphone if getDisplayMedia is rejected
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      streamRef.current = stream;

      // 3. Open native WebSocket to Deepgram
      const params = new URLSearchParams({
        model: 'nova-2',
        language: 'en-US',
        smart_format: 'true',
        interim_results: 'true',
        endpointing: '500',
        encoding: 'opus',
        sample_rate: '48000',
      });
      const wsUrl = `wss://api.deepgram.com/v1/listen?${params.toString()}`;
      const ws = new WebSocket(wsUrl, ['token', apiKey]);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsListening(true);

        // 4. Stream audio via MediaRecorder
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm';

        const mediaRecorder = new MediaRecorder(stream, { mimeType });
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.addEventListener('dataavailable', (event) => {
          if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
            ws.send(event.data);
          }
        });

        mediaRecorder.start(250); // Send a chunk every 250ms
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // 5. Parse transcript from Deepgram response format
          if (data.type === 'Results') {
            const alt = data?.channel?.alternatives?.[0];
            const transcript = alt?.transcript ?? '';
            if (transcript) {
              const isFinal = data.speech_final === true || data.is_final === true;
              onTranscript(transcript, isFinal);
            }
          }
        } catch {
          // Non-JSON keepalive frames — safe to ignore
        }
      };

      ws.onerror = (ev) => {
        console.error('[Deepgram WS] Error:', ev);
        setError('WebSocket connection error — check API key and network.');
        stopListening();
      };

      ws.onclose = () => {
        setIsListening(false);
      };

      // Stop stream tracks if the user ends the screen share themselves
      stream.getAudioTracks().forEach((track) => {
        track.addEventListener('ended', () => stopListening());
      });

    } catch (err: any) {
      console.error('[Deepgram] Start failed:', err);
      setError(err.message || 'Failed to start listening');
    }
  }, [onTranscript]);

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.close();
    }
    setIsListening(false);
  }, []);

  useEffect(() => {
    return () => {
      stopListening();
    };
  }, [stopListening]);

  return {
    isListening,
    startListening,
    stopListening,
    error,
  };
}
