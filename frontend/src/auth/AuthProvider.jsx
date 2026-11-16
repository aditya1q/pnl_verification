import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { onSessionEnded, postJson, refreshSession, requestJson, setAccessToken } from "@/api/client";

const AuthContext = createContext(null);
const WRITE_ROLES = ["admin", "operator"];

// Signed-in user for the whole app. On load, the refresh cookie (if any) restores the session.
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", user: null, notice: "" });

  useEffect(() => {
    refreshSession()
      .then((data) => setState({ status: "in", user: data.user, notice: "" }))
      .catch(() => setState({ status: "out", user: null, notice: "" }));
    return onSessionEnded(() => setState({ status: "out", user: null, notice: "Your session has ended. Sign in again." }));
  }, []);

  const login = useCallback(async (username, password) => {
    const data = await postJson("/api/auth/login", { username, password });
    setAccessToken(data.access_token);
    setState({ status: "in", user: data.user, notice: "" });
  }, []);

  const logout = useCallback(async () => {
    try { await requestJson("/api/auth/logout", { method: "POST" }); } catch { /* signed out locally anyway */ }
    setAccessToken(null);
    setState({ status: "out", user: null, notice: "" });
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const data = await postJson("/api/auth/change-password", { current_password: currentPassword, new_password: newPassword });
    setAccessToken(data.access_token);
    setState((prev) => ({ ...prev, user: data.user }));
  }, []);

  const value = useMemo(() => ({
    ...state,
    login,
    logout,
    changePassword,
    canWrite: WRITE_ROLES.includes(state.user?.role),
    isAdmin: state.user?.role === "admin",
  }), [state, login, logout, changePassword]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
