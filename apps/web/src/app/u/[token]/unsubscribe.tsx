"use client";

import { useEffect, useState } from "react";
import { CircleCheck, Loader2, MailX } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type Info = { channel: "sms" | "email"; address: string; unsubscribed: boolean };
type State =
  | { kind: "loading" }
  | { kind: "invalid" }
  | { kind: "error" }
  | { kind: "ready"; info: Info; sending: boolean };

const CHANNEL = { sms: "پیامک", email: "ایمیل" } as const;

/** "+98912•••071" reads as "0912•••071". */
function local(address: string): string {
  return address.replace(/^\+98/, "0");
}

/** Public unsubscribe page (spec 4.5). Nothing changes until the person confirms:
 * mail systems open links on their own to scan them. */
export function Unsubscribe({ token }: { token: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    fetch(`/api/public/unsubscribe/${encodeURIComponent(token)}`)
      .then(async (res) => {
        if (!alive) return;
        if (res.status === 404) setState({ kind: "invalid" });
        else if (!res.ok) setState({ kind: "error" });
        else setState({ kind: "ready", info: (await res.json()) as Info, sending: false });
      })
      .catch(() => alive && setState({ kind: "error" }));
    return () => {
      alive = false;
    };
  }, [token]);

  async function confirm(info: Info) {
    setState({ kind: "ready", info, sending: true });
    try {
      const res = await fetch(`/api/public/unsubscribe/${encodeURIComponent(token)}`, { method: "POST" });
      if (!res.ok) throw new Error(String(res.status));
      setState({ kind: "ready", info: (await res.json()) as Info, sending: false });
    } catch {
      setState({ kind: "error" });
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardContent className="flex flex-col items-center gap-4 py-8 text-center">
        {state.kind === "loading" ? (
          <Loader2 className="size-8 animate-spin text-muted-foreground" aria-label="در حال بارگذاری" />
        ) : state.kind === "invalid" ? (
          <>
            <MailX className="size-10 text-muted-foreground" aria-hidden />
            <h1 className="text-lg font-bold">این پیوند معتبر نیست</h1>
            <p className="text-sm text-muted-foreground">ممکن است ناقص کپی شده باشد. از پیوند داخل همان پیام استفاده کنید.</p>
          </>
        ) : state.kind === "error" ? (
          <>
            <MailX className="size-10 text-destructive" aria-hidden />
            <h1 className="text-lg font-bold">انجام نشد</h1>
            <p className="text-sm text-muted-foreground">لطفاً کمی بعد دوباره تلاش کنید.</p>
          </>
        ) : state.info.unsubscribed ? (
          <>
            <CircleCheck className="size-10 text-primary" aria-hidden />
            <h1 className="text-lg font-bold">لغو دریافت ثبت شد</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              از این پس {CHANNEL[state.info.channel]} تبلیغاتی به <bdi dir="ltr">{local(state.info.address)}</bdi> فرستاده نمی‌شود.
              پیام‌های ضروری حساب شما، مانند کد ورود، همچنان ارسال می‌شوند.
            </p>
          </>
        ) : (
          <>
            <MailX className="size-10 text-muted-foreground" aria-hidden />
            <h1 className="text-lg font-bold">لغو دریافت {CHANNEL[state.info.channel]} تبلیغاتی</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              با تأیید، دیگر {CHANNEL[state.info.channel]} تبلیغاتی به <bdi dir="ltr">{local(state.info.address)}</bdi> فرستاده نمی‌شود.
            </p>
            <Button onClick={() => void confirm(state.info)} disabled={state.sending}>
              {state.sending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              تأیید لغو دریافت
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
