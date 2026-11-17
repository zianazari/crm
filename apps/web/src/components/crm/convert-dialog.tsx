"use client";

import { useState, type ReactElement } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
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
import { ApiError, apiFetch, duplicateMatches } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { ConvertResult, DuplicateMatch, LeadFull } from "@/lib/types";

/** Convert a lead into a customer. If a customer with the same mobile/email exists,
 * offer to attach the lead to it instead of creating a duplicate (spec section 3). */
export function ConvertDialog({ lead, trigger }: { lead: LeadFull; trigger: ReactElement }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [jobTitle, setJobTitle] = useState("");
  const [matches, setMatches] = useState<DuplicateMatch[] | null>(null);
  const [pending, setPending] = useState(false);

  async function convert(options: { customerId?: string; allowDuplicate?: boolean } = {}) {
    setPending(true);
    try {
      const result = await apiFetch<ConvertResult>(
        `/leads/${lead.id}/convert${options.allowDuplicate ? "?allow_duplicate=true" : ""}`,
        {
          method: "POST",
          body: JSON.stringify({ customer_id: options.customerId ?? null, job_title: jobTitle || null }),
        },
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.leads }),
        queryClient.invalidateQueries({ queryKey: keys.customers }),
      ]);
      toast.success(result.created_customer ? "مشتری جدید ساخته شد." : "به پرونده مشتری موجود متصل شد.");
      router.push(`/customers/${result.customer_id}`);
    } catch (err) {
      const found = duplicateMatches(err);
      if (found) setMatches(found);
      else toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setMatches(null);
      }}
    >
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>تبدیل به مشتری</DialogTitle>
          <DialogDescription>
            پرونده مشتری با همین اطلاعات، منبع و مسئول ساخته می‌شود و سابقه این سرنخ حفظ می‌شود.
            {lead.company_name ? ` «${lead.company_name}» به‌عنوان سازمان مشتری ثبت می‌شود.` : null}
          </DialogDescription>
        </DialogHeader>

        {lead.company_name && !matches ? (
          <Field label="سمت در سازمان" htmlFor="convert-job">
            <Input id="convert-job" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
          </Field>
        ) : null}

        {matches ? (
          <div className="space-y-3">
            <p className="text-sm">مشتری با همین موبایل یا ایمیل وجود دارد:</p>
            <ul className="space-y-2">
              {matches.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm">
                  <div>
                    <div className="font-medium">{m.full_name}</div>
                    <div className="text-xs text-muted-foreground">مسئول: {m.owner.full_name}</div>
                  </div>
                  {m.access === "full" ? (
                    <Button size="sm" disabled={pending} onClick={() => void convert({ customerId: m.id })}>
                      اتصال به این پرونده
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">با مسئول هماهنگ کنید</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <DialogFooter>
          {matches ? (
            <Button variant="outline" disabled={pending} onClick={() => void convert({ allowDuplicate: true })}>
              ساخت مشتری جداگانه
            </Button>
          ) : (
            <Button disabled={pending} onClick={() => void convert()}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              تبدیل
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
