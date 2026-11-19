"use client";

import { useRef, useState } from "react";
import { ImageUp, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { UserAvatar } from "@/components/crm/user-avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, apiFetch, type CurrentUser } from "@/lib/api";

const SIZE = 256;

/** Crops the middle square and shrinks it to 256px, so uploads stay small (the API
 * takes at most 200 KB). WebP where the browser can encode it, JPEG otherwise. */
async function squareImage(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas");
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, SIZE, SIZE);
  bitmap.close();
  const encode = (type: string) =>
    new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, 0.85));
  const webp = await encode("image/webp");
  if (webp && webp.type === "image/webp") return webp;
  const jpeg = await encode("image/jpeg");
  if (!jpeg) throw new Error("encode");
  return jpeg;
}

export function ProfilePhotoDialog({
  user,
  open,
  onOpenChange,
  onSaved,
}: {
  user: CurrentUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (user: CurrentUser) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<{ blob: Blob; url: string } | null>(null);
  const [pending, setPending] = useState(false);

  function reset(next: boolean) {
    if (preview) URL.revokeObjectURL(preview.url);
    setPreview(null);
    onOpenChange(next);
  }

  async function choose(file: File | undefined) {
    if (!file) return;
    try {
      const blob = await squareImage(file);
      if (preview) URL.revokeObjectURL(preview.url);
      setPreview({ blob, url: URL.createObjectURL(blob) });
    } catch {
      toast.error("این فایل تصویر قابل خواندن نیست.");
    }
  }

  async function save(remove = false) {
    setPending(true);
    try {
      const saved = await apiFetch<CurrentUser>("/users/me/avatar", {
        method: remove ? "DELETE" : "PUT",
        body: remove ? undefined : preview?.blob,
        headers: remove || !preview ? undefined : { "Content-Type": preview.blob.type },
      });
      onSaved({ ...user, avatar_version: saved.avatar_version });
      toast.success(remove ? "تصویر حذف شد." : "تصویر پروفایل ذخیره شد.");
      reset(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ذخیره نشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>تصویر پروفایل</DialogTitle>
          <DialogDescription>همکاران این تصویر را کنار نام شما در پرونده‌ها، تابلو و فعالیت‌ها می‌بینند.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col items-center gap-4 py-2">
          {preview ? (
            // eslint-disable-next-line @next/next/no-img-element -- a local preview (blob URL)
            <img src={preview.url} alt="پیش‌نمایش تصویر" className="size-28 rounded-full object-cover ring-1 ring-border" />
          ) : (
            <UserAvatar user={user} className="size-28 text-3xl" />
          )}
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            aria-label="انتخاب تصویر"
            onChange={(e) => {
              void choose(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <Button variant="outline" onClick={() => input.current?.click()} disabled={pending}>
            <ImageUp aria-hidden />
            {preview || user.avatar_version ? "انتخاب تصویر دیگر" : "انتخاب تصویر"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">وسط تصویر به شکل مربع برداشته و کوچک می‌شود.</p>
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          {user.avatar_version && !preview ? (
            <Button variant="ghost" className="text-destructive" onClick={() => void save(true)} disabled={pending}>
              <Trash2 aria-hidden />
              حذف تصویر
            </Button>
          ) : (
            <span />
          )}
          <Button onClick={() => void save()} disabled={pending || !preview}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ذخیره
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
