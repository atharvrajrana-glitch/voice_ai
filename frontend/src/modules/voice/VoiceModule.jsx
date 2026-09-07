import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, RotateCcw, Plus, FileText, Loader2, X, Send, Volume2 } from 'lucide-react';
import { askAICore } from '../aiCore/api';
import { uploadPatientDocument } from '../patientDocs/api';

const FONT_LINK = 'https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap';

function toSpeechLocale(languageName) {
  if (!languageName) return 'en-US';
  const map = {
    english: 'en-US', hindi: 'hi-IN', spanish: 'es-ES', french: 'fr-FR',
    arabic: 'ar-SA', bengali: 'bn-IN', tamil: 'ta-IN', telugu: 'te-IN',
    marathi: 'mr-IN', gujarati: 'gu-IN', punjabi: 'pa-IN', urdu: 'ur-IN',
    mandarin: 'zh-CN', chinese: 'zh-CN', portuguese: 'pt-BR', german: 'de-DE',
    japanese: 'ja-JP', russian: 'ru-RU',
  };
  const key = languageName.toLowerCase().trim();
  for (const name in map) {
    if (key.includes(name)) return map[name];
  }
  return 'en-US';
}

function floatTo16BitPCM(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < float32Array.length; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

export default function VoiceModule({ patientName = '' }) {
  const [phase, setPhase] = useState('idle');
  const [transcriptLog, setTranscriptLog] = useState([]);
  const [interim, setInterim] = useState('');
  const [textQuestion, setTextQuestion] = useState('');
  const [needsGreeting, setNeedsGreeting] = useState(true);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const [bookingNotification, setBookingNotification] = useState(null);
  const [usingLive, setUsingLive] = useState(true); // Gemini Live is primary; falls back to Whisper/REST

  // ---- Classic (Whisper/REST) refs ----
  const recognitionRef = useRef(null);
  const keepAliveRef = useRef(null);
  const voicesRef = useRef([]);
  const fileInputRef = useRef(null);
  const handlePatientTextRef = useRef(null);

  // ---- Gemini Live (push-to-talk) refs ----
  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const micSourceRef = useRef(null);
  const processorRef = useRef(null);
  const streamRef = useRef(null);
  const playContextRef = useRef(null);
  const nextPlayTimeRef = useRef(0);
  const isRecordingRef = useRef(false); // true while mic button held
  const isBusyRef = useRef(false);      // true from stop_turn until turn_complete
  const liveConnectingRef = useRef(false);
  const isMountedRef = useRef(true);

  const sessionId = localStorage.getItem('medclear_session_id');
  
  // Build API URL dynamically based on current window location
  // If accessed from localhost, backend is also localhost
  // If accessed from hostname, backend is the same hostname
  const getApiUrl = () => {
    if (import.meta.env.VITE_API_URL) {
      return import.meta.env.VITE_API_URL;
    }
    // Use current host (preserves localhost when accessed locally, uses IP when accessed via IP)
    const protocol = window.location.protocol;
    const host = window.location.hostname;
    const port = window.location.port ? `:${window.location.port === '5173' ? '8080' : window.location.port}` : '';
    return `${protocol}//${host}${port}`;
  };
  
  const WS_BASE = getApiUrl()
    .replace('http://', 'ws://')
    .replace('https://', 'wss://');

  // =====================================================
  // SETUP
  // =====================================================
  useEffect(() => {
    // StrictMode runs an effect cleanup/re-run cycle in development.
    // Restore this guard on every setup so reconnects remain enabled.
    isMountedRef.current = true;
    const link = document.createElement('link');
    link.href = FONT_LINK;
    link.rel = 'stylesheet';
    document.head.appendChild(link);

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition && !window.speechSynthesis) {
      setPhase('unsupported');
    }

    const loadVoices = () => {
      voicesRef.current = window.speechSynthesis.getVoices();
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      isMountedRef.current = false;
      document.head.removeChild(link);
      if (recognitionRef.current) {
        try { recognitionRef.current.abort?.(); } catch (e) {}
      }
      window.speechSynthesis?.cancel();
      clearInterval(keepAliveRef.current);
      teardownLive();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // =====================================================
  // CLASSIC (WHISPER / REST) MODE — FALLBACK
  // =====================================================
  const speak = useCallback((text, who, onDone, locale, skipLog = false) => {
    window.speechSynthesis.resume();

    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1.3;
    utter.pitch = 1.0;
    utter.lang = locale || 'en-US';

    const voices = voicesRef.current.length ? voicesRef.current : window.speechSynthesis.getVoices();
    const wantLang = (locale || 'en-US').toLowerCase();
    const wantPrefix = wantLang.split('-')[0];
    const matchedVoice =
      voices.find((v) => v.lang.toLowerCase() === wantLang) ||
      voices.find((v) => v.lang.toLowerCase().startsWith(`${wantPrefix}-`));
    if (matchedVoice) utter.voice = matchedVoice;

    utter.onend = () => {
      clearInterval(keepAliveRef.current);
      onDone && onDone();
    };
    utter.onerror = () => {
      clearInterval(keepAliveRef.current);
      onDone && onDone();
    };

    setPhase('speaking');
    if (!skipLog) {
      setTranscriptLog((log) => [...log, { who, text }]);
    }
    window.speechSynthesis.speak(utter);
  }, []);

  const startListeningClassic = useCallback(async () => {
    try {
      setPhase('listening');
      setInterim('Recording...');

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { autoGainControl: true, noiseSuppression: true, echoCancellation: true, sampleRate: 16000 },
      });

      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/wav' });
      const audioChunks = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunks.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        setInterim('Transcribing...');
        stream.getTracks().forEach((track) => track.stop());

        try {
          const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
          const formData = new FormData();
          formData.append('file', audioBlob, 'audio.wav');

          const response = await fetch('/api/v1/transcribe', { method: 'POST', body: formData });
          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Transcription failed');
          }

          const data = await response.json();
          setInterim('');

          if (data.text.trim()) {
            setTranscriptLog((log) => [...log, { who: 'patient', text: data.text.trim() }]);
            handlePatientTextRef.current(data.text.trim());
          } else {
            setPhase('idle');
          }
        } catch (err) {
          console.error('[Voice] Transcription error:', err);
          setInterim('');
          setPhase('idle');
          speak("I couldn't understand that. Could you please try again?", 'ai', () => startListeningClassic());
        }
      };

      mediaRecorder.start();

      const timeout = setTimeout(() => {
        if (mediaRecorder.state === 'recording') mediaRecorder.stop();
      }, 10000);

      recognitionRef.current = { mediaRecorder, timeout };
    } catch (err) {
      console.error('[Voice] Microphone error:', err);
      setPhase('idle');
      setInterim('');
      if (err.name === 'NotAllowedError') {
        speak('Microphone access is required. Please check your browser permissions.', 'ai', () => {});
      } else {
        speak('Could not access microphone. Please try again.', 'ai', () => {});
      }
    }
  }, [speak]);

  const handlePatientText = useCallback(
    async (heardText) => {
      window.speechSynthesis.cancel();
      setPhase('thinking');

      let fullSentence = '';
      let accumulatedTTSBuffer = '';
      let hasStartedSpeaking = false;

      try {
        const startListeningAfterSpeech = () => {
          if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
            window.setTimeout(startListeningAfterSpeech, 120);
            return;
          }
          const isClosingStatement = /(goodbye|have a (wonderful|great|good) day|bye\b|reach out if you need|take care|thank you|thanks for|appreciate|welcome)/i.test(fullSentence);
          if (isClosingStatement) {
            setPhase('idle');
            setNeedsGreeting(true);
          } else if (usingLive) {
            startListeningLive();
          } else {
            startListeningClassic();
          }
        };

        const { reply, resolved, language, isBookingSuccess } = await askAICore(
          heardText,
          { documentMode: uploadStatus === 'done' },
          (newWord) => {
            fullSentence += newWord;

            setTranscriptLog((currentLog) => {
              const newLog = [...currentLog];
              const lastIndex = newLog.length - 1;
              const lastEntry = newLog[lastIndex];
              if (lastEntry && lastEntry.who === 'ai') {
                newLog[lastIndex] = { ...lastEntry, text: fullSentence };
              } else {
                newLog.push({ who: 'ai', text: fullSentence });
              }
              return newLog;
            });

            accumulatedTTSBuffer += newWord;

            if (/[.,!?]\s*$/.test(accumulatedTTSBuffer)) {
              const textToSpeak = accumulatedTTSBuffer.trim();
              accumulatedTTSBuffer = '';
              if (textToSpeak) {
                if (!hasStartedSpeaking) {
                  setPhase('speaking');
                  hasStartedSpeaking = true;
                }
                speak(textToSpeak, 'ai', null, 'en-US', true);
              }
            }
          }
        );

        if (isBookingSuccess) {
          setBookingNotification({ show: true, message: 'Appointment booked successfully!' });
          setTimeout(() => setBookingNotification(null), 5000);
        }

        if (accumulatedTTSBuffer.trim()) {
          speak(accumulatedTTSBuffer.trim(), 'ai', () => startListeningAfterSpeech(), 'en-US', true);
        } else {
          startListeningAfterSpeech();
        }
      } catch (err) {
        console.error('Unable to get an AI-core response:', err);
        speak("I'm having trouble reaching the assistant right now. Please try again in a moment.", 'ai', () =>
          usingLive ? startListeningLive() : startListeningClassic()
        );
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [speak, startListeningClassic, uploadStatus, usingLive]
  );

  useEffect(() => {
    handlePatientTextRef.current = handlePatientText;
  }, [handlePatientText]);

  const stopAll = () => {
    window.speechSynthesis.cancel();

    if (recognitionRef.current) {
      if (recognitionRef.current.mediaRecorder) {
        const { mediaRecorder, timeout } = recognitionRef.current;
        if (mediaRecorder.state === 'recording') mediaRecorder.stop();
        clearTimeout(timeout);
      } else if (recognitionRef.current.abort) {
        recognitionRef.current.abort();
      }
    }

    stopLiveTurn();
    setPhase('idle');
    setInterim('');
  };

  // =====================================================
  // GEMINI LIVE MODE — PRIMARY (push-to-talk)
  // =====================================================
  const teardownLive = useCallback(() => {
    if (processorRef.current) {
      try { processorRef.current.disconnect(); } catch (e) {}
      processorRef.current = null;
    }
    if (micSourceRef.current) {
      try { micSourceRef.current.disconnect(); } catch (e) {}
      micSourceRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (playContextRef.current) {
      playContextRef.current.close().catch(() => {});
      playContextRef.current = null;
    }
    if (wsRef.current) {
      try { wsRef.current.close(); } catch (e) {}
      wsRef.current = null;
    }
    isRecordingRef.current = false;
    isBusyRef.current = false;
  }, []);

  const playPcmChunk = useCallback((base64Data) => {
    if (!playContextRef.current) {
      playContextRef.current = new AudioContext({ sampleRate: 24000 });
      nextPlayTimeRef.current = 0;
    }
    const ctx = playContextRef.current;
    const binary = atob(base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

    const float32 = new Float32Array(bytes.length / 2);
    const view = new DataView(bytes.buffer);
    for (let i = 0; i < float32.length; i++) {
      float32[i] = view.getInt16(i * 2, true) / 32768;
    }

    const buffer = ctx.createBuffer(1, float32.length, 24000);
    buffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    const startAt = Math.max(now, nextPlayTimeRef.current);
    source.start(startAt);
    nextPlayTimeRef.current = startAt + buffer.duration;

    setPhase('speaking');
  }, []);

  // Sets up mic capture; frames are only SENT while isRecordingRef.current is true
  const startMicCapture = useCallback(async (ws) => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    streamRef.current = stream;

    const audioContext = new AudioContext({ sampleRate: 16000 });
    audioContextRef.current = audioContext;

    const source = audioContext.createMediaStreamSource(stream);
    micSourceRef.current = source;
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;

    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      if (!isRecordingRef.current) return; // only stream while button held

      const input = e.inputBuffer.getChannelData(0);
      const pcmBuffer = floatTo16BitPCM(input);
      const uint8View = new Uint8Array(pcmBuffer);
      let binary = '';
      const chunkSize = 8192;
      for (let i = 0; i < uint8View.length; i += chunkSize) {
        binary += String.fromCharCode(...uint8View.subarray(i, i + chunkSize));
      }
      ws.send(JSON.stringify({ type: 'audio', data: btoa(binary) }));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);
  }, []);

  const connectLive = useCallback(async () => {
    if (!sessionId) {
      setUsingLive(false);
      startListeningClassic();
      return;
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) return; // already connected
    if (liveConnectingRef.current) return;
    liveConnectingRef.current = true;

    console.log('[Live] Connecting to Gemini Live...');

    const ws = new WebSocket(`${WS_BASE}/ws/live?session_id=${sessionId}`);
    wsRef.current = ws;

    let connected = false;
    const timeout = setTimeout(() => {
      if (!connected) {
        console.warn('[Live] Connection timeout - falling back to Classic mode');
        liveConnectingRef.current = false;
        setUsingLive(false);
        teardownLive();
        startListeningClassic();
      }
    }, 5000);

    ws.onopen = async () => {
      connected = true;
      liveConnectingRef.current = false;
      clearTimeout(timeout);
      setUsingLive(true);
      console.log('[Live] Connected. Ready for mic input.');

      try {
        await startMicCapture(ws);
        setPhase('idle');
      } catch (err) {
        console.error('[Live] Microphone error:', err);
        setUsingLive(false);
        teardownLive();
        startListeningClassic();
      }
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === 'audio') {
        playPcmChunk(msg.data);
      } else if (msg.type === 'user_transcript') {
        setInterim(msg.text);
        setTranscriptLog((log) => {
          const newLog = [...log];
          const last = newLog[newLog.length - 1];
          if (last?.who === 'patient') {
            newLog[newLog.length - 1] = { ...last, text: msg.text };
          } else {
            newLog.push({ who: 'patient', text: msg.text });
          }
          return newLog;
        });
      } else if (msg.type === 'ai_transcript') {
        setTranscriptLog((log) => {
          const newLog = [...log];
          const last = newLog[newLog.length - 1];
          if (last?.who === 'ai') {
            newLog[newLog.length - 1] = { ...last, text: last.text + msg.text };
          } else {
            newLog.push({ who: 'ai', text: msg.text });
          }
          return newLog;
        });
      } else if (msg.type === 'turn_complete') {
        // FIX: Simple timeout instead of unreliable audio playback check
        // After turn_complete, give audio 2 seconds to finish playing
        console.log('[Live] turn_complete received - waiting 2s for audio to finish');
        setTimeout(() => {
          isBusyRef.current = false;
          setPhase('idle');
          setInterim('');
          console.log('[Live] Turn complete - ready for next turn');
        }, 2000);
      }
    };

    ws.onerror = (error) => {
      console.error('[Live] WebSocket error:', error);
      if (!connected) {
        liveConnectingRef.current = false;
        setUsingLive(false);
        teardownLive();
        startListeningClassic();
      }
    };

    ws.onclose = (event) => {
      clearTimeout(timeout);
      if (wsRef.current !== ws) return;

      // A Live session may be closed by Gemini or the network after a turn.
      // Reset every reference so the next connection starts from a clean state.
      wsRef.current = null;
      liveConnectingRef.current = false;
      isRecordingRef.current = false;
      isBusyRef.current = false;

      if (processorRef.current) {
        try { processorRef.current.disconnect(); } catch (e) {}
        processorRef.current = null;
      }
      if (micSourceRef.current) {
        try { micSourceRef.current.disconnect(); } catch (e) {}
        micSourceRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
        audioContextRef.current = null;
      }

        console.warn(`[Live] WebSocket closed (code ${event.code}). Reconnecting...`);
      if (isMountedRef.current) {
        setPhase('idle');
        setInterim('');
        window.setTimeout(() => {
          if (isMountedRef.current && !wsRef.current && !liveConnectingRef.current) {
            connectLive();
          }
        }, 250);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, WS_BASE, playPcmChunk, startMicCapture, startListeningClassic, teardownLive]);

  const startListeningLive = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      await connectLive();
    }
    setPhase('listening');
    // actual recording begins on mic button press (handleMicPress), not here
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectLive]);

  const handleMicPress = () => {
    console.log('[Mic] Button pressed - checking conditions...');
    console.log('[Mic] usingLive:', usingLive);
    console.log('[Mic] isBusyRef:', isBusyRef.current);
    console.log('[Mic] wsRef:', wsRef.current?.readyState, '(1=OPEN)');
    
    if (!usingLive) {
      console.log('[Mic] ❌ Not using Live mode');
      return;
    }
    if (isBusyRef.current) {
      console.log('[Mic] ❌ Still busy from previous turn');
      return;
    }
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.log('[Mic] ❌ WebSocket not open');
      return;
    }
    
    console.log('[Mic] ✅ All checks passed - starting turn');
    isRecordingRef.current = true;
    
    wsRef.current.send(JSON.stringify({ type: 'start_turn' }));
    setPhase('listening');
  };

  const stopLiveTurn = () => {
    if (!isRecordingRef.current) return;
    isRecordingRef.current = false;
    isBusyRef.current = true;
    
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop_turn' }));
    }
    setPhase('thinking');
  };

  const handleMicRelease = () => {
    stopLiveTurn();
  };

  // =====================================================
  // UI HANDLERS
  // =====================================================
  const startGreeting = () => {
    const firstName = patientName.trim().split(/\s+/)[0];
    const greeting = firstName ? `Hello, ${firstName}. How can I help you?` : 'Hello, how can I help you?';
    setNeedsGreeting(false);
    speak(greeting, 'ai', () => {
      if (usingLive) connectLive();
      else startListeningClassic();
    });
  };

  const handleDocumentSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const sid = localStorage.getItem('medclear_session_id');
    if (!sid) {
      setUploadMessage('You must sign in first to upload documents');
      return;
    }

    setUploadedFile(file);
    setUploadStatus('uploading');
    setUploadMessage('');

    try {
      const result = await uploadPatientDocument(file, sid);
      if (!result) {
        setUploadStatus('error');
        setUploadMessage('Upload failed - no response from server');
        return;
      }
      const success = result.success === true;
      if (success) {
        setUploadStatus('done');
        setUploadMessage('');
      } else {
        setUploadStatus('error');
        setUploadMessage(result.message || 'Unable to process this PDF. Please try another file.');
      }
    } catch (error) {
      console.error('Upload exception:', error);
      setUploadStatus('error');
      setUploadMessage('Unable to upload this PDF. Please try again.');
    }
  };

  const clearDocument = () => {
    setUploadedFile(null);
    setUploadStatus(null);
    setUploadMessage('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const activityLabel = {
    idle: needsGreeting ? 'Tap the microphone to begin' : usingLive ? 'Hold the mic to speak' : 'Ready when you are',
    listening: interim ? `Listening: "${interim}"` : usingLive ? 'Listening... (release to send)' : 'Listening...',
    thinking: 'Thinking...',
    speaking: 'Speaking...',
  }[phase];

  const submitTextQuestion = (event) => {
    event.preventDefault();
    const question = textQuestion.trim();
    if (!question || phase === 'thinking') return;

    stopAll();
    setTextQuestion('');
    setTranscriptLog((log) => [...log, { who: 'patient', text: question }]);

    if (usingLive && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'text', text: question }));
      isBusyRef.current = true;
      setPhase('thinking');
    } else {
      handlePatientText(question);
    }
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1, delayChildren: 0.2 } },
  };
  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] w-full bg-gradient-hero px-4 py-6 md:px-8">
      <motion.div className="max-w-4xl mx-auto space-y-6" variants={containerVariants} initial="hidden" animate="show">
        <AnimatePresence>
          {bookingNotification?.show && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="glass-lg border-l-4 border-green-500 p-4 bg-green-500/10"
            >
              <p className="text-green-300 font-medium">{bookingNotification.message}</p>
            </motion.div>
          )}
        </AnimatePresence>

        <motion.div variants={itemVariants} className="glass-lg p-8 text-center">
          <div className="flex justify-center mb-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-r from-purple-500 to-pink-500 flex items-center justify-center animate-float">
              <Volume2 size={32} className="text-white" />
            </div>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-gradient mb-2">Voice Assistant</h1>
          <p className="text-white/60 text-lg">Ask me anything about your health</p>

          <div className="flex justify-center mt-6">
            <div className="flex items-center gap-3 px-4 py-2 glass-sm">
              <div className={`status-dot ${phase === 'listening' ? 'status-dot-active' : phase === 'thinking' ? 'animate-pulse' : 'status-dot-inactive'}`} />
              <span className="text-sm font-medium text-white/80">{activityLabel}</span>
            </div>
          </div>
        </motion.div>

        <motion.div variants={itemVariants} className="glass-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Conversation</h2>
            {transcriptLog.length > 0 && (
              <button onClick={() => setTranscriptLog([])} className="btn btn-sm-secondary flex items-center gap-2">
                <RotateCcw size={14} />
                Clear
              </button>
            )}
          </div>

          <div className="space-y-4 max-h-96 overflow-y-auto">
            {transcriptLog.length === 0 ? (
              <p className="text-white/40 text-center py-8">Start a conversation to see the transcript here</p>
            ) : (
              <motion.div className="space-y-4" variants={containerVariants} initial="hidden" animate="show">
                {transcriptLog.map((entry, i) => (
                  <motion.div
                    key={i}
                    variants={itemVariants}
                    className={`flex gap-3 ${entry.who === 'ai' ? 'justify-start' : entry.who === 'system' ? 'justify-center' : 'justify-end'}`}
                  >
                    <div
                      className={`max-w-xs rounded-2xl px-4 py-3 ${
                        entry.who === 'ai'
                          ? 'glass text-white/80'
                          : entry.who === 'system'
                          ? 'glass text-white/60 text-xs'
                          : 'bg-gradient-to-r from-purple-500 to-pink-500 text-white'
                      }`}
                    >
                      <p className="text-sm">{entry.text}</p>
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </div>
        </motion.div>

        <motion.div variants={itemVariants}>
          <input ref={fileInputRef} type="file" accept="application/pdf" onChange={handleDocumentSelect} style={{ display: 'none' }} />

          {uploadedFile && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass p-4 flex items-center gap-4 mb-4">
              <div className="p-3 rounded-lg bg-white/10">
                {uploadStatus === 'uploading' ? (
                  <Loader2 size={20} className="animate-spin text-purple-400" />
                ) : (
                  <FileText size={20} className="text-purple-400" />
                )}
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-white">{uploadedFile.name}</p>
                <p className={`text-xs ${uploadStatus === 'error' ? 'text-red-400' : 'text-white/40'}`}>
                  {uploadStatus === 'uploading' ? 'Uploading...' : uploadStatus === 'error' ? uploadMessage : 'PDF ready'}
                </p>
              </div>
              <button onClick={clearDocument} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
                <X size={18} className="text-white/60" />
              </button>
            </motion.div>
          )}
        </motion.div>

        <motion.form onSubmit={submitTextQuestion} variants={itemVariants} className="glass-lg p-4 flex gap-3">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="p-3 hover:bg-white/10 rounded-xl transition-colors flex-shrink-0"
            title="Upload PDF"
          >
            <Plus size={20} className="text-purple-400" />
          </button>

          <input
            value={textQuestion}
            onChange={(e) => setTextQuestion(e.target.value)}
            placeholder="Ask anything..."
            disabled={phase === 'thinking'}
            className="input-glass flex-1"
          />

          {needsGreeting ? (
            <button
              type="button"
              onClick={startGreeting}
              disabled={phase === 'thinking'}
              className="btn btn-sm-primary flex items-center gap-2 flex-shrink-0"
              title="Start"
            >
              <Mic size={18} />
            </button>
          ) : usingLive ? (
            <button
              type="button"
              onMouseDown={handleMicPress}
              onMouseUp={handleMicRelease}
              onMouseLeave={handleMicRelease}
              onTouchStart={handleMicPress}
              onTouchEnd={handleMicRelease}
              disabled={phase === 'thinking'}
              className={`btn btn-sm-primary flex items-center gap-2 flex-shrink-0 ${phase === 'listening' ? 'ring-2 ring-pink-400' : ''}`}
              title="Hold to speak"
            >
              <Mic size={18} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => (phase === 'listening' ? stopAll() : startListeningClassic())}
              disabled={phase === 'thinking'}
              className="btn btn-sm-primary flex items-center gap-2 flex-shrink-0"
              title={phase === 'listening' ? 'Stop' : 'Speak'}
            >
              <Mic size={18} />
            </button>
          )}

          <button
            type="submit"
            disabled={!textQuestion.trim() || phase === 'thinking'}
            className="btn btn-sm-primary flex items-center gap-2 flex-shrink-0"
          >
            <Send size={18} />
          </button>
        </motion.form>
      </motion.div>
    </div>
  );
}
