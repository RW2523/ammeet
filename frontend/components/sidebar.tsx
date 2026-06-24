"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Users, Calendar, MessageSquare, BookOpen,
  Settings, LogOut, ChevronRight, Zap, CreditCard, Cpu, Radio
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore, useWorkspaceStore } from "@/lib/store";
import { Button } from "@/components/ui/button";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/workspaces", label: "Workspaces", icon: Settings },
  { href: "/settings/ai", label: "AI Model", icon: Cpu },
];

const workspaceNavItems = (id: string) => [
  { href: `/workspaces/${id}`, label: "Overview", icon: LayoutDashboard },
  { href: `/workspaces/${id}/people`, label: "People & Roles", icon: Users },
  { href: `/workspaces/${id}/meetings`, label: "Meetings", icon: Calendar },
  { href: `/workspaces/${id}/test-join`, label: "Live Test (Join)", icon: Radio },
  { href: `/workspaces/${id}/knowledge`, label: "Knowledge Base", icon: BookOpen },
  { href: `/workspaces/${id}/integrations`, label: "Integrations", icon: Zap },
  { href: `/workspaces/${id}/billing`, label: "Plan & Billing", icon: CreditCard },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, clearAuth } = useAuthStore();
  const { current } = useWorkspaceStore();

  const handleLogout = () => {
    clearAuth();
    router.push("/auth/login");
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-800">
        <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center flex-shrink-0">
          <span className="text-white text-sm font-bold">AM</span>
        </div>
        <div>
          <p className="text-white font-semibold text-sm">AmMeeting</p>
          <p className="text-slate-500 text-xs">AI Meeting Assistant</p>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
              pathname === item.href
                ? "bg-blue-600 text-white"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            )}
          >
            <item.icon className="h-4 w-4 flex-shrink-0" />
            {item.label}
          </Link>
        ))}

        {current && (
          <>
            <div className="pt-4 pb-2 px-3">
              <div className="flex items-center gap-2">
                <ChevronRight className="h-3 w-3 text-slate-500" />
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider truncate">
                  {current.name}
                </p>
              </div>
            </div>
            {workspaceNavItems(current.id).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                  pathname.startsWith(item.href) && pathname === item.href
                    ? "bg-slate-700 text-white"
                    : "text-slate-400 hover:text-white hover:bg-slate-800"
                )}
              >
                <item.icon className="h-4 w-4 flex-shrink-0" />
                {item.label}
              </Link>
            ))}
          </>
        )}
      </nav>

      {/* User footer */}
      <div className="border-t border-slate-800 p-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-full bg-blue-700 flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-bold">
              {user?.full_name?.charAt(0) ?? "?"}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-white truncate">{user?.full_name}</p>
            <p className="text-xs text-slate-500 truncate">{user?.email}</p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-slate-400 hover:text-white"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4 mr-2" />
          Sign out
        </Button>
      </div>
    </aside>
  );
}
