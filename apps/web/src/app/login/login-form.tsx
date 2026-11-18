"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { formatNumber, toAsciiDigits } from "@/lib/format";

type Channel = "sms" | "email";
type Challenge = { challenge_id: string; expires_in: number; resend_after: number };

const CODE_LENGTH = 5;

/** One field for both: an "@" means email, otherwise a phone number (Persian digits,
 * spaces, dashes and +98 are fine; the API normalizes and validates it). */
function detectChannel(value: string): Channel | null {
  const text = value.trim();
  if (text.includes("@")) return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text) ? "email" : null;
  const digits = toAsciiDigits(text).replace(/[\s\-()+]/g, "");
  return /^\d{10,14}$/.test(digits) ? "sms" : null;
}

function safeNext(next: string | null): string {
  // Only same-site paths, never "//evil.example" or absolute URLs.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/overview";
}

function useCountdown() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (seconds <= 0) return;
    const id = setTimeout(() => setSeconds((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [seconds]);
  return [seconds, setSeconds] as const;
}

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [destination, setDestination] = useState("");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [resendIn, setResendIn] = useCountdown();
  const codeRef = useRef<HTMLInputElement>(null);

  function describe(err: unknown): string {
    if (err instanceof ApiError && err.status === 429 && err.retryAfter) {
      return `${err.message} (${formatNumber(err.retryAfter)} ثانیه)`;
    }
    return err instanceof ApiError ? err.message : "خطایی رخ داد. دوباره تلاش کنید.";
  }

  async function requestCode(event?: FormEvent) {
    event?.preventDefault();
    setError(null);
    const channel = detectChannel(destination);
    if (!channel) {
      setError("یک ایمیل یا شماره‌ی همراه معتبر وارد کنید.");
      return;
    }
    setPending(true);
    try {
      const result = await apiFetch<Challenge>("/auth/otp/request", {
        method: "POST",
        body: JSON.stringify({ channel, destination }),
      });
      setChallenge(result);
      setCode("");
      setResendIn(result.resend_after);
      setTimeout(() => codeRef.current?.focus(), 0);
    } catch (err) {
      setError(describe(err));
    } finally {
      setPending(false);
    }
  }

  async function verify(value: string) {
    if (!challenge) return;
    setError(null);
    setPending(true);
    try {
      await apiFetch("/auth/otp/verify", {
        method: "POST",
        body: JSON.stringify({ challenge_id: challenge.challenge_id, code: value }),
      });
      router.replace(safeNext(searchParams.get("next")));
    } catch (err) {
      setError(describe(err));
      setCode("");
      codeRef.current?.focus();
      setPending(false);
    }
  }

  function onCodeChange(raw: string) {
    const digits = toAsciiDigits(raw).replace(/\D/g, "").slice(0, CODE_LENGTH);
    setCode(digits);
    if (digits.length === CODE_LENGTH && !pending) void verify(digits);
  }

  if (!challenge) {
    return (
      <form onSubmit={requestCode} className="mt-6" noValidate>
        <div className="space-y-3">
          <label htmlFor="destination" className="block text-sm leading-5 font-medium">
            ایمیل یا شماره‌ی همراه
          </label>
          <Input
            id="destination"
            dir="ltr"
            required
            autoFocus
            value={destination}
            onChange={(e) => {
              setDestination(e.target.value);
              setError(null);
            }}
            type="text"
            inputMode="email"
            autoComplete="username"
            placeholder="name@example.com"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "destination-error" : undefined}
            className="h-12 rounded-lg text-sm text-start md:text-sm"
          />
        </div>

        {error ? (
          <p id="destination-error" role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button
          type="submit"
          className="mt-3.5 h-[42px] w-full rounded-lg text-sm font-semibold"
          disabled={pending || !destination.trim()}
        >
          {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
          ادامه
        </Button>
      </form>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (code.length === CODE_LENGTH) void verify(code);
      }}
      className="mt-6 space-y-3.5"
    >
      <p className="text-sm text-muted-foreground">
        اگر{" "}
        <span className="ltr-value font-medium text-foreground">{destination}</span> در سامانه
        ثبت شده باشد، کد {formatNumber(CODE_LENGTH)} رقمی به آن ارسال شده است.
      </p>

      <div className="space-y-3">
        <label htmlFor="code" className="block text-sm leading-5 font-medium">
          کد ورود
        </label>
        <Input
          id="code"
          ref={codeRef}
          dir="ltr"
          value={code}
          onChange={(e) => onCodeChange(e.target.value)}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={CODE_LENGTH * 2}
          placeholder="•••••"
          aria-describedby={error ? "code-error" : undefined}
          className="h-12 rounded-lg text-center text-2xl tracking-[0.6em]"
        />
      </div>

      {error ? (
        <p id="code-error" role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <Button
        type="submit"
        className="h-[42px] w-full rounded-lg text-sm font-semibold"
        disabled={pending || code.length !== CODE_LENGTH}
      >
        {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
        ورود
      </Button>

      <div className="flex items-center justify-between text-sm">
        <button
          type="button"
          onClick={() => {
            setChallenge(null);
            setError(null);
          }}
          className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
        >
          <ArrowRight className="size-4" aria-hidden />
          تغییر ایمیل یا شماره
        </button>
        {resendIn > 0 ? (
          <span className="text-muted-foreground">
            ارسال دوباره تا {formatNumber(resendIn)} ثانیه
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void requestCode()}
            disabled={pending}
            className="font-medium text-primary hover:underline"
          >
            ارسال دوباره کد
          </button>
        )}
      </div>
    </form>
  );
}
