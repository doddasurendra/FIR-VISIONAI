import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: 'STATION' | 'DISTRICT' | 'STATE';
  district: string;
  station: string | null;
  badge_number: string | null;
  designation: string | null;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  switchDemoUser: (role: 'STATION' | 'DISTRICT' | 'STATE') => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const cached = localStorage.getItem('fir_sahayak_user');
    return cached ? JSON.parse(cached) : null;
  });
  const [token, setToken] = useState<string | null>(() => {
    return localStorage.getItem('fir_sahayak_token') || null;
  });

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete axios.defaults.headers.common['Authorization'];
    }
  }, [token]);

  const login = async (username: string, password: string): Promise<boolean> => {
    try {
      const res = await axios.post('/api/v1/auth/login', { username, password });
      const { access_token, user: userData } = res.data;
      setToken(access_token);
      setUser(userData);
      localStorage.setItem('fir_sahayak_token', access_token);
      localStorage.setItem('fir_sahayak_user', JSON.stringify(userData));
      axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
      return true;
    } catch (e) {
      console.error('Login error:', e);
      return false;
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('fir_sahayak_token');
    localStorage.removeItem('fir_sahayak_user');
    delete axios.defaults.headers.common['Authorization'];
  };

  const switchDemoUser = async (role: 'STATION' | 'DISTRICT' | 'STATE') => {
    if (role === 'STATION') {
      await login('station_officer', 'StationPass@2024');
    } else if (role === 'DISTRICT') {
      await login('district_admin', 'DistrictPass@2024');
    } else if (role === 'STATE') {
      await login('state_director', 'StateAdmin@2024');
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user && !!token,
        login,
        logout,
        switchDemoUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
