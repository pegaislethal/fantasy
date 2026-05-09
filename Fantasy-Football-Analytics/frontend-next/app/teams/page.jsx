"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Users, ShieldCheck, Zap, Plus, ArrowRightLeft, Settings2, Filter, X } from "lucide-react";
import { getPlayers } from "@/services/footballApiService";
import { getMyTeam, updateTeam, createNewSquad } from "@/services/teamService";
import ProtectedRoute from "@/components/ProtectedRoute";
import { APP_ROUTES } from "@/utils/constants";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { y: 16, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
    transition: { type: "spring", stiffness: 110, damping: 16 },
  },
};

const FORMATION_PRESETS = [
  { name: "3-5-2", label: "3 DEF, 5 MID, 2 FWD", slots: [3, 5, 2, 1] },
  { name: "4-3-3", label: "4 DEF, 3 MID, 3 FWD", slots: [4, 3, 3, 1] },
  { name: "4-4-2", label: "4 DEF, 4 MID, 2 FWD", slots: [4, 4, 2, 1] },
  { name: "4-5-1", label: "4 DEF, 5 MID, 1 FWD", slots: [4, 5, 1, 1] },
  { name: "5-3-2", label: "5 DEF, 3 MID, 2 FWD", slots: [5, 3, 2, 1] },
  { name: "5-4-1", label: "5 DEF, 4 MID, 1 FWD", slots: [5, 4, 1, 1] },
];

export default function TeamsPage() {
  const [players, setPlayers] = useState([]);
  const [filter, setFilter] = useState("");
  const [team, setTeam] = useState({ players: [], formation: "4-4-2", budget: 100000000 });
  const [squads, setSquads] = useState([]);
  const [currentSquadId, setCurrentSquadId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showPlayerList, setShowPlayerList] = useState(false);
  const [showFormationMenu, setShowFormationMenu] = useState(false);
  const [selectedSlotIndex, setSelectedSlotIndex] = useState(null);

  useEffect(() => {
    let mounted = true;
    Promise.all([getPlayers(), getMyTeam()])
      .then(([p, t]) => {
        if (!mounted) return;
        setPlayers(p || []);
        if (t) {
          setTeam({ 
            players: t.players || [], 
            formation: t.formation || "4-4-2",
            budget: t.budget || 100000000
          });
        }
      })
      .catch((e) => console.warn("Failed to load team or players", e))
      .finally(() => setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  function filteredPlayers() {
    return players.filter((p) => p.name && p.name.toLowerCase().includes(filter.toLowerCase()));
  }

  async function handleChangeFormation(newFormation) {
    setTeam((t) => ({ ...t, formation: newFormation }));
    setShowFormationMenu(false);
    try {
      const updated = await updateTeam({ players: team.players, formation: newFormation });
      if (updated) {
        setTeam((t) => ({ 
          ...t, 
          players: updated.players || t.players, 
          formation: updated.formation || newFormation,
          budget: updated.budget ?? t.budget
        }));
      }
    } catch (e) {
      console.warn("Failed to update formation", e);
    }
  }

  async function handleRemovePlayer(slotIndex) {
    const newPlayers = team.players ? [...team.players] : [];
    newPlayers[slotIndex] = null;
    setTeam((t) => ({ ...t, players: newPlayers }));
    try {
      const updated = await updateTeam({ players: newPlayers, formation: team.formation });
      if (updated) {
        setTeam((t) => ({ 
          ...t, 
          players: updated.players || newPlayers,
          budget: updated.budget ?? t.budget
        }));
      }
    } catch (e) {
      console.warn("Failed to remove player", e);
    }
  }

  async function handleSelectPlayer(player) {
    // assign player to selected slot
    const newPlayers = team.players ? [...team.players] : [];
    if (selectedSlotIndex == null) {
      newPlayers.push({ id: player.id, name: player.name });
    } else {
      newPlayers[selectedSlotIndex] = { id: player.id, name: player.name };
    }
    setTeam((t) => ({ ...t, players: newPlayers }));
    setShowPlayerList(false);
    setSelectedSlotIndex(null);
    try {
      const updated = await updateTeam({ players: newPlayers, formation: team.formation });
      if (updated) {
        setTeam((t) => ({ 
          ...t, 
          players: updated.players || newPlayers,
          budget: updated.budget ?? t.budget
        }));
      }
    } catch (e) {
      console.warn("Failed to update team", e);
    }
  }

  async function handleNewSquad() {
    try {
      const res = await createNewSquad(team.formation);
      if (res) {
        setTeam({ players: [], formation: team.formation });
      }
    } catch (e) {
      console.warn("Failed to create new squad", e);
    }
  }

  function openPlayerSelector(slotIndex) {
    setSelectedSlotIndex(slotIndex);
    setShowPlayerList(true);
  }

  return (
    <ProtectedRoute>
      <div className="container mx-auto p-6 md:p-10 max-w-7xl">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-10"
      >
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <ShieldCheck className="h-8 w-8 text-primary" />
            Squad Management
          </h1>
          <p className="text-muted-foreground mt-1">
            Build, optimize, and manage your starting XI for the next gameweek.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-2">
            <input
              className="px-3 py-2 rounded-md border"
              placeholder="Filter players"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border bg-card hover:bg-muted/50 transition-colors text-sm font-medium"
              onClick={() => setShowPlayerList((s) => !s)}
            >
              <Filter className="h-4 w-4" />
              Browse
            </button>
          </div>
          <Link
            href={APP_ROUTES.transfers}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-primary/50 text-primary hover:bg-primary/5 transition-all text-sm font-bold"
          >
            <ArrowRightLeft className="h-4 w-4" />
            Transfer Market
          </Link>
          <button
            onClick={handleNewSquad}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity text-sm font-bold shadow-lg shadow-primary/20"
          >
            <Plus className="h-4 w-4" />
            New Squad
          </button>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Field View (Interactive) */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="lg:col-span-2 space-y-6"
        >
          <div
            className="card rounded-3xl relative overflow-hidden flex items-center justify-center p-8"
            style={{ aspectRatio: "4 / 5" }}
          >
            <div
              className="absolute inset-0 opacity-20 pointer-events-none"
              style={{
                backgroundImage:
                  "radial-gradient(circle at center, transparent 30%, #000 100%), repeating-linear-gradient(0deg, transparent, transparent 40px, rgba(255,255,255,0.05) 40px, rgba(255,255,255,0.05) 80px)",
              }}
            />

            <div className="relative z-10 w-full h-full flex flex-col justify-around py-4">
              {(() => {
                const [d, m, f] = team.formation.split("-").map(Number);
                const rows = [
                  { label: "FWD", count: f, start: 0, color: "primary" },
                  { label: "MID", count: m, start: f, color: "primary" },
                  { label: "DEF", count: d, start: f + m, color: "primary" },
                  { label: "GK", count: 1, start: f + m + d, color: "yellow-500" },
                  { label: "BENCH", count: 4, start: 11, color: "muted-foreground" },
                ];

                return rows.map((row, rowIdx) => (
                  <div key={rowIdx} className="flex justify-center gap-4 md:gap-12 px-4">
                    {Array.from({ length: row.count }).map((_, i) => {
                      const slotIdx = row.start + i;
                      const p = team.players?.[slotIdx];
                      const borderColor = row.color === "yellow-500" ? "hover:border-yellow-500" : "hover:border-primary";
                      const activeColor = row.color === "yellow-500" ? "border-yellow-500/40" : "border-primary/40";
                      
                      return (
                        <motion.div
                          key={i}
                          variants={itemVariants}
                          className="flex flex-col items-center gap-2"
                        >
                          <div
                            onClick={() => openPlayerSelector(slotIdx)}
                            className={`h-14 w-14 md:h-20 md:w-20 rounded-2xl ${p ? "bg-primary/10 " + activeColor : "bg-card border-border"} border-2 shadow-xl flex items-center justify-center group cursor-pointer ${borderColor} transition-all relative`}
                          >
                            {p ? (
                              <div className="text-[10px] md:text-xs font-black text-center px-1 leading-tight uppercase">
                                {p.name.split(' ').pop()}
                              </div>
                            ) : (
                              <Users className={`h-6 w-6 md:h-8 md:w-8 text-muted-foreground group-hover:text-${row.color}`} />
                            )}
                            
                            {p && (
                              <button 
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRemovePlayer(slotIdx);
                                }}
                                className="absolute -top-2 -right-2 h-5 w-5 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-lg"
                              >
                                <X className="h-3 w-3" />
                              </button>
                            )}
                          </div>
                          <span className="text-[8px] md:text-[10px] font-black bg-background/80 px-2 py-0.5 rounded text-muted-foreground border border-border/50 uppercase tracking-tighter">
                            {p ? p.team : row.label}
                          </span>
                        </motion.div>
                      );
                    })}
                  </div>
                ));
              })()}
            </div>
          </div>
        </motion.div>

        {/* Sidebar Controls */}
        <div className="space-y-6">
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="card p-6"
          >
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Zap className="h-5 w-5 text-primary" />
              Squad Intel
            </h3>
            <div className="space-y-4">
              <div className="flex justify-between items-center p-3 rounded-xl bg-muted/30 border border-border">
                <span className="text-sm text-muted-foreground font-medium">Budget Remaining</span>
                <span className="font-bold">£{(team.budget / 1000000).toFixed(1)}m</span>
              </div>
              <div className="flex justify-between items-center p-3 rounded-xl bg-muted/30 border border-border">
                <span className="text-sm text-muted-foreground font-medium">Free Transfers</span>
                <span className="font-bold text-green-500">2</span>
              </div>
              <div className="flex justify-between items-center p-3 rounded-xl bg-muted/30 border border-border">
                <span className="text-sm text-muted-foreground font-medium">Current Formation</span>
                <div className="flex items-center gap-2">
                  <span className="font-bold">{team.formation}</span>
                  <div className="relative">
                    <button
                      onClick={() => setShowFormationMenu((s) => !s)}
                      className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground hover:opacity-90"
                    >
                      Change
                    </button>
                    {showFormationMenu && (
                      <div className="absolute right-0 top-full mt-2 w-48 bg-card border border-border rounded-lg p-2 z-40 shadow-lg">
                        <div className="text-xs font-bold text-muted-foreground mb-2">
                          Preset Formations
                        </div>
                        {FORMATION_PRESETS.map((f) => (
                          <button
                            key={f.name}
                            onClick={() => handleChangeFormation(f.name)}
                            className={`w-full text-left px-2 py-2 rounded text-xs ${
                              team.formation === f.name
                                ? "bg-primary/20 text-primary font-bold"
                                : "hover:bg-muted/50"
                            }`}
                          >
                            <div className="font-bold">{f.name}</div>
                            <div className="text-muted-foreground">{f.label}</div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <button className="w-full mt-6 py-3 rounded-xl border border-primary text-primary font-bold text-sm hover:bg-primary/10 transition-colors flex items-center justify-center gap-2">
              <ArrowRightLeft className="h-4 w-4" />
              Auto-Optimize Squad
            </button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0, transition: { delay: 0.1 } }}
            className="card p-6"
          >
            <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Settings2 className="h-5 w-5 text-muted-foreground" />
              AI Strategy
            </h3>
            <div className="space-y-4">
              {team.players && team.players.length > 0 ? (
                <>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Your current squad is weighted towards defensive stability. AI suggests
                    targeting offensive assets for the upcoming Burnley (H) fixture.
                  </p>
                  <div className="h-2 w-full bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-primary w-[65%]" />
                  </div>
                  <p className="text-[10px] text-right text-muted-foreground font-bold uppercase tracking-wider">
                    Aggression Index: 65%
                  </p>
                </>
              ) : (
                <div className="text-xs text-muted-foreground p-3 bg-muted/30 rounded border border-border/50">
                  <p className="font-semibold text-primary mb-1">No players in squad</p>
                  <p>
                    Add players to your squad to receive AI strategy recommendations and transfer
                    insights.
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        </div>
      </div>

      {/* Player List Drawer */}
      {showPlayerList && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-start justify-end">
          <div className="w-full md:w-96 h-full bg-card p-4 overflow-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Players</h3>
              <button
                onClick={() => setShowPlayerList(false)}
                className="text-sm text-muted-foreground"
              >
                Close
              </button>
            </div>
            <input
              placeholder="Filter players by name"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full px-3 py-2 rounded-md border mb-4"
            />
            <div className="space-y-2">
              {filteredPlayers().map((p) => (
                <div
                  key={p.id}
                  className="p-2 border rounded cursor-pointer hover:bg-muted/30"
                  onClick={() => handleSelectPlayer(p)}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-bold">{p.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {p.position} — {p.team}
                      </div>
                    </div>
                    <div className="text-sm text-primary">Select</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      </div>
    </ProtectedRoute>
  );
}
