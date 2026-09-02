import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, RotateCcw, Plus, FileText, Loader2, X, Send, Volume2 } from 'lucide-react';
import { askAICore } from '../aiCore/api';
import { uploadPatientDocument } from '../patientDocs/api';

const FONT_LINK = 'https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap';

function toSpeechLocale(languageName) {
  if (!languageName) return 'en-US';
  const map = {
    english: 'en-US',
    hindi: 'hi-IN',
    spanish: 'es-ES',
    french: 'fr-FR',
    arabic: 'ar-SA',
    bengali: 'bn-IN',
    tamil: 'ta-IN',
    telugu: 'te-IN',
    marathi: 'mr-IN',
    gujarati: 'gu-IN',
    punjabi: 'pa-IN',
    urdu: 'ur-IN',
    mandarin: 'zh-CN',
    chinese: 'zh-CN',
    portuguese: 'pt-BR',
    german: 'de-DE',
    japanese: 'ja-JP',
    russian: 'ru-RU',
  };
  const key = languageName.toLowerCase().trim();
  for (const name in map) {
    if (key.includes(name)) return map[name];
  }
  return 'en-US';
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

  const recognitionRef = useRef(null);
  const keepAliveRef = useRef(null);
  const voicesRef = useRef([]);
  const fileInputRef = useRef(null);
  const handlePatientTextRef = useRef(null);

  let fullSentence = '';
  let accumulatedTTSBuffer = '';
  let hasStartedSpeaking = false;

  useEffect(() => {
    const link = document.createElement('link');
    link.href = FONT_LINK;
    link.rel = 'stylesheet';
    document.head.appendChild(link);

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || !window.speechSynthesis) {
      setPhase('unsupported');
    }

    const loadVoices = () => {
      voicesRef.current = window.speechSynthesis.getVoices();
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      document.head.removeChild(link);
      if (recognitionRef.current) recognitionRef.current.abort();
      window.speechSynthesis?.cancel();
      clearInterval(keepAliveRef.current);
    };
  }, []);

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

  const startListening = useCallback(async () => {
    try {
      setPhase('listening');
      setInterim('Recording...');
      console.log('[Voice] Requesting microphone permission...');
      
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: true,
          noiseSuppression: true,
          echoCancellation: true,
          sampleRate: 16000
        }
      });
      
      console.log('[Voice] Microphone access granted');
      
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/wav' });
      const audioChunks = [];
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };
      
      mediaRecorder.onstop = async () => {
        console.log('[Voice] Recording stopped, transcribing...');
        setInterim('Transcribing...');
        
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
        
        try {
          // Create audio blob
          const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
          console.log(`[Voice] Audio blob size: ${audioBlob.size} bytes`);
          
          // Send to backend Whisper API
          const formData = new FormData();
          formData.append('file', audioBlob, 'audio.wav');
          
          const response = await fetch('/api/v1/transcribe', {
            method: 'POST',
            body: formData
          });
          
          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Transcription failed');
          }
          
          const data = await response.json();
          console.log(`[Voice] Transcribed: "${data.text}" (confidence: ${(data.confidence * 100).toFixed(0)}%)`);
          
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
          speak('I couldn\'t understand that. Could you please try again?', 'ai', () => startListening());
        }
      };
      
      // Start recording (5-10 seconds max)
      mediaRecorder.start();
      console.log('[Voice] Recording started...');
      
      // Stop after 10 seconds (user can click button to stop earlier)
      const timeout = setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          console.log('[Voice] Auto-stopping after 10 seconds');
          mediaRecorder.stop();
        }
      }, 10000);
      
      // Store timeout and mediaRecorder for manual stop
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
      console.log('[Phase Debug] Set to thinking at', Date.now());
      let fullSentence = '';
      let accumulatedTTSBuffer = '';
      let hasStartedSpeaking = false;

      try {
        const startListeningAfterSpeech = () => {
          if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
            window.setTimeout(startListeningAfterSpeech, 120);
            return;
          }

          const isClosingStatement = /(goodbye|have a (wonderful|great|good) day|bye\b|reach out if you need|take care|thank you|thanks for|appreciate|welcome)/i.test(
            fullSentence
          );

          if (isClosingStatement) {
            setPhase('idle');
            setNeedsGreeting(true);
          } else {
            startListening();
          }
        };

        const { reply, resolved, language, isBookingSuccess } = await askAICore(heardText, { documentMode: uploadStatus === 'done' }, (newWord) => {
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
        });

        if (isBookingSuccess) {
          setBookingNotification({
            show: true,
            message: 'Appointment booked successfully!',
          });

          setTimeout(() => setBookingNotification(null), 5000);
        }

        if (accumulatedTTSBuffer.trim()) {
          speak(accumulatedTTSBuffer.trim(), 'ai', () => {
            startListeningAfterSpeech();
          }, 'en-US', true);
        } else {
          startListeningAfterSpeech();
        }
      } catch (err) {
        console.error('Unable to get an AI-core response:', err);
        speak('I\'m having trouble reaching the assistant right now. Please try again in a moment.', 'ai', () => startListening());
      }
    },
    [speak, startListening, uploadStatus]
  );

  useEffect(() => {
    handlePatientTextRef.current = handlePatientText;
  }, [handlePatientText]);

  const startGreeting = () => {
    const firstName = patientName.trim().split(/\s+/)[0];
    const greeting = firstName ? `Hello, ${firstName}. How can I help you?` : 'Hello, how can I help you?';
    setNeedsGreeting(false);
    speak(greeting, 'ai', startListening);
  };

  const stopAll = () => {
    window.speechSynthesis.cancel();
    
    // Handle both old Web Speech API and new MediaRecorder
    if (recognitionRef.current) {
      if (recognitionRef.current.mediaRecorder) {
        // New: MediaRecorder (Whisper)
        const { mediaRecorder, timeout } = recognitionRef.current;
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
        clearTimeout(timeout);
      } else if (recognitionRef.current.abort) {
        // Old: Web Speech API
        recognitionRef.current.abort();
      }
    }
    
    setPhase('idle');
    setInterim('');
  };

  const handleDocumentSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const sessionId = localStorage.getItem('medclear_session_id');
    if (!sessionId) {
      setUploadMessage('You must sign in first to upload documents');
      return;
    }

    setUploadedFile(file);
    setUploadStatus('uploading');
    setUploadMessage('');

    try {
      const result = await uploadPatientDocument(file, sessionId);

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
    idle: needsGreeting ? 'Tap the microphone to begin' : 'Ready when you are',
    listening: interim ? `Listening: "${interim}"` : 'Listening...',
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
    handlePatientText(question);
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] w-full bg-gradient-hero px-4 py-6 md:px-8">
      <motion.div
        className="max-w-4xl mx-auto space-y-6"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {/* Booking Notification */}
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

        {/* Header */}
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

        {/* Transcript */}
        <motion.div variants={itemVariants} className="glass-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Conversation</h2>
            {transcriptLog.length > 0 && (
              <button
                onClick={() => setTranscriptLog([])}
                className="btn btn-sm-secondary flex items-center gap-2"
              >
                <RotateCcw size={14} />
                Clear
              </button>
            )}
          </div>

          <div className="space-y-4 max-h-96 overflow-y-auto">
            {transcriptLog.length === 0 ? (
              <p className="text-white/40 text-center py-8">Start a conversation to see the transcript here</p>
            ) : (
              <motion.div
                className="space-y-4"
                variants={containerVariants}
                initial="hidden"
                animate="show"
              >
                {transcriptLog.map((entry, i) => (
                  <motion.div key={i} variants={itemVariants} className={`flex gap-3 ${entry.who === 'ai' ? 'justify-start' : 'justify-end'}`}>
                    <div
                      className={`max-w-xs rounded-2xl px-4 py-3 ${
                        entry.who === 'ai'
                          ? 'glass text-white/80'
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

        {/* File Upload */}
        <motion.div variants={itemVariants}>
          <input ref={fileInputRef} type="file" accept="application/pdf" onChange={handleDocumentSelect} style={{ display: 'none' }} />

          {uploadedFile && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass p-4 flex items-center gap-4 mb-4"
            >
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

        {/* Input Area */}
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

          <button
            type="button"
            onClick={() => (phase === 'listening' ? stopAll() : needsGreeting ? startGreeting() : startListening())}
            disabled={phase === 'thinking'}
            className="btn btn-sm-primary flex items-center gap-2 flex-shrink-0"
            title={phase === 'listening' ? 'Stop' : needsGreeting ? 'Start' : 'Speak'}
          >
            <Mic size={18} />
          </button>

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
