import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../api/client';
import { useLanguage } from '../../context/LanguageContext';
import { Mic, MicOff, X, Send, Pause, Play, Square, RotateCcw, Volume2, ExternalLink, Headphones } from 'lucide-react';
import { MarkdownText } from '../common/MarkdownText';

type Lang = 'en' | 'te' | 'hi';
type LangChoice = 'auto' | Lang;

interface Citation { type: 'guide' | 'live' | 'document'; title?: string; path?: string; section?: string; page?: number }
interface Turn {
  role: 'user' | 'assistant';
  text: string;
  speech?: string;
  language?: Lang;
  citations?: Citation[];
  navigate_to?: string | null;
  grounding?: string;
  error?: boolean;
}

const SPEECH_LOCALE: Record<Lang, string> = { en: 'en-IN', te: 'te-IN', hi: 'hi-IN' };
const LANG_NAME: Record<LangChoice, string> = { auto: 'Auto', en: 'English', te: 'తెలుగు', hi: 'हिंदी' };

const MIC_ERRORS: Record<string, string> = {
  'not-allowed': 'Microphone permission was denied. Allow microphone access from the browser address bar, or type your question.',
  'service-not-allowed': 'Speech recognition is blocked in this browser. Type your question instead.',
  'audio-capture': 'No microphone was found. Connect a microphone, or type your question.',
  network: 'Speech recognition needs a network connection to the browser speech service. Check the connection, or type your question.',
  'language-not-supported': 'This browser cannot recognise speech in the selected language. Choose another language, or type your question.',
  'no-speech': 'No speech was heard. Press the microphone and speak again.',
  aborted: ''
};

function detectLang(text: string): Lang {
  if (/[ఀ-౿]/.test(text)) return 'te';
  if (/[ऀ-ॿ]/.test(text)) return 'hi';
  return 'en';
}

function getRecognitionCtor(): any {
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export const VoiceAssistant: React.FC = () => {
  const navigate = useNavigate();
  const { language: uiLanguage } = useLanguage();
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<LangChoice>('auto');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [interim, setInterim] = useState('');
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState<'idle' | 'speaking' | 'paused'>('idle');
  const [autoSpeak, setAutoSpeak] = useState(true);
  const recognitionRef = useRef<any>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const sttSupported = !!getRecognitionCtor();
  const ttsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  const recognitionLang: Lang = choice === 'auto' ? ((['en', 'te', 'hi'].includes(uiLanguage) ? uiLanguage : 'en') as Lang) : choice;

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, interim]);

  useEffect(() => () => {
    recognitionRef.current?.abort?.();
    if (ttsSupported) window.speechSynthesis.cancel();
  }, [ttsSupported]);

  const stopSpeaking = useCallback(() => {
    if (!ttsSupported) return;
    window.speechSynthesis.cancel();
    setSpeaking('idle');
  }, [ttsSupported]);

  const speak = useCallback((text: string, lang: Lang) => {
    if (!ttsSupported || !text) return;
    window.speechSynthesis.cancel();
    const voices = window.speechSynthesis.getVoices();
    const voice = voices.find(v => v.lang?.toLowerCase().startsWith(lang)) || null;
    if (!voice && lang !== 'en') {
      setNotice(`No ${LANG_NAME[lang]} voice is installed in this browser, so the answer is shown as text only.`);
      return;
    }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = SPEECH_LOCALE[lang];
    if (voice) u.voice = voice;
    u.rate = 1;
    u.onend = () => setSpeaking('idle');
    u.onerror = () => setSpeaking('idle');
    setSpeaking('speaking');
    window.speechSynthesis.speak(u);
  }, [ttsSupported]);

  const togglePause = () => {
    if (!ttsSupported) return;
    if (speaking === 'speaking') { window.speechSynthesis.pause(); setSpeaking('paused'); }
    else if (speaking === 'paused') { window.speechSynthesis.resume(); setSpeaking('speaking'); }
  };

  const ask = useCallback(async (question: string, mode: 'voice' | 'text') => {
    const q = question.trim();
    if (!q || busy) return;
    setNotice(null);
    stopSpeaking();
    const history = turns.slice(-6).map(t => ({ role: t.role, text: t.text }));
    setTurns(prev => [...prev, { role: 'user', text: q, language: detectLang(q) }]);
    setInput('');
    setBusy(true);
    try {
      const language = choice === 'auto' ? 'auto' : choice;
      const res = await api.post('/assistant/query', { question: q, language, history, input_mode: mode });
      const d = res.data;
      setTurns(prev => [...prev, {
        role: 'assistant', text: d.answer, speech: d.speech, language: d.language, citations: d.citations,
        navigate_to: d.navigate_to, grounding: d.grounding
      }]);
      if (autoSpeak && d.speech) speak(d.speech, d.language);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const msg = !e?.response
        ? 'The assistant could not reach the server. Check the network connection and try again.'
        : typeof detail === 'string' ? detail : `The assistant failed (HTTP ${e.response.status}). Try again.`;
      setTurns(prev => [...prev, { role: 'assistant', text: msg, error: true }]);
    } finally {
      setBusy(false);
    }
  }, [busy, choice, turns, autoSpeak, speak, stopSpeaking]);

  const startListening = () => {
    const Ctor = getRecognitionCtor();
    if (!Ctor) {
      setNotice('Speech recognition is not available in this browser (use Chrome or Edge). You can type your question below.');
      return;
    }
    stopSpeaking();
    setNotice(null);
    const rec = new Ctor();
    rec.lang = SPEECH_LOCALE[recognitionLang];
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    let finalText = '';
    rec.onresult = (event: any) => {
      let partial = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else partial += r[0].transcript;
      }
      setInterim(partial || finalText);
    };
    rec.onerror = (event: any) => {
      const msg = MIC_ERRORS[event.error] ?? `Speech recognition error (${event.error}). Type your question instead.`;
      if (msg) setNotice(msg);
    };
    rec.onend = () => {
      setListening(false);
      setInterim('');
      if (finalText.trim()) ask(finalText, 'voice');
    };
    try {
      rec.start();
      recognitionRef.current = rec;
      setListening(true);
    } catch {
      setNotice('The microphone could not be started. Try again, or type your question.');
    }
  };

  const stopListening = () => {
    recognitionRef.current?.stop?.();
  };

  const reset = () => {
    recognitionRef.current?.abort?.();
    stopSpeaking();
    setTurns([]);
    setNotice(null);
    setInterim('');
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-blue-700 hover:bg-blue-800 text-white shadow-lg flex items-center justify-center focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-300"
        aria-label="Open the FIR VisionAI voice assistant"
        title="Voice assistant"
      >
        <Headphones className="w-6 h-6" />
      </button>
    );
  }

  return (
    <section
      className="fixed z-50 bottom-0 right-0 sm:bottom-5 sm:right-5 w-full sm:w-[420px] h-[85vh] sm:h-[600px] bg-white sm:rounded-2xl shadow-2xl border border-slate-200 flex flex-col"
      aria-label="FIR VisionAI voice assistant"
      role="dialog"
    >
      <header className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-blue-900 text-white sm:rounded-t-2xl">
        <div>
          <h2 className="text-sm font-bold">FIR VisionAI Assistant</h2>
          <p className="text-[10px] text-blue-200">Ask how to use the application, or about your jurisdiction's live status</p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={reset} className="p-1.5 rounded hover:bg-blue-800" aria-label="Reset conversation" title="Reset conversation">
            <RotateCcw className="w-4 h-4" />
          </button>
          <button onClick={() => { reset(); setOpen(false); }} className="p-1.5 rounded hover:bg-blue-800" aria-label="Close assistant">
            <X className="w-4 h-4" />
          </button>
        </div>
      </header>

      <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-100 text-xs">
        <label htmlFor="va-lang" className="font-semibold text-slate-600">Language</label>
        <select id="va-lang" value={choice} onChange={e => setChoice(e.target.value as LangChoice)}
                className="border border-slate-300 rounded px-2 py-1 text-xs">
          {(['auto', 'en', 'te', 'hi'] as LangChoice[]).map(l => <option key={l} value={l}>{LANG_NAME[l]}</option>)}
        </select>
        <label className="ml-auto flex items-center gap-1 text-slate-600">
          <input type="checkbox" checked={autoSpeak} onChange={e => setAutoSpeak(e.target.checked)} />
          Speak answers
        </label>
      </div>
      {choice === 'auto' && (
        <p className="px-4 pt-1 text-[10px] text-slate-500">
          Auto answers in the language you speak or type; speech is recognised in {LANG_NAME[recognitionLang]} (the header language).
        </p>
      )}

      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3" aria-live="polite">
        {turns.length === 0 && (
          <div className="text-xs text-slate-500 space-y-2">
            <p>Try asking:</p>
            <ul className="list-disc pl-4 space-y-1">
              <li>How do I register a new FIR?</li>
              <li>How many pending drafts do I have?</li>
              <li>డాష్‌బోర్డ్‌లో Under Review అంటే ఏమిటి?</li>
              <li>नॉलेज बेस में दस्तावेज़ कैसे खोजें?</li>
            </ul>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={t.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[88%] rounded-xl px-3 py-2 text-sm ${
              t.role === 'user' ? 'bg-blue-600 text-white' : t.error ? 'bg-red-50 text-red-800 border border-red-200' : 'bg-slate-100 text-slate-800'
            }`}>
              {t.role === 'user' ? <p className="whitespace-pre-wrap">{t.text}</p> : <MarkdownText text={t.text} />}
              {t.role === 'assistant' && !t.error && (
                <div className="mt-2 space-y-1">
                  {t.citations && t.citations.length > 0 && (
                    <div className="text-[10px] text-slate-500">
                      Source: {t.citations.map((c, j) => (
                        <span key={j} className="mr-1">
                          {c.type === 'live' ? '● live data — ' : c.type === 'guide' ? 'app guide — ' : ''}
                          {c.title}{c.section ? `, ${c.section}` : ''}{c.page ? `, p. ${c.page}` : ''}{j < t.citations!.length - 1 ? ';' : ''}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="flex gap-2">
                    {t.speech && ttsSupported && (
                      <button onClick={() => speak(t.speech!, t.language || 'en')} className="text-[10px] text-blue-700 flex items-center gap-1"
                              aria-label="Play this answer aloud">
                        <Volume2 className="w-3 h-3" /> Play
                      </button>
                    )}
                    {t.navigate_to && (
                      <button onClick={() => navigate(t.navigate_to!)} className="text-[10px] text-blue-700 flex items-center gap-1"
                              aria-label="Open the related page">
                        <ExternalLink className="w-3 h-3" /> Open page
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {interim && <div className="text-xs italic text-slate-500">“{interim}”</div>}
        {busy && <div className="text-xs text-slate-500">Thinking…</div>}
      </div>

      {notice && <div className="mx-4 mb-2 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded p-2" role="alert">{notice}</div>}

      {speaking !== 'idle' && (
        <div className="flex items-center gap-2 px-4 pb-2 text-xs">
          <span className="text-slate-500">Speaking…</span>
          <button onClick={togglePause} className="px-2 py-1 rounded bg-slate-100 flex items-center gap-1" aria-label={speaking === 'paused' ? 'Resume speech' : 'Pause speech'}>
            {speaking === 'paused' ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
            {speaking === 'paused' ? 'Resume' : 'Pause'}
          </button>
          <button onClick={stopSpeaking} className="px-2 py-1 rounded bg-slate-100 flex items-center gap-1" aria-label="Stop speech">
            <Square className="w-3 h-3" /> Stop
          </button>
        </div>
      )}

      <form onSubmit={e => { e.preventDefault(); ask(input, 'text'); }} className="flex items-center gap-2 px-4 py-3 border-t border-slate-200">
        <button
          type="button"
          onClick={listening ? stopListening : startListening}
          disabled={busy}
          className={`w-10 h-10 shrink-0 rounded-full flex items-center justify-center ${listening ? 'bg-red-600 text-white animate-pulse' : 'bg-blue-700 text-white'} disabled:opacity-50`}
          aria-label={listening ? 'Stop listening' : 'Start listening'}
          aria-pressed={listening}
          title={sttSupported ? (listening ? 'Stop listening' : 'Speak your question') : 'Speech recognition not available in this browser'}
        >
          {listening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
        </button>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder={listening ? 'Listening…' : 'Type a question'}
          aria-label="Type your question"
          className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm"
          maxLength={1000}
        />
        <button type="submit" disabled={busy || !input.trim()} className="w-10 h-10 shrink-0 rounded-lg bg-slate-800 text-white flex items-center justify-center disabled:opacity-40" aria-label="Send question">
          <Send className="w-4 h-4" />
        </button>
      </form>
      <p className="px-4 pb-2 text-[9px] text-slate-400">
        Speech is transcribed by your browser's speech service; no audio is stored. The assistant explains and looks up information; it never approves, submits or deletes records.
      </p>
    </section>
  );
};
