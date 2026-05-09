"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { LayoutDashboard, Users, Trophy, BrainCircuit, LogOut, Menu, User, Calendar, ArrowRightLeft, ShieldCheck } from "lucide-react";
import { APP_ROUTES } from "@/utils/constants";
import { useAuth } from "@/context/AuthContext";

const links = [
  { href: APP_ROUTES.dashboard, label: "Dashboard", icon: LayoutDashboard },
  { href: APP_ROUTES.team, label: "Team", icon: Users },
  { href: APP_ROUTES.transfers, label: "Transfers", icon: ArrowRightLeft },
  { href: APP_ROUTES.matches, label: "Matches", icon: Calendar },
  { href: APP_ROUTES.leaderboard, label: "Leaderboard", icon: Trophy },
  { href: APP_ROUTES.predictions, label: "AI Predictions", icon: BrainCircuit },
];

const adminLinks = [
  { href: "/admin/dashboard", label: "Admin", icon: ShieldCheck },
];

export default function Navbar() {
  const pathname = usePathname();
  const { isAuthenticated, user, logout } = useAuth();

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-border/30 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 shadow-sm">
      <div className="container mx-auto flex h-16 items-center px-4 md:px-8">
        <Link
          href={isAuthenticated ? APP_ROUTES.dashboard : APP_ROUTES.home}
          className="mr-8 flex items-center space-x-3"
          aria-label="Go to home"
        >
          <div
            role="img"
            aria-label="Fantasy Football logo"
            className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary/90 to-primary/60 text-primary-foreground font-bold text-lg shadow"
          >
            F
          </div>
          <span className="hidden font-bold sm:inline-block text-lg tracking-tight">
            Fantasy Football
          </span>
        </Link>

        <div className="flex flex-1 items-center justify-between space-x-2 md:justify-end">
          <nav className="hidden md:flex items-center space-x-6 text-sm font-medium">
            {[...links, ...(user?.role === "admin" ? adminLinks : [])]
              .filter((item) => {
                if (isAuthenticated) return true;
                // Hide protected routes if not authenticated
                const protectedRoutes = [
                  APP_ROUTES.dashboard,
                  APP_ROUTES.team,
                  APP_ROUTES.transfers,
                  APP_ROUTES.matches,
                  APP_ROUTES.leaderboard, // Leaderboard is usually protected too
                  APP_ROUTES.predictions
                ];
                return !protectedRoutes.includes(item.href);
              })
              .map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`relative flex items-center space-x-2 smooth-transition ${
                      isActive ? "text-foreground" : "text-foreground/70 hover:text-foreground"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                    {isActive && (
                      <motion.div
                        layoutId="navbar-active"
                        className="absolute -bottom-[21px] left-0 right-0 h-[2px] bg-primary"
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    )}
                  </Link>
                );
              })}
          </nav>
          <div className="flex items-center space-x-4">
            {/* Profile / Auth actions */}
            {isAuthenticated ? (
              <>
                <Link
                  href={APP_ROUTES.profile}
                  className="hidden md:inline-flex items-center gap-3"
                >
                  <div className="h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center font-semibold">
                    {user?.username?.[0]?.toUpperCase() || <User className="h-4 w-4" />}
                  </div>
                </Link>
                <button
                  onClick={logout}
                  className="btn-primary hidden md:inline-flex h-9"
                  aria-label="Sign out"
                  type="button"
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign Out
                </button>
              </>
            ) : (
              <>
                <Link
                  href={APP_ROUTES.login}
                  className="hidden md:inline-flex items-center text-sm font-medium text-foreground/80 hover:text-foreground"
                >
                  Log in
                </Link>
                <Link href={APP_ROUTES.signup} className="btn-primary hidden md:inline-flex h-9">
                  Sign up
                </Link>
                <Link
                  href={APP_ROUTES.login}
                  className="md:hidden flex items-center justify-center rounded-md w-9 h-9 border border-input bg-background/70 hover:bg-background/75 smooth-transition"
                  aria-label="Open menu"
                >
                  <User className="h-4 w-4" />
                </Link>
              </>
            )}
            <button
              className="md:hidden flex items-center justify-center rounded-md w-9 h-9 border border-input bg-background/70 hover:bg-background/75 smooth-transition"
              aria-label="Open menu"
              type="button"
            >
              <Menu className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
