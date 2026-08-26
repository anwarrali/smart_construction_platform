/**
 * Microphone capture with immediate on-screen feedback.
 *
 * The backend owns the authoritative transcript: it is the only side with the
 * audio, the project context, and the authorization to act. But a round trip
 * that starts when the engineer stops speaking means the screen shows nothing
 * at all while they talk, and a voice interface that looks inert while you use
 * it feels broken however fast the answer eventually arrives.
 *
 * So there are two transcripts, deliberately:
 *
 *   * a **live preview** from the browser's own recognizer, printed as the
 *     words are spoken, worth nothing except reassurance — it is never sent
 *     anywhere and never drives an action;
 *   * the **real transcript**, produced server-side from the recorded audio,
 *     which is what the interpretation and every mutation are built on.
 *
 * Where the browser has no recognizer (Firefox, most of Safari) the preview is
 * simply absent and the flow is unchanged. That is why the preview may never
 * become load-bearing: on a meaningful share of devices it does not exist.
 *
 * The recorded audio is the same in both cases, so nothing about correctness
 * depends on which browser this runs in.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type CaptureState = "idle" | "starting" | "recording" | "stopping" | "error";

/** Minimal shape of the vendor-prefixed Web Speech API we actually use. */
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}

type RecognitionConstructor = new () => SpeechRecognitionLike;

const recognitionConstructor = (): RecognitionConstructor | undefined => {
  if (typeof window === "undefined") return undefined;
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return scope.SpeechRecognition || scope.webkitSpeechRecognition;
};

/**
 * Pick a recording container the browser can produce *and* the backend
 * accepts. Order matters: the first supported entry wins, and each carries the
 * extension the server validates the byte signature against.
 */
const CANDIDATE_FORMATS: Array<{ mimeType: string; extension: string }> = [
  { mimeType: "audio/webm;codecs=opus", extension: "webm" },
  { mimeType: "audio/webm", extension: "webm" },
  { mimeType: "audio/mp4", extension: "m4a" },
];

const chooseFormat = () => {
  const supported =
    typeof MediaRecorder !== "undefined"
      ? CANDIDATE_FORMATS.find((format) => MediaRecorder.isTypeSupported(format.mimeType))
      : undefined;
  return supported || CANDIDATE_FORMATS[0];
};

export interface VoiceCaptureResult {
  audio: Blob;
  filename: string;
  durationSeconds: number;
  /** Browser-side preview text, if this browser produced any. */
  previewTranscript: string;
  timings: {
    micStartMs: number;
    recordingMs: number;
    firstPartialTranscriptMs?: number;
  };
}

export interface UseVoiceCapture {
  state: CaptureState;
  /** Words recognized locally so far. Display only. */
  previewTranscript: string;
  /** Seconds elapsed in the current recording. */
  elapsedSeconds: number;
  /** 0–1 input level, for the listening animation. */
  level: number;
  supported: boolean;
  /** True when this browser can show a live preview at all. */
  previewSupported: boolean;
  error: string;
  start: () => Promise<void>;
  stop: () => Promise<VoiceCaptureResult | null>;
  cancel: () => void;
}

interface Options {
  /** BCP-47 tag for the live preview only; the server detects language itself. */
  language?: string;
  maxSeconds?: number;
}

export const useVoiceCapture = (options: Options = {}): UseVoiceCapture => {
  const { language = "en-US", maxSeconds = 180 } = options;

  const [state, setState] = useState<CaptureState>("idle");
  const [previewTranscript, setPreviewTranscript] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState("");

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalPreviewRef = useRef("");
  const audioContextRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const tickRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const micStartMsRef = useRef(0);
  const firstPartialRef = useRef<number | undefined>(undefined);
  const formatRef = useRef(chooseFormat());

  const supported =
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== "undefined";
  const previewSupported = Boolean(recognitionConstructor());

  const teardown = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (tickRef.current !== null) window.clearInterval(tickRef.current);
    tickRef.current = null;
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    void audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    setLevel(0);
  }, []);

  // A recording left running when the page navigates away keeps the microphone
  // indicator lit, which users reasonably read as the app listening to them.
  useEffect(() => teardown, [teardown]);

  const startLevelMeter = useCallback((stream: MediaStream) => {
    try {
      const context = new AudioContext();
      audioContextRef.current = context;
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      context.createMediaStreamSource(stream).connect(analyser);
      const buffer = new Uint8Array(analyser.frequencyBinCount);
      const sample = () => {
        analyser.getByteTimeDomainData(buffer);
        let sum = 0;
        for (const value of buffer) sum += (value - 128) ** 2;
        setLevel(Math.min(1, Math.sqrt(sum / buffer.length) / 40));
        rafRef.current = requestAnimationFrame(sample);
      };
      sample();
    } catch {
      // A level meter is decoration. Losing it must not lose the recording.
    }
  }, []);

  const startPreview = useCallback(() => {
    const Recognition = recognitionConstructor();
    if (!Recognition) return;
    try {
      const recognition = new Recognition();
      recognition.lang = language;
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.onresult = (event) => {
        if (firstPartialRef.current === undefined) {
          firstPartialRef.current = Math.round(performance.now() - startedAtRef.current);
        }
        let interim = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const text = result[0]?.transcript || "";
          if (result.isFinal) finalPreviewRef.current += text;
          else interim += text;
        }
        setPreviewTranscript((finalPreviewRef.current + interim).trim());
      };
      // A recognizer that dies mid-sentence must not surface as an error: the
      // recording it was previewing is still perfectly good.
      recognition.onerror = () => undefined;
      recognition.onend = () => undefined;
      recognition.start();
      recognitionRef.current = recognition;
    } catch {
      recognitionRef.current = null;
    }
  }, [language]);

  const start = useCallback(async () => {
    if (!supported) {
      setError("unsupported");
      setState("error");
      return;
    }
    setError("");
    setPreviewTranscript("");
    finalPreviewRef.current = "";
    firstPartialRef.current = undefined;
    setElapsedSeconds(0);
    setState("starting");

    const requestedAt = performance.now();
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch {
      setError("permission");
      setState("error");
      return;
    }
    micStartMsRef.current = Math.round(performance.now() - requestedAt);
    streamRef.current = stream;

    const format = chooseFormat();
    formatRef.current = format;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream, { mimeType: format.mimeType });
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorderRef.current = recorder;
    startedAtRef.current = performance.now();
    recorder.start();

    startLevelMeter(stream);
    startPreview();
    setState("recording");

    tickRef.current = window.setInterval(() => {
      const seconds = Math.floor((performance.now() - startedAtRef.current) / 1000);
      setElapsedSeconds(seconds);
      // Stopping at the server's own limit turns a 413 after a long upload
      // into a bounded recording the engineer can still send.
      if (seconds >= maxSeconds) recorderRef.current?.stop();
    }, 250);
  }, [maxSeconds, startLevelMeter, startPreview, supported]);

  const stop = useCallback(
    () =>
      new Promise<VoiceCaptureResult | null>((resolve) => {
        const recorder = recorderRef.current;
        if (!recorder || recorder.state === "inactive") {
          teardown();
          setState("idle");
          resolve(null);
          return;
        }
        setState("stopping");
        const recordingMs = Math.round(performance.now() - startedAtRef.current);
        recorder.onstop = () => {
          const format = formatRef.current;
          const audio = new Blob(chunksRef.current, { type: format.mimeType.split(";")[0] });
          const preview = previewTranscript;
          teardown();
          setState("idle");
          resolve(
            audio.size === 0
              ? null
              : {
                  audio,
                  filename: `voice-${Date.now()}.${format.extension}`,
                  durationSeconds: Math.max(1, Math.round(recordingMs / 1000)),
                  previewTranscript: preview,
                  timings: {
                    micStartMs: micStartMsRef.current,
                    recordingMs,
                    firstPartialTranscriptMs: firstPartialRef.current,
                  },
                },
          );
        };
        recorder.stop();
      }),
    [previewTranscript, teardown],
  );

  const cancel = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    chunksRef.current = [];
    teardown();
    setPreviewTranscript("");
    setElapsedSeconds(0);
    setState("idle");
  }, [teardown]);

  return {
    state,
    previewTranscript,
    elapsedSeconds,
    level,
    supported,
    previewSupported,
    error,
    start,
    stop,
    cancel,
  };
};
