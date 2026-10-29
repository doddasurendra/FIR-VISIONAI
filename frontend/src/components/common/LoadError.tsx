import React from 'react';
import { AlertCircle } from 'lucide-react';

/** The message for a failed request: the server's explanation when it gave one. */
export const errorMessage = (e: any, fallback: string): string => {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (!e?.response) return `${fallback} The server could not be reached.`;
  return fallback;
};

/** A failed load: what went wrong and a Retry button, in place of an endless spinner. */
export const LoadError: React.FC<{ message: string; onRetry: () => void; className?: string }> = ({
  message,
  onRetry,
  className = '',
}) => (
  <div
    role="alert"
    className={`p-3 bg-red-50 text-red-800 rounded-lg border border-red-200 text-xs flex items-center gap-2 ${className}`}
  >
    <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
    <span className="flex-1">{message}</span>
    <button
      onClick={onRetry}
      className="px-2.5 py-1 bg-white border border-red-300 rounded-md font-semibold hover:bg-red-100"
    >
      Retry
    </button>
  </div>
);
