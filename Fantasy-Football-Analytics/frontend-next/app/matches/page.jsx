"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Calendar, Clock, Trophy, ChevronRight, Filter, AlertCircle } from "lucide-react";
import { getMatches } from "@/services/footballApiService";
import ProtectedRoute from "@/components/ProtectedRoute";

export default function MatchesPage() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("all"); // all, finished, scheduled

  useEffect(() => {
    getMatches()
      .then((data) => {
        setMatches(data || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch matches:", err);
        setError("Unable to load match data. Please try again later.");
        setLoading(false);
      });
  }, []);

  const filteredMatches = matches.filter((m) => {
    if (activeTab === "finished") return m.status === "FINISHED";
    if (activeTab === "scheduled") return m.status === "SCHEDULED" || m.status === "TIMED";
    return true;
  });

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  };

  const formatTime = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <ProtectedRoute>
      <div className="container mx-auto p-6 md:p-10 max-w-5xl">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-10"
      >
        <h1 className="text-4xl font-extrabold tracking-tight mb-2">Premier League Fixtures</h1>
        <p className="text-muted-foreground text-lg">
          Stay updated with the latest results and upcoming matches from the Premier League.
        </p>
      </motion.div>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div className="flex p-1 bg-muted rounded-xl w-fit">
          {["all", "finished", "scheduled"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-6 py-2 rounded-lg text-sm font-bold transition-all ${
                activeTab === tab
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/30 px-4 py-2 rounded-lg border border-border">
          <Filter className="h-4 w-4" />
          <span>Showing {filteredMatches.length} matches</span>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-4">
          <div className="h-12 w-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          <p className="text-muted-foreground animate-pulse">Fetching match data...</p>
        </div>
      ) : error ? (
        <div className="card p-12 text-center flex flex-col items-center border-destructive/20 bg-destructive/5">
          <AlertCircle className="h-12 w-12 text-destructive mb-4" />
          <h3 className="text-xl font-bold mb-2">Something went wrong</h3>
          <p className="text-muted-foreground max-w-md">{error}</p>
          <button 
            onClick={() => window.location.reload()}
            className="mt-6 px-6 py-2 bg-primary text-primary-foreground rounded-lg font-bold"
          >
            Try Again
          </button>
        </div>
      ) : (
        <div className="grid gap-6">
          {filteredMatches.length > 0 ? (
            filteredMatches.map((match, idx) => (
              <motion.div
                key={match.id || idx}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="group relative"
              >
                <div className="card hover:border-primary/50 transition-all duration-300 overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-primary opacity-0 group-hover:opacity-100 transition-opacity"></div>
                  
                  <div className="p-6 flex flex-col md:flex-row items-center justify-between gap-6">
                    {/* Date & Time */}
                    <div className="flex flex-col items-center md:items-start min-w-[120px]">
                      <div className="flex items-center gap-2 text-muted-foreground mb-1">
                        <Calendar className="h-4 w-4" />
                        <span className="text-xs font-bold uppercase tracking-wider">{formatDate(match.kickoff)}</span>
                      </div>
                      <div className="flex items-center gap-2 font-mono text-sm">
                        <Clock className="h-4 w-4 text-primary" />
                        <span>{formatTime(match.kickoff)}</span>
                      </div>
                    </div>

                    {/* Teams & Score */}
                    <div className="flex-1 flex items-center justify-center gap-4 md:gap-8 w-full">
                      <div className="flex-1 text-right">
                        <span className="text-lg md:text-xl font-bold truncate block">{match.home_team}</span>
                      </div>
                      
                      <div className="flex flex-col items-center justify-center min-w-[80px]">
                        {match.status === "FINISHED" ? (
                          <div className="bg-primary/10 text-primary px-4 py-2 rounded-xl border border-primary/20 flex items-center gap-3">
                            <span className="text-2xl font-black">{match.score.split(' - ')[0]}</span>
                            <span className="text-muted-foreground font-light">:</span>
                            <span className="text-2xl font-black">{match.score.split(' - ')[1]}</span>
                          </div>
                        ) : (
                          <div className="bg-muted px-4 py-2 rounded-xl text-xs font-bold text-muted-foreground uppercase tracking-widest border border-border">
                            VS
                          </div>
                        )}
                        <span className={`text-[10px] mt-2 font-bold uppercase tracking-tighter ${match.status === "FINISHED" ? "text-green-500" : "text-yellow-500"}`}>
                          {match.status}
                        </span>
                      </div>

                      <div className="flex-1 text-left">
                        <span className="text-lg md:text-xl font-bold truncate block">{match.away_team}</span>
                      </div>
                    </div>

                    {/* Action */}
                    <div className="hidden md:block">
                      <button className="h-10 w-10 rounded-full bg-muted flex items-center justify-center hover:bg-primary hover:text-primary-foreground transition-all">
                        <ChevronRight className="h-5 w-5" />
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))
          ) : (
            <div className="card p-20 text-center flex flex-col items-center">
              <Trophy className="h-12 w-12 text-muted-foreground mb-4 opacity-20" />
              <p className="text-muted-foreground text-lg italic">No matches found for this filter.</p>
            </div>
          )}
        </div>
      )}
      </div>
    </ProtectedRoute>
  );
}
