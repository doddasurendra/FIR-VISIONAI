import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home, ShieldAlert } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  title?: string;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an unhandled error:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  private handleReload = () => {
    window.location.reload();
  };

  private handleGoHome = () => {
    window.location.href = '/';
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const errorMessage = this.state.error?.message || 'An unexpected rendering or runtime error occurred.';

      return (
        <div className="min-h-[400px] w-full flex items-center justify-center p-6 bg-slate-50">
          <div className="max-w-xl w-full bg-white rounded-2xl border border-red-200 shadow-xl overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-red-600 to-rose-700 px-6 py-4 text-white flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-white/20 rounded-lg backdrop-blur-sm">
                  <ShieldAlert className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h3 className="font-bold text-base leading-tight">
                    {this.props.title || 'Application Workspace Notice'}
                  </h3>
                  <p className="text-xs text-red-100">
                    Government of Andhra Pradesh · Prohibition &amp; Excise Department
                  </p>
                </div>
              </div>
            </div>

            {/* Body */}
            <div className="p-6 space-y-4">
              <div className="flex items-start space-x-3 bg-red-50 border border-red-100 rounded-xl p-3.5">
                <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div className="text-xs text-red-900 leading-relaxed font-medium">
                  {errorMessage}
                </div>
              </div>

              <p className="text-xs text-slate-500 leading-relaxed">
                The application encountered an issue while rendering this view. Your session data and saved cases remain intact.
                You can reload the workspace or return to the dashboard.
              </p>

              {this.state.errorInfo?.componentStack && (
                <details className="text-[11px] bg-slate-100 rounded-lg p-2.5 text-slate-700">
                  <summary className="cursor-pointer font-semibold text-slate-800 hover:text-slate-900">
                    Technical Diagnostics
                  </summary>
                  <pre className="mt-2 text-[10px] font-mono whitespace-pre-wrap max-h-36 overflow-y-auto text-slate-600">
                    {this.state.error?.stack || this.state.errorInfo.componentStack}
                  </pre>
                </details>
              )}

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <button
                  type="button"
                  onClick={this.handleReset}
                  className="px-4 py-2 bg-[#0f5132] hover:bg-[#0a3d26] text-white text-xs font-semibold rounded-lg shadow-sm transition-colors flex items-center space-x-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Try Again</span>
                </button>

                <button
                  type="button"
                  onClick={this.handleReload}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors flex items-center space-x-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Reload Page</span>
                </button>

                <button
                  type="button"
                  onClick={this.handleGoHome}
                  className="px-4 py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg shadow-sm transition-colors flex items-center space-x-1.5 ml-auto"
                >
                  <Home className="w-3.5 h-3.5" />
                  <span>Dashboard</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
