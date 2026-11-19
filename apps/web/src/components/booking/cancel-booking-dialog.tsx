"use client";

import { useState } from "react";
import { CalendarX2, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
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
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";

/** Cancel a booking, with an optional reason. Used on the booking page, the portal and
 * the staff side (where the reason is required). */
export function CancelBookingDialog({
  onCancel,
  staff = false,
  size = "default",
}: {
  onCancel: (reason: string) => Promise<void>;
  staff?: boolean;
  size?: "default" | "sm";
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  async function confirm() {
    setPending(true);
    try {
      await onCancel(reason.trim());
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "لغو انجام نشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setReason("");
      }}
    >
      <DialogTrigger
        render={
          <Button variant="ghost" size={size} className="text-destructive">
            <CalendarX2 aria-hidden />
            لغو جلسه
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>لغو جلسه</DialogTitle>
          <DialogDescription>
            {staff ? "زمان آزاد می‌شود و به مشتری پیام لغو می‌رود." : "زمان آزاد می‌شود و کارشناس باخبر می‌شود."}
          </DialogDescription>
        </DialogHeader>
        <Field label={staff ? "دلیل" : "دلیل (اختیاری)"} htmlFor="cancel-reason" required={staff}>
          <Textarea id="cancel-reason" rows={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button variant="destructive" onClick={() => void confirm()} disabled={pending || (staff && reason.trim().length < 2)}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            لغو جلسه
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
