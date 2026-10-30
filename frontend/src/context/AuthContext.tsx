import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import type { User, TokenResponse } from "../types";
import { tokenStorage } from "../api/client";
import { getProfile, logout as logoutApi } from "../api/auth";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  setSession: (tokens: TokenResponse, user?: User) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadProfile = async () => {
    try {
      const profile = await getProfile();
      setUser(profile);
    } catch {
      tokenStorage.clear();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (tokenStorage.getAccessToken()) {
      loadProfile();
    } else {
      setIsLoading(false);
    }
  }, []);

  const setSession = async (tokens: TokenResponse, prefetchedUser?: User) => {
    tokenStorage.setTokens(tokens);
    if (prefetchedUser) {
      setUser(prefetchedUser);
    } else {
      await loadProfile();
    }
  };

  const logout = async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    try {
      if (refreshToken) await logoutApi(refreshToken);
    } finally {
      tokenStorage.clear();
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user, setSession, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
