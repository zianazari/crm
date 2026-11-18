"use client";

import { useState, type ReactElement } from "react";
import { Loader2 } from "lucide-react";

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
import { Input } from "@/components/ui/input";

/** Confirms an action that needs a written reason (reopen, void, ...). */
export function ReasonDialog({
  title,
  description,
  confirmLabel,
  destructive,
  trigger,
  onConfirm,
  open: controlledOpen,
  onOpenChange,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  trigger?: ReactElement;
  onConfirm: (reason: string) => Promise<boolean>;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = (next: boolean) => {
    setInternalOpen(next);
    onOpenChange?.(next);
  };
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setReason("");
      }}
    >
      {trigger ? <DialogTrigger render={trigger} /> : null}
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          id="reason-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setPending(true);
            const ok = await onConfirm(reason.trim());
            setPending(false);
            if (ok) setOpen(false);
          }}
        >
          <Field label="دلیل" htmlFor="reason-input" required>
            <Input id="reason-input" required minLength={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </form>
        <DialogFooter>
          <Button
            type="submit"
            form="reason-form"
            variant={destructive ? "destructive" : "default"}
            disabled={pending || reason.trim().length < 2}
          >
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
