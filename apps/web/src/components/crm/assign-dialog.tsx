"use client";

import { useState, type ReactElement } from "react";
import { useQueryClient } from "@tanstack/react-query";
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
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { ApiError, apiFetch } from "@/lib/api";
import { useAssignableUsers } from "@/lib/queries";
import type { UserRef } from "@/lib/types";

/** Change owner of a lead or customer; recorded in ownership history (spec 4.1). */
export function AssignDialog({
  path,
  currentOwner,
  invalidate,
  trigger,
}: {
  path: string;
  currentOwner: UserRef;
  invalidate: readonly string[];
  trigger: ReactElement;
}) {
  const queryClient = useQueryClient();
  const { data: users = [] } = useAssignableUsers();
  const [open, setOpen] = useState(false);
  const [ownerId, setOwnerId] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);

  async function save() {
    setPending(true);
    try {
      await apiFetch(`${path}/assign`, {
        method: "POST",
        body: JSON.stringify({ owner_id: ownerId, reason: reason || null }),
      });
      await queryClient.invalidateQueries({ queryKey: invalidate });
      toast.success("مسئول تغییر کرد.");
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setOwnerId("");
        setReason("");
      }}
    >
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>تغییر مسئول</DialogTitle>
          <DialogDescription>مسئول فعلی: {currentOwner.full_name}. این تغییر در تاریخچه ثبت می‌شود.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="مسئول جدید" htmlFor="assign-owner" required>
            <NativeSelect
              id="assign-owner"
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value)}
              className="w-full"
            >
              <NativeSelectOption value="">انتخاب کنید</NativeSelectOption>
              {users
                .filter((u) => u.id !== currentOwner.id)
                .map((u) => (
                  <NativeSelectOption key={u.id} value={u.id}>
                    {u.full_name}
                  </NativeSelectOption>
                ))}
            </NativeSelect>
          </Field>
          <Field label="دلیل" htmlFor="assign-reason">
            <Input id="assign-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </div>
        <DialogFooter>
          <Button onClick={() => void save()} disabled={!ownerId || pending}>
            ثبت تغییر
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
