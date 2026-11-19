"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck2, CalendarClock, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { CancelBookingDialog } from "@/components/booking/cancel-booking-dialog";
import { formatSlot, SlotPicker } from "@/components/booking/slot-picker";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import type { PortalBooking, Slots } from "@/lib/booking";
import { formatDateTime } from "@/lib/format";
import { portalFetch } from "@/lib/portal";

/** The customer's own meetings (spec 4.9 «زمان‌های رزروشده خودش»). Hidden until there is one. */
export function PortalBookings() {
  const queryClient = useQueryClient();
  // The time is taken with the data (not during render), so the page can be prerendered.
  const { data: result } = useQuery({
    queryKey: ["portal", "bookings"],
    queryFn: async () => ({ rows: await portalFetch<PortalBooking[]>("/bookings"), now: Date.now() }),
  });
  if (!result || result.rows.length === 0) return null;
  const { rows: data, now } = result;
  const upcoming = data.filter((b) => b.status === "confirmed" && new Date(b.end_at).getTime() > now);
  const past = data.filter((b) => !upcoming.includes(b)).slice(0, 5);
  // Only the list: a moved booking has a new id, so its old slot query must not refetch.
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["portal", "bookings"], exact: true });

  return (
    <section aria-labelledby="my-meetings" className="space-y-3">
      <h2 id="my-meetings" className="text-lg font-semibold">
        جلسه‌های من
      </h2>
      {upcoming.length === 0 ? <p className="text-sm text-muted-foreground">جلسه پیش رویی ندارید.</p> : null}
      <ul className="space-y-3">
        {upcoming.map((b) => (
          <li key={b.id} className="space-y-3 rounded-xl border bg-card p-4">
            <div className="flex items-start gap-3">
              <CalendarCheck2 className="mt-0.5 size-5 shrink-0 text-emerald-700" aria-hidden />
              <div className="min-w-0 space-y-0.5">
                <p className="font-medium">{formatSlot(b.start_at, b.end_at)}</p>
                <p className="text-sm text-muted-foreground">
                  {b.meeting_title} · با {b.staff_name}
                </p>
                {b.meeting_description ? <p className="text-sm text-muted-foreground">{b.meeting_description}</p> : null}
              </div>
            </div>
            {b.can_change ? (
              <div className="flex flex-wrap items-center gap-2">
                <MoveDialog booking={b} onMoved={() => void refresh()} />
                <CancelBookingDialog
                  size="sm"
                  onCancel={async (reason) => {
                    await portalFetch(`/bookings/${b.id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) });
                    await refresh();
                    toast.success("جلسه لغو شد.");
                  }}
                />
                <span className="text-xs text-muted-foreground">تا {formatDateTime(b.change_until)}</span>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">مهلت تغییر گذشته است؛ برای تغییر با کارشناس خود تماس بگیرید.</p>
            )}
          </li>
        ))}
      </ul>
      {past.length > 0 ? (
        <ul className="space-y-1 text-sm text-muted-foreground">
          {past.map((b) => (
            <li key={b.id}>
              {b.meeting_title} · {formatSlot(b.start_at)} · {b.status === "canceled" ? "لغو شد" : "برگزار شد"}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function MoveDialog({ booking, onMoved }: { booking: PortalBooking; onMoved: () => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const slots = useQuery({
    queryKey: ["portal", "bookings", booking.id, "slots"],
    queryFn: () => portalFetch<Slots>(`/bookings/${booking.id}/slots`),
    enabled: open,
  });

  async function save() {
    if (!chosen) return;
    setPending(true);
    try {
      await portalFetch(`/bookings/${booking.id}/reschedule`, { method: "POST", body: JSON.stringify({ start_at: chosen }) });
      toast.success("زمان جلسه تغییر کرد.");
      setOpen(false);
      onMoved();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
      if (err instanceof ApiError && err.status === 409) {
        setChosen(null);
        void queryClient.invalidateQueries({ queryKey: ["portal", "bookings", booking.id, "slots"] });
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setChosen(null);
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline">
            <CalendarClock aria-hidden />
            تغییر زمان
          </Button>
        }
      />
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-x-hidden overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>تغییر زمان جلسه</DialogTitle>
          <DialogDescription>زمان فعلی: {formatSlot(booking.start_at, booking.end_at)}</DialogDescription>
        </DialogHeader>
        {slots.data ? (
          <SlotPicker slots={slots.data} value={chosen} onChange={setChosen} current={booking.start_at} />
        ) : slots.error ? (
          <p className="text-sm text-destructive">{slots.error instanceof ApiError ? slots.error.message : "بارگیری نشد."}</p>
        ) : (
          <Skeleton className="h-48" />
        )}
        <DialogFooter>
          <Button onClick={() => void save()} disabled={!chosen || pending || chosen === booking.start_at}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ثبت زمان جدید
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
