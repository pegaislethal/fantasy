"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { updateProfile } from "@/services/accountService";

export default function ProfilePage() {
  const { user, setAuthenticatedUser } = useAuth();
  const [form, setForm] = useState({ username: "", email: "" });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) {
      setForm({ username: user.username || "", email: user.email || "" });
    } else if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem("ff_user");
        if (stored) {
          const parsed = JSON.parse(stored);
          setForm({ username: parsed.username || "", email: parsed.email || "" });
        }
      } catch (e) {
        console.warn("Failed to read user from localStorage", e);
      }
    }
  }, [user]);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const res = await updateProfile(form);
      if (res?.user) {
        setAuthenticatedUser(res.user);
        try {
          localStorage.setItem("ff_user", JSON.stringify(res.user));
        } catch (e) {}
        setMessage("Profile updated.");
      }
    } catch (err) {
      setError(err.message || "Failed to update profile.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container mx-auto p-6 md:p-10">
      <div className="card max-w-lg w-full mx-auto p-6">
        <h1 className="text-2xl font-bold mb-4">Your Profile</h1>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="text-sm text-muted-foreground">Username</label>
            <input
              className="w-full mt-1 px-3 py-2 rounded-md border border-border"
              value={form.username}
              onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">Email</label>
            <input
              className="w-full mt-1 px-3 py-2 rounded-md border border-border"
              value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
            />
          </div>
          <div className="flex items-center gap-3">
            <button className="btn-primary" disabled={loading} type="submit">
              {loading ? "Saving..." : "Save"}
            </button>
            {message && <p className="text-sm text-green-400">{message}</p>}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        </form>
      </div>
    </div>
  );
}
