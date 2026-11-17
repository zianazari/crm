"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Loader2, Mail, Smartphone } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { formatNumber, toAsciiDigits } from "@/lib/format";
import { cn } from "@/lib/utils";

type Channel = "sms" | "email";
type Challenge = { challenge_id: string; expires_in: number; resend_after: number };

const CODE_LENGTH = 5;

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
  const [channel, setChannel] = useState<Channel>("sms");
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
      <form onSubmit={requestCode} className="space-y-5">
        <div role="radiogroup" aria-label="روش دریافت کد" className="grid grid-cols-2 gap-2 rounded-lg bg-muted p-1">
          {(
            [
              { value: "sms", label: "پیامک", icon: Smartphone },
              { value: "email", label: "ایمیل", icon: Mail },
            ] as const
          ).map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={channel === value}
              onClick={() => {
                setChannel(value);
                setDestination("");
                setError(null);
              }}
              className={cn(
                "flex items-center justify-center gap-2 rounded-md py-2 text-sm font-medium text-muted-foreground transition-colors",
                channel === value && "bg-card text-foreground shadow-sm",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          <label htmlFor="destination" className="text-sm font-medium">
            {channel === "sms" ? "شماره موبایل" : "ایمیل"}
          </label>
          <Input
            id="destination"
            dir="ltr"
            required
            autoFocus
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            type={channel === "sms" ? "tel" : "email"}
            inputMode={channel === "sms" ? "tel" : "email"}
            autoComplete={channel === "sms" ? "tel" : "email"}
            placeholder={channel === "sms" ? "09xxxxxxxxx" : "name@example.com"}
            className="h-11 text-start"
          />
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button type="submit" className="h-11 w-full" disabled={pending || !destination.trim()}>
          {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
          دریافت کد ورود
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
      className="space-y-5"
    >
      <p className="text-sm text-muted-foreground">
        اگر{" "}
        <span className="ltr-value font-medium text-foreground">{destination}</span> در سامانه
        ثبت شده باشد، کد {formatNumber(CODE_LENGTH)} رقمی به آن ارسال شده است.
      </p>

      <div className="space-y-2">
        <label htmlFor="code" className="text-sm font-medium">
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
          className="h-12 text-center text-2xl tracking-[0.6em]"
        />
      </div>

      {error ? (
        <p id="code-error" role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <Button type="submit" className="h-11 w-full" disabled={pending || code.length !== CODE_LENGTH}>
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
          تغییر {channel === "sms" ? "شماره" : "ایمیل"}
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
