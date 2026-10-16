import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, X, Shield } from 'lucide-react';

interface LogoZoomModalProps {
  isOpen: boolean;
  onClose: () => void;
  src?: string;
  alt?: string;
  title?: string;
  subtitle?: string;
}

export const LogoZoomModal: React.FC<LogoZoomModalProps> = ({
  isOpen,
  onClose,
  src = '/assets/andhra-pradesh-government-logo.jpg',
  alt = 'Government of Andhra Pradesh Official Emblem',
  title = 'Government of Andhra Pradesh',
  subtitle = 'Official State Emblem • Prohibition & Excise Department'
}) => {
  const [scale, setScale] = useState<number>(1);
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const containerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const initialTouchDistanceRef = useRef<number | null>(null);
  const initialTouchScaleRef = useRef<number>(1);

  const MIN_SCALE = 0.5;
  const MAX_SCALE = 3.5;
  const STEP = 0.25;

  const handleZoomIn = useCallback(() => {
    setScale((prev) => Math.min(Number((prev + STEP).toFixed(2)), MAX_SCALE));
  }, []);

  const handleZoomOut = useCallback(() => {
    setScale((prev) => Math.max(Number((prev - STEP).toFixed(2)), MIN_SCALE));
  }, []);

  const handleReset = useCallback(() => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
  }, []);

  // Prevent background scrolling while modal is open
  useEffect(() => {
    if (!isOpen) return;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Focus close button on open
    setTimeout(() => {
      closeBtnRef.current?.focus();
    }, 50);

    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [isOpen]);

  // Reset scale and position whenever modal opens
  useEffect(() => {
    if (isOpen) {
      setScale(1);
      setPosition({ x: 0, y: 0 });
    }
  }, [isOpen]);

  // Keyboard navigation: Escape to close, +/- to zoom, 0/R to reset
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        handleZoomIn();
      } else if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        handleZoomOut();
      } else if (e.key === '0' || e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        handleReset();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, handleZoomIn, handleZoomOut, handleReset]);

  // Mouse wheel zoom listener (attached non-passively to container)
  useEffect(() => {
    if (!isOpen) return;
    const container = containerRef.current;
    if (!container) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (e.deltaY < 0) {
        setScale((prev) => Math.min(Number((prev + 0.15).toFixed(2)), MAX_SCALE));
      } else {
        setScale((prev) => Math.max(Number((prev - 0.15).toFixed(2)), MIN_SCALE));
      }
    };

    container.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      container.removeEventListener('wheel', onWheel);
    };
  }, [isOpen]);

  // Touch pinch-to-zoom handlers
  const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
    if (e.touches.length === 2) {
      const dist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      initialTouchDistanceRef.current = dist;
      initialTouchScaleRef.current = scale;
    } else if (e.touches.length === 1 && scale > 1) {
      setIsDragging(true);
      setDragStart({
        x: e.touches[0].clientX - position.x,
        y: e.touches[0].clientY - position.y
      });
    }
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
    if (e.touches.length === 2 && initialTouchDistanceRef.current !== null) {
      const currentDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const ratio = currentDist / initialTouchDistanceRef.current;
      const newScale = Math.min(
        Math.max(Number((initialTouchScaleRef.current * ratio).toFixed(2)), MIN_SCALE),
        MAX_SCALE
      );
      setScale(newScale);
    } else if (e.touches.length === 1 && isDragging && scale > 1) {
      setPosition({
        x: e.touches[0].clientX - dragStart.x,
        y: e.touches[0].clientY - dragStart.y
      });
    }
  };

  const handleTouchEnd = () => {
    initialTouchDistanceRef.current = null;
    setIsDragging(false);
  };

  // Mouse drag when zoomed in
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (scale <= 1) return;
    setIsDragging(true);
    setDragStart({
      x: e.clientX - position.x,
      y: e.clientY - position.y
    });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isDragging || scale <= 1) return;
    setPosition({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  if (!isOpen) return null;

  const zoomPercent = Math.round(scale * 100);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="logo-zoom-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/85 backdrop-blur-md transition-opacity select-none"
      onClick={onClose}
    >
      {/* Centered Modal Card */}
      <div
        className="relative w-full max-w-4xl max-h-[92vh] flex flex-col bg-slate-900 border border-emerald-500/40 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Bar */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-3.5 bg-gradient-to-r from-[#0f5132] via-slate-900 to-slate-900 text-white border-b border-emerald-500/30">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-400/30 flex items-center justify-center text-amber-300">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <h2 id="logo-zoom-modal-title" className="text-sm sm:text-base font-bold tracking-tight text-emerald-50">
                {title}
              </h2>
              <p className="text-[11px] sm:text-xs text-emerald-200/80">
                {subtitle}
              </p>
            </div>
          </div>

          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            title="Close preview (Esc)"
            aria-label="Close preview"
            className="p-1.5 sm:p-2 text-slate-300 hover:text-white bg-slate-800/80 hover:bg-red-600/80 rounded-lg transition-colors border border-slate-700 hover:border-red-500 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-900"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Zoomable Image Viewport */}
        <div
          ref={containerRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          className={`relative flex-1 flex items-center justify-center min-h-[320px] max-h-[62vh] sm:max-h-[68vh] p-4 sm:p-8 bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 overflow-hidden ${
            scale > 1 ? (isDragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-default'
          }`}
        >
          {/* Subtle grid watermark background */}
          <div className="absolute inset-0 bg-[radial-gradient(#10b981_1px,transparent_1px)] [background-size:24px_24px] opacity-10 pointer-events-none" />

          <div
            style={{
              transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
              transformOrigin: 'center center',
              transition: isDragging ? 'none' : 'transform 180ms ease-out'
            }}
            className="relative flex items-center justify-center max-w-full max-h-full"
          >
            <img
              src={src}
              alt={alt}
              draggable={false}
              className="max-h-[50vh] sm:max-h-[58vh] w-auto max-w-[85vw] sm:max-w-[70vw] object-contain drop-shadow-[0_10px_25px_rgba(0,0,0,0.6)] rounded-lg pointer-events-none select-none"
            />
          </div>
        </div>

        {/* Interactive Controls Deck */}
        <div className="px-4 sm:px-6 py-3 bg-slate-950/95 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          {/* Instructions Hint */}
          <div className="text-[11px] text-slate-400 hidden sm:flex items-center gap-2">
            <span className="inline-block px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 font-mono text-[10px] text-slate-300">
              Scroll / Pinch to Zoom
            </span>
            {scale > 1 && (
              <span className="inline-block px-1.5 py-0.5 bg-emerald-950/60 text-emerald-300 rounded border border-emerald-800/60 font-mono text-[10px]">
                Drag to Pan
              </span>
            )}
          </div>

          {/* Controls Group */}
          <div className="flex items-center space-x-2 mx-auto sm:mx-0">
            {/* Zoom Out Button */}
            <button
              type="button"
              onClick={handleZoomOut}
              disabled={scale <= MIN_SCALE}
              title="Zoom Out (− or wheel down)"
              aria-label="Zoom out"
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 text-slate-100 rounded-lg font-medium border border-slate-700 hover:border-slate-600 transition-all focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-900"
            >
              <ZoomOut className="w-4 h-4 text-emerald-400" />
              <span className="hidden xs:inline">Zoom Out</span>
            </button>

            {/* Current Scale Percentage Indicator */}
            <div
              className="px-3 py-1.5 bg-slate-900 text-emerald-300 border border-emerald-500/40 rounded-lg font-mono font-bold text-xs min-w-[64px] text-center"
              aria-live="polite"
              title="Current magnification"
            >
              {zoomPercent}%
            </div>

            {/* Zoom In Button */}
            <button
              type="button"
              onClick={handleZoomIn}
              disabled={scale >= MAX_SCALE}
              title="Zoom In (+ or wheel up)"
              aria-label="Zoom in"
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 text-slate-100 rounded-lg font-medium border border-slate-700 hover:border-slate-600 transition-all focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-900"
            >
              <ZoomIn className="w-4 h-4 text-emerald-400" />
              <span className="hidden xs:inline">Zoom In</span>
            </button>

            {/* Reset Button */}
            <button
              type="button"
              onClick={handleReset}
              title="Reset Zoom Scale (0 or R)"
              aria-label="Reset zoom"
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg font-medium border border-slate-700 hover:border-slate-600 transition-all focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-900"
            >
              <RotateCcw className="w-3.5 h-3.5 text-amber-400" />
              <span>Reset</span>
            </button>

            {/* Close Button */}
            <button
              type="button"
              onClick={onClose}
              title="Close modal (Esc)"
              aria-label="Close modal"
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white rounded-lg font-semibold shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-900"
            >
              <X className="w-4 h-4" />
              <span>Close</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
