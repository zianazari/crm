"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Loader2, Pause, Play, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import type { Campaign } from "@/lib/campaigns";
import { formatDateTime } from "@/lib/format";

export function CampaignActions({ campaign }: { campaign: Campaign }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  async function act(path: "pause" | "resume", message: string) {
    setBusy(true);
    try {
      const saved = await apiFetch<Campaign>(`/campaigns/${campaign.id}/${path}`, { method: "POST" });
      queryClient.setQueryData(["campaigns", campaign.id], saved);
      void queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success(message);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
    } finally {
      setBusy(false);
    }
  }
  if (campaign.status === "running") {
    return (
      <Button variant="outline" disabled={busy} onClick={() => void act("pause", "کمپین متوقف شد؛ پیام‌های ارسال‌نشده لغو شدند.")}>
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Pause aria-hidden />}
        توقف
      </Button>
    );
  }
  if (campaign.status === "paused") {
    return (
      <Button disabled={busy} onClick={() => void act("resume", "ارسال ادامه یافت.")}>
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Play aria-hidden />}
        ادامه ارسال
      </Button>
    );
  }
  if (campaign.status === "scheduled") {
    return (
      <Button variant="outline" disabled={busy} onClick={() => void act("pause", "زمان‌بندی لغو شد و کمپین به پیش‌نویس برگشت.")}>
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Pause aria-hidden />}
        لغو زمان‌بندی
      </Button>
    );
  }
  return null;
}

export function WaitingNotice({ campaign }: { campaign: Campaign }) {
  if (campaign.status === "scheduled" && campaign.scheduled_at) {
    return (
      <Alert>
        <CalendarClock aria-hidden />
        <AlertTitle>زمان‌بندی‌شده برای {formatDateTime(campaign.scheduled_at)}</AlertTitle>
        <AlertDescription>فهرست گیرندگان در همان زمان ثابت می‌شود.</AlertDescription>
      </Alert>
    );
  }
  if (!campaign.waiting_reason) return null;
  return (
    <Alert variant={campaign.status === "paused" ? "destructive" : "default"}>
      <TriangleAlert aria-hidden />
      <AlertTitle>{campaign.status === "paused" ? "متوقف شد" : "ارسال موقتاً منتظر است"}</AlertTitle>
      <AlertDescription>{campaign.waiting_reason}</AlertDescription>
    </Alert>
  );
}
