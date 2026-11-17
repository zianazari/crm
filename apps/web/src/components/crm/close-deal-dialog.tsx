"use client";

import { useState } from "react";
import { CircleCheck, CircleX, Loader2 } from "lucide-react";
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
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { todayIso } from "@/lib/jalali";
import { keys } from "@/lib/queries";
import type { DealFull } from "@/lib/types";
import { cn } from "@/lib/utils";

export type CloseMode = "won" | "lost";

/** Close a deal. Won needs the contract amount and date; lost needs a reason (spec 4.3). */
export function CloseDealDialog({
  deal,
  mode,
  onOpenChange,
}: {
  deal: DealFull;
  mode: CloseMode | null;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<CloseMode>(mode ?? "won");
  const [amount, setAmount] = useState<number | null>(deal.amount);
  const [contractDate, setContractDate] = useState<string | null>(todayIso());
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (selected === "won" && (amount === null || !contractDate)) {
      setError("مبلغ و تاریخ قرارداد لازم است.");
      return;
    }
    if (selected === "lost" && reason.trim().length < 2) {
      setError("دلیل را بنویسید.");
      return;
    }
    setPending(true);
    try {
      await apiFetch(`/deals/${deal.id}/${selected === "won" ? "win" : "lose"}`, {
        method: "POST",
        body: JSON.stringify(
          selected === "won"
            ? { contract_amount: amount, contract_date: contractDate, version: deal.version }
            : { lost_reason: reason, version: deal.version },
        ),
      });
      toast.success(selected === "won" ? "فروش با موفقیت بسته شد." : "فروش به‌عنوان «به نتیجه نرسید» بسته شد.");
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
      await queryClient.invalidateQueries({ queryKey: keys.deals });
    }
  }

  return (
    <Dialog open={mode !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>نتیجه نهایی «{deal.title}»</DialogTitle>
          <DialogDescription>{deal.customer.full_name}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="نتیجه">
          {(
            [
              { value: "won", label: "فروش انجام شد", icon: CircleCheck, tone: "border-primary bg-accent text-accent-foreground" },
              { value: "lost", label: "به نتیجه نرسید", icon: CircleX, tone: "border-destructive bg-destructive/10 text-destructive" },
            ] as const
          ).map(({ value, label, icon: Icon, tone }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={selected === value}
              onClick={() => setSelected(value)}
              className={cn(
                "flex items-center justify-center gap-2 rounded-lg border py-2.5 text-sm font-medium",
                selected === value ? tone : "text-muted-foreground hover:bg-muted",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>

        {selected === "won" ? (
          <div className="space-y-4">
            <Field label="مبلغ قرارداد" htmlFor="contract-amount" required>
              <AmountInput id="contract-amount" value={amount} onChange={setAmount} required />
            </Field>
            <Field label="تاریخ قرارداد" htmlFor="contract-date" required>
              <JalaliDateInput id="contract-date" value={contractDate} onChange={setContractDate} required />
            </Field>
          </div>
        ) : (
          <Field label="دلیل" htmlFor="lost-reason" required>
            <Input
              id="lost-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="مثلاً قیمت بالا، انتخاب رقیب، نبود بودجه"
            />
          </Field>
        )}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            onClick={() => void submit()}
            disabled={pending}
            variant={selected === "lost" ? "destructive" : "default"}
          >
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ثبت نتیجه
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
