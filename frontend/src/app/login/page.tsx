"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API, setToken } from "../../../lib/api";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [income, setIncome] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body =
        mode === "signup"
          ? { email, password, monthly_income: Number(income) || 0 }
          : { email, password };
      const r = await fetch(API + "/auth/" + mode, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(typeof d.detail === "string" ? d.detail : "Check your details and try again");
      }
      setToken(d.token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-100 p-8">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl bg-white p-8 shadow">
        <h1 className="text-3xl font-bold text-blue-600">FinPilot AI</h1>
        <p className="text-gray-600">
          {mode === "login" ? "Log in to your account" : "Create your account"}
        </p>

        {error && <p className="rounded bg-red-100 p-2 text-sm text-red-700">{error}</p>}

        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Password (min 8 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        {mode === "signup" && (
          <input
            type="number"
            min={0}
            placeholder="Monthly income (₹)"
            value={income}
            onChange={(e) => setIncome(e.target.value)}
            className="w-full rounded border px-3 py-2"
          />
        )}

        <button
          disabled={busy}
          className="w-full rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {busy ? "Please wait..." : mode === "login" ? "Log in" : "Sign up"}
        </button>
        <button
          type="button"
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setError("");
          }}
          className="w-full text-sm text-blue-600"
        >
          {mode === "login" ? "No account? Sign up" : "Have an account? Log in"}
        </button>
      </form>
    </main>
  );
}