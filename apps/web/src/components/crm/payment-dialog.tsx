"use client";

import { useState, type ReactElement } from "react";
import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AmountInput } from "@/components/crm/amount-input";
import { Field } from "@/components/crm/bits";
import { JalaliDateInput } from "@/components/crm/jalali-date-input";
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
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { todayIso } from "@/lib/jalali";
import { keys } from "@/lib/queries";

export function PaymentDialog({
  dealId,
  kind,
  trigger,
}: {
  dealId: string;
  kind: "payment" | "refund";
  trigger: ReactElement;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState<number | null>(null);
  const [paidOn, setPaidOn] = useState<string | null>(todayIso());
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const refund = kind === "refund";

  async function save() {
    if (!amount || !paidOn) {
      setError("مبلغ و تاریخ لازم است.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await apiFetch(`/deals/${dealId}/payments`, {
        method: "POST",
        body: JSON.stringify({ kind, amount, paid_on: paidOn, reference: reference || null, note: note || null }),
      });
      await queryClient.invalidateQueries({ queryKey: keys.deals });
      toast.success(refund ? "بازپرداخت ثبت شد." : "پرداخت ثبت شد.");
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setAmount(null);
          setPaidOn(todayIso());
          setReference("");
          setNote("");
          setError(null);
        }
      }}
    >
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{refund ? "ثبت بازپرداخت" : "ثبت پرداخت"}</DialogTitle>
          <DialogDescription>ثبت عملیاتی است و جایگزین حسابداری رسمی نیست.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="مبلغ" htmlFor="pay-amount" required>
            <AmountInput id="pay-amount" value={amount} onChange={setAmount} required />
          </Field>
          <Field label={refund ? "تاریخ بازپرداخت" : "تاریخ دریافت"} htmlFor="pay-date" required>
            <JalaliDateInput id="pay-date" value={paidOn} onChange={setPaidOn} required />
          </Field>
          <Field label="شماره پیگیری / مرجع" htmlFor="pay-ref">
            <Input id="pay-ref" dir="ltr" className="text-start" value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
          <Field label="یادداشت" htmlFor="pay-note">
            <Input id="pay-note" value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        </div>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button onClick={() => void save()} disabled={pending} variant={refund ? "destructive" : "default"}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ثبت
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
