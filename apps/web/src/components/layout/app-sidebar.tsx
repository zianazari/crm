"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { mainNav, secondaryNav, type NavItem } from "@/lib/navigation";

export function Logo() {
  return (
    <Link href="/overview" className="flex items-center gap-2 px-3 py-1">
      <span
        aria-hidden
        className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground"
      >
        <svg viewBox="0 0 24 24" className="size-5" fill="currentColor">
          <path d="M14.5 3 21 9.5 9.5 21 3 14.5z" opacity=".55" />
          <path d="M14.5 3 21 9.5l-4 4L10.5 7z" />
        </svg>
      </span>
      <span className="text-xl font-extrabold tracking-tight">CRM</span>
    </Link>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-sidebar-foreground transition-colors",
        "hover:bg-sidebar-accent/60 focus-visible:outline-2 focus-visible:outline-sidebar-ring",
        active && "bg-sidebar-accent text-sidebar-accent-foreground font-semibold",
      )}
    >
      <Icon className="size-5 shrink-0" aria-hidden />
      <span>{item.label}</span>
    </Link>
  );
}

/** Navigation links shared by the desktop sidebar and the mobile menu. */
export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <div className="flex flex-1 flex-col gap-6" onClick={onNavigate}>
      <nav aria-label="منوی اصلی" className="flex flex-1 flex-col gap-1 px-3">
        {mainNav.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item.href)} />
        ))}
      </nav>
      <nav aria-label="مدیریت" className="flex flex-col gap-1 px-3">
        {secondaryNav.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item.href)} />
        ))}
      </nav>
    </div>
  );
}

export function AppSidebar() {
  return (
    <aside className="sticky top-0 hidden h-svh w-60 shrink-0 flex-col gap-6 border-e border-sidebar-border bg-sidebar py-5 lg:flex">
      <Logo />
      <SidebarNav />
    </aside>
  );
}
