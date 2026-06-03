"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuthStore } from "../../store/useAuthStore";
import { useToastStore } from "../../store/useToastStore";

export default function SignUpPage() {
  const router = useRouter();
  const { signup, loading } = useAuthStore();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (password.length < 8) {
      setLocalError("Password must be at least 8 characters");
      return;
    }
    if (password !== confirm) {
      setLocalError("Passwords don't match");
      return;
    }
    try {
      await signup(username, password);
      useToastStore.getState().success("Account created", `Welcome, ${username}`);
      router.push("/library");
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Sign-up failed");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <form
        onSubmit={handleSubmit}
        className="glass-panel rounded-xl p-8 w-full max-w-sm flex flex-col gap-4"
      >
        <Link href="/" className="flex items-center gap-2 justify-center mb-2">
          <span className="material-symbols-outlined text-primary-container text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>graphic_eq</span>
          <span className="font-headline text-2xl font-semibold text-primary-container tracking-tight">Synesthesia</span>
        </Link>
        <h1 className="font-headline text-xl text-on-surface text-center">Create your account</h1>
        <p className="text-xs text-on-surface-variant text-center -mt-2">
          Optional — needed only to save analyses to your library.
        </p>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-on-surface-variant">Username</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            autoComplete="username"
            className="bg-surface-container-high border border-white/10 rounded-md px-3 py-2 text-on-surface focus:border-primary focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-on-surface-variant">Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            className="bg-surface-container-high border border-white/10 rounded-md px-3 py-2 text-on-surface focus:border-primary focus:outline-none"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-on-surface-variant">Confirm password</span>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            className="bg-surface-container-high border border-white/10 rounded-md px-3 py-2 text-on-surface focus:border-primary focus:outline-none"
          />
        </label>

        {localError && <p className="text-xs text-error">{localError}</p>}

        <button
          type="submit"
          disabled={loading}
          className="primary-gradient text-on-primary font-semibold py-2.5 rounded-full disabled:opacity-50"
        >
          {loading ? "Creating account…" : "Create account"}
        </button>

        <p className="text-xs text-on-surface-variant text-center mt-2">
          Already have one? <Link href="/login" className="text-primary hover:underline">Sign in</Link>
        </p>
        <p className="text-xs text-outline-variant text-center">
          <Link href="/" className="hover:text-on-surface">← Continue as guest</Link>
        </p>
      </form>
    </div>
  );
}
