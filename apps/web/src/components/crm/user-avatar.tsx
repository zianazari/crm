import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import type { UserRef } from "@/lib/types";
import { cn } from "@/lib/utils";

export function avatarUrl(user: Pick<UserRef, "id" | "avatar_version">): string | null {
  return user.avatar_version ? `/api/users/${user.id}/avatar?v=${user.avatar_version}` : null;
}

/** A person's photo, or their initial when they have none (or it fails to load).
 * Persian letters join when adjacent, so one letter reads more cleanly than two. */
export function UserAvatar({ user, className }: { user: UserRef; className?: string }) {
  const src = avatarUrl(user);
  return (
    <Avatar className={cn("size-7", className)}>
      {src ? <AvatarImage src={src} alt="" className="object-cover" /> : null}
      <AvatarFallback className="bg-accent text-[0.75em] font-medium text-accent-foreground">
        {user.full_name.trim().charAt(0)}
      </AvatarFallback>
    </Avatar>
  );
}
