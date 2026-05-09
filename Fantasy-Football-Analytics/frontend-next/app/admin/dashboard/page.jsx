"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, Calendar, ShieldCheck, Users } from "lucide-react";
import { getAdminMatches, getAdminPlayers, getAdminStats } from "@/services/adminService";

export default function AdminDashboardPage() {
  const [stats, setStats] = useState(null);
  const [players, setPlayers] = useState([]);
  const [matches, setMatches] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    Promise.all([getAdminStats(), getAdminPlayers(), getAdminMatches()])
      .then(([adminStats, playerData, matchData]) => {
        if (!mounted) return;
        setStats(adminStats);
        setPlayers(playerData || []);
        setMatches(matchData || []);
      })
      .catch((err) => setError(err.message || "Failed to load admin dashboard."))
      .finally(() => setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  const cards = [
    { label: "Total Users", value: stats?.total_users ?? 0, icon: Users },
    { label: "Admins", value: stats?.admins ?? 0, icon: ShieldCheck },
    { label: "Players", value: players.length, icon: Activity },
    { label: "PL Matches", value: matches.length, icon: Calendar },
  ];

  return (
    <div className="container mx-auto p-6 md:p-10 space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Admin Dashboard</h1>
          <p className="text-muted-foreground mt-1">Monitor users, player data, and match schedules.</p>
        </div>
        <Link href="/admin/users" className="btn-primary w-fit">
          Manage Users
        </Link>
      </div>

      {error ? <div className="text-destructive bg-destructive/10 border border-destructive/20 rounded-lg p-4">{error}</div> : null}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {cards.map((card) => (
          <div key={card.label} className="card p-6 flex items-center gap-4">
            <div className="p-3 rounded-lg bg-muted/50 text-primary">
              <card.icon className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">{card.label}</p>
              <p className="text-2xl font-bold">{loading ? "..." : card.value}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h2 className="text-xl font-bold mb-4">Recent Players</h2>
          <div className="space-y-3">
            {players.slice(0, 8).map((player) => (
              <div key={player.id} className="flex items-center justify-between border border-border rounded-lg p-3">
                <div>
                  <p className="font-bold">{player.name}</p>
                  <p className="text-xs text-muted-foreground">{player.position} - {player.team}</p>
                </div>
                <span className="text-sm text-primary">EUR {(Number(player.value || 0) / 1000000).toFixed(1)}m</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-xl font-bold mb-4">Match Data Control</h2>
          <div className="space-y-3">
            {matches.slice(0, 8).map((match) => (
              <div key={match.id} className="flex items-center justify-between border border-border rounded-lg p-3">
                <div>
                  <p className="font-bold">{match.home_team} vs {match.away_team}</p>
                  <p className="text-xs text-muted-foreground">Matchweek {match.matchday || "-"} - {match.status}</p>
                </div>
                <span className="text-sm text-primary">{match.score || "Scheduled"}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
