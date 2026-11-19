"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck2, CalendarClock, Clock, Link2Off, Loader2, ShieldCheck, UserRound } from "lucide-react";
import { toast } from "sonner";

import { LoginForm } from "@/app/login/login-form";
import { CancelBookingDialog } from "@/components/booking/cancel-booking-dialog";
import { formatSlot, SlotPicker } from "@/components/booking/slot-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { bookFetch, type LinkView, type Slots } from "@/lib/booking";
import { formatDateTime, formatNumber } from "@/lib/format";

type Mode = "pick" | "verify" | "confirm" | "view" | "move";

export function BookingPage({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const view = useQuery({
    queryKey: ["book", token],
    queryFn: () => bookFetch<LinkView>(`/${token}`),
    retry: false,
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode | null>(null);
  const [pending, setPending] = useState(false);

  const link = view.data;
  const current: Mode =
    mode ??
    (link?.state === "booked" ? (link.verified ? "view" : "verify") : "pick");
  const wantsSlots = link && (link.state === "open" || (link.state === "booked" && current === "move"));
  const slots = useQuery({
    queryKey: ["book", token, "slots"],
    queryFn: () => bookFetch<Slots>(`/${token}/slots`),
    enabled: Boolean(wantsSlots),
    refetchInterval: 60_000,
  });

  function accept(next: LinkView) {
    queryClient.setQueryData(["book", token], next);
    void queryClient.invalidateQueries({ queryKey: ["book", token, "slots"] });
  }

  async function submit(path: "book" | "reschedule") {
    if (!chosen) return;
    setPending(true);
    try {
      accept(await bookFetch<LinkView>(`/${token}/${path}`, { method: "POST", body: JSON.stringify({ start_at: chosen }) }));
      setMode("view");
      setChosen(null);
      toast.success(path === "book" ? "جلسه رزرو شد. پیام تأیید برایتان فرستاده شد." : "زمان جلسه تغییر کرد.");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "انجام نشد.";
      toast.error(message);
      if (err instanceof ApiError && err.status === 409) {
        setChosen(null);
        setMode(path === "book" ? "pick" : "move");
        await queryClient.invalidateQueries({ queryKey: ["book", token] });
      }
      if (err instanceof ApiError && err.status === 401) setMode("verify");
    } finally {
      setPending(false);
    }
  }

  if (view.error) {
    return (
      <Notice icon={<Link2Off className="size-8" aria-hidden />} title="این لینک معتبر نیست">
        نشانی را کامل و بدون تغییر باز کنید یا از کارشناس خود لینک تازه بخواهید.
      </Notice>
    );
  }
  if (!link) return <Skeleton className="h-96" />;

  const header = (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">{link.meeting.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        <p className="flex items-center gap-2">
          <UserRound className="size-4" aria-hidden />
          با {link.staff_name}
        </p>
        <p className="flex items-center gap-2">
          <Clock className="size-4" aria-hidden />
          {formatNumber(link.meeting.duration_minutes)} دقیقه · به وقت تهران
        </p>
        {link.meeting.description ? <p className="whitespace-pre-line leading-7">{link.meeting.description}</p> : null}
      </CardContent>
    </Card>
  );

  if (link.state === "expired" || link.state === "revoked") {
    return (
      <>
        {header}
        <Notice icon={<Link2Off className="size-8" aria-hidden />} title={link.state === "expired" ? "مهلت این لینک تمام شده است" : "این لینک دیگر فعال نیست"}>
          برای انتخاب زمان، از کارشناس خود لینک تازه بخواهید.
        </Notice>
      </>
    );
  }

  return (
    <>
      {header}
      {current === "view" && link.booking ? (
        <Card className="border-emerald-300">
          <CardContent className="space-y-4">
            <div className="flex items-start gap-3">
              <CalendarCheck2 className="mt-0.5 size-6 shrink-0 text-emerald-700" aria-hidden />
              <div className="space-y-1">
                <p className="font-semibold">جلسه شما رزرو شده است</p>
                <p className="text-base">{formatSlot(link.booking.start_at, link.booking.end_at)}</p>
              </div>
            </div>
            {link.booking.can_change ? (
              <>
                <p className="text-xs text-muted-foreground">
                  تا {formatDateTime(link.booking.change_until)} می‌توانید زمان را تغییر دهید یا جلسه را لغو کنید.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={() => setMode("move")}>
                    <CalendarClock aria-hidden />
                    تغییر زمان
                  </Button>
                  <CancelBookingDialog
                    onCancel={async (reason) => {
                      accept(await bookFetch<LinkView>(`/${token}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }));
                      setMode(null);
                      toast.success("جلسه لغو شد.");
                    }}
                  />
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                مهلت تغییر یا لغو این جلسه گذشته است. اگر نمی‌توانید حاضر شوید، با کارشناس خود تماس بگیرید.
              </p>
            )}
          </CardContent>
        </Card>
      ) : current === "verify" ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="size-5" aria-hidden />
              تأیید هویت
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {link.state === "booked" ? (
              <p className="text-muted-foreground">با این لینک جلسه‌ای رزرو شده است. برای دیدن یا تغییر آن، هویت خود را تأیید کنید.</p>
            ) : chosen ? (
              <p className="text-muted-foreground">
                زمان انتخاب‌شده: <span className="font-medium text-foreground">{formatSlot(chosen)}</span>
                <br />
                شماره همراه یا ایمیلی را که نزد ما ثبت کرده‌اید وارد کنید تا کد تأیید برایتان فرستاده شود.
              </p>
            ) : null}
            <LoginForm
              api={`/book/${token}`}
              submitLabel="تأیید"
              onVerified={() => {
                void view.refetch().then(({ data }) => setMode(data?.state === "booked" ? "view" : "confirm"));
              }}
            />
            {link.state !== "booked" ? (
              <Button variant="link" className="px-0" onClick={() => setMode("pick")}>
                انتخاب زمان دیگر
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : current === "confirm" && chosen ? (
        <Card>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">زمان انتخاب‌شده</p>
            <p className="text-lg font-semibold">{formatSlot(chosen)}</p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void submit("book")} disabled={pending}>
                {pending ? <Loader2 className="animate-spin" aria-hidden /> : <CalendarCheck2 aria-hidden />}
                ثبت رزرو
              </Button>
              <Button variant="ghost" onClick={() => setMode("pick")} disabled={pending}>
                تغییر انتخاب
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{current === "move" ? "زمان تازه را انتخاب کنید" : "یک زمان انتخاب کنید"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!slots.data ? (
              slots.error ? (
                <p className="text-sm text-destructive">{slots.error instanceof ApiError ? slots.error.message : "زمان‌ها بارگیری نشد."}</p>
              ) : (
                <Skeleton className="h-48" />
              )
            ) : (
              <SlotPicker slots={slots.data} value={chosen} onChange={setChosen} current={current === "move" ? link.booking?.start_at : undefined} />
            )}
            <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 border-t bg-card pt-3">
              <span className="text-sm">{chosen ? formatSlot(chosen) : <span className="text-muted-foreground">زمانی انتخاب نشده است</span>}</span>
              <div className="flex gap-2">
                {current === "move" ? (
                  <>
                    <Button variant="ghost" onClick={() => { setMode("view"); setChosen(null); }}>
                      انصراف
                    </Button>
                    <Button onClick={() => void submit("reschedule")} disabled={!chosen || pending || chosen === link.booking?.start_at}>
                      {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                      ثبت زمان جدید
                    </Button>
                  </>
                ) : (
                  <Button onClick={() => setMode(link.verified ? "confirm" : "verify")} disabled={!chosen}>
                    ادامه
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
      <p className="text-center text-xs text-muted-foreground">
        این صفحه فقط برای انتخاب زمان است و اطلاعات پرونده شما را نشان نمی‌دهد.
      </p>
    </>
  );
}

function Notice({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
        <span className="text-muted-foreground">{icon}</span>
        <p className="font-semibold">{title}</p>
        <p className="text-sm text-muted-foreground">{children}</p>
      </CardContent>
    </Card>
  );
}
