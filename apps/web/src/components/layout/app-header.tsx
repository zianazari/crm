import { Search } from "lucide-react";

import { MobileNav } from "@/components/layout/mobile-nav";
import { NotificationBell } from "@/components/layout/notification-bell";
import { UserMenu } from "@/components/layout/user-menu";

export function AppHeader() {
  return (
    <header className="sticky top-0 z-10 flex h-16 items-center gap-4 border-b bg-background/90 px-4 backdrop-blur md:px-6">
      <MobileNav />
      <form role="search" className="relative w-full max-w-md">
        <Search
          aria-hidden
          className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <label htmlFor="global-search" className="sr-only">
          جست‌وجو
        </label>
        <input
          id="global-search"
          name="q"
          type="search"
          placeholder="جست‌وجو در مشتریان، فروش‌ها، فعالیت‌ها و …"
          className="h-10 w-full rounded-lg border bg-card ps-9 pe-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
        />
      </form>
      <div className="ms-auto flex items-center gap-2">
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  );
}
