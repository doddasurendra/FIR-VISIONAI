import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: attach bearer token and handle FormData
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('fir_sahayak_token') || localStorage.getItem('token');
  if (token) {
    if (config.headers && typeof (config.headers as any).set === 'function') {
      (config.headers as any).set('Authorization', `Bearer ${token}`);
    } else {
      (config.headers as any)['Authorization'] = `Bearer ${token}`;
    }
  }

  // If payload is FormData (e.g. PDF upload), remove Content-Type so browser sets boundary
  if (config.data instanceof FormData) {
    if (config.headers && typeof (config.headers as any).delete === 'function') {
      (config.headers as any).delete('Content-Type');
    } else if (config.headers) {
      delete (config.headers as any)['Content-Type'];
    }
  }

  return config;
}, (error) => Promise.reject(error));

// Response interceptor: auto token refresh on 401
let isRefreshing = false;
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: any) => void }> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else if (token) {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If 401 and not an auth endpoint
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest.url?.includes('/auth/')) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            if (originalRequest.headers && typeof (originalRequest.headers as any).set === 'function') {
              (originalRequest.headers as any).set('Authorization', `Bearer ${token}`);
            } else {
              originalRequest.headers['Authorization'] = `Bearer ${token}`;
            }
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem('fir_sahayak_refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post('/api/v1/auth/refresh', {
            refresh_token: refreshToken
          });
          const { access_token, refresh_token: newRefresh } = res.data;
          localStorage.setItem('fir_sahayak_token', access_token);
          if (newRefresh) {
            localStorage.setItem('fir_sahayak_refresh_token', newRefresh);
          }

          api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
          if (originalRequest.headers && typeof (originalRequest.headers as any).set === 'function') {
            (originalRequest.headers as any).set('Authorization', `Bearer ${access_token}`);
          } else {
            originalRequest.headers['Authorization'] = `Bearer ${access_token}`;
          }

          processQueue(null, access_token);
          return api(originalRequest);
        } catch (refreshErr) {
          processQueue(refreshErr, null);
          localStorage.removeItem('fir_sahayak_token');
          localStorage.removeItem('fir_sahayak_refresh_token');
          localStorage.removeItem('fir_sahayak_user');
          window.dispatchEvent(new Event('auth:unauthorized'));
          return Promise.reject(refreshErr);
        } finally {
          isRefreshing = false;
        }
      } else {
        localStorage.removeItem('fir_sahayak_token');
        localStorage.removeItem('fir_sahayak_user');
        window.dispatchEvent(new Event('auth:unauthorized'));
      }
    }

    return Promise.reject(error);
  }
);

export default api;
