"use client";

import { createContext, useContext, useMemo, useState, useEffect, useRef } from "react";

const AuthContext = createContext(null);

// Inactivity timeout in milliseconds (15 minutes)
const INACTIVITY_TIMEOUT = 15 * 60 * 1000;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const inactivityTimerRef = useRef(null);
  const lastActivityRef = useRef(Date.now());

  // Function to reset inactivity timer
  const resetInactivityTimer = useRef((logout) => {
    // Clear existing timer
    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
    }

    // Update last activity time
    lastActivityRef.current = Date.now();

    // Set new timer
    inactivityTimerRef.current = setTimeout(() => {
      console.warn("User inactive for 15 minutes. Logging out...");
      logout();
    }, INACTIVITY_TIMEOUT);
  });

  useEffect(() => {
    // On mount, load auth state from localStorage if present
    const checkAuth = () => {
      try {
        if (typeof window !== "undefined") {
          const storedToken = localStorage.getItem("ff_access");
          const storedUser = localStorage.getItem("ff_user");
          if (storedToken) {
            if (storedUser) {
              const parsed = JSON.parse(storedUser);
              if (JSON.stringify(user) !== JSON.stringify(parsed)) {
                setUser(parsed);
              }
            } else if (!user) {
              setUser({ username: null });
            }
          } else {
            // Token was removed
            if (user) {
              setUser(null);
            }
          }
        }
      } catch (e) {
        console.warn("Failed to initialize auth from localStorage", e);
      }
    };

    checkAuth();

    // Listen for storage changes from other tabs
    const handleStorageChange = (e) => {
      if (e.key === "ff_access" && !e.newValue) {
        setUser(null);
        if (inactivityTimerRef.current) {
          clearTimeout(inactivityTimerRef.current);
        }
      }
    };
    window.addEventListener("storage", handleStorageChange);

    // Periodic check for token removal in current tab
    const interval = setInterval(checkAuth, 2000);

    return () => {
      window.removeEventListener("storage", handleStorageChange);
      clearInterval(interval);
      if (inactivityTimerRef.current) {
        clearTimeout(inactivityTimerRef.current);
      }
    };
  }, [user]);

  const logout = () => {
    try {
      if (typeof window !== "undefined") {
        localStorage.removeItem("ff_access");
        localStorage.removeItem("ff_refresh");
        localStorage.removeItem("ff_user");
        document.cookie = "ff_access=; Path=/; Max-Age=0;";
        document.cookie = "ff_refresh=; Path=/; Max-Age=0;";
        document.cookie = "ff_role=; Path=/; Max-Age=0;";
        
        // Clear inactivity timer
        if (inactivityTimerRef.current) {
          clearTimeout(inactivityTimerRef.current);
        }

        // Clear state
        setUser(null);

        // Redirect to landing page (home)
        window.location.href = "/";
      }
    } catch (e) {
      console.warn("Failed to clear auth data", e);
      setUser(null);
    }
  };

  // Set up inactivity timer when user logs in
  useEffect(() => {
    if (user && typeof window !== "undefined") {
      resetInactivityTimer.current(logout);

      // Activity event listeners
      const activityEvents = ["mousemove", "keypress", "click", "touchstart", "wheel", "scroll"];

      const handleActivity = () => {
        resetInactivityTimer.current(logout);
      };

      // Add event listeners
      activityEvents.forEach((event) => {
        window.addEventListener(event, handleActivity);
      });

      // Cleanup
      return () => {
        activityEvents.forEach((event) => {
          window.removeEventListener(event, handleActivity);
        });
        if (inactivityTimerRef.current) {
          clearTimeout(inactivityTimerRef.current);
        }
      };
    }
  }, [user]);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      setAuthenticatedUser: setUser,
      logout,
    }),
    [user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
