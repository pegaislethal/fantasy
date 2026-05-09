"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, UserCheck, UserX } from "lucide-react";
import { getAdminUsers, updateAdminUser } from "@/services/adminService";
import AdminRoute from "@/components/AdminRoute";

export default function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadUsers() {
    try {
      const data = await getAdminUsers();
      setUsers(data || []);
    } catch (err) {
      setError(err.message || "Failed to load users.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let mounted = true;
    getAdminUsers()
      .then((data) => {
        if (mounted) setUsers(data || []);
      })
      .catch((err) => {
        if (mounted) setError(err.message || "Failed to load users.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  async function updateUser(userId, payload) {
    try {
      const updated = await updateAdminUser(userId, payload);
      setUsers((rows) => rows.map((row) => (row.id === userId ? updated : row)));
    } catch (err) {
      setError(err.message || "Failed to update user.");
    }
  }

  return (
    <AdminRoute>
    <div className="container mx-auto p-6 md:p-10">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Admin Users</h1>
        <p className="text-muted-foreground mt-1">Manage roles and account access.</p>
      </div>

      {error ? <div className="text-destructive bg-destructive/10 border border-destructive/20 rounded-lg p-4 mb-6">{error}</div> : null}

      <div className="card overflow-hidden">
        <div className="grid grid-cols-12 gap-4 px-6 py-4 bg-muted/50 text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          <div className="col-span-5">User</div>
          <div className="col-span-2">Role</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-3 text-right">Actions</div>
        </div>
        <div className="divide-y divide-border">
          {loading ? (
            <div className="p-8 text-muted-foreground">Loading users...</div>
          ) : users.length === 0 ? (
            <div className="p-8 text-muted-foreground">No users found.</div>
          ) : (
            users.map((user) => (
              <div key={user.id} className="grid grid-cols-12 gap-4 px-6 py-4 items-center">
                <div className="col-span-5">
                  <p className="font-bold">{user.username || user.email}</p>
                  <p className="text-xs text-muted-foreground">{user.email}</p>
                </div>
                <div className="col-span-2">
                  <span className="inline-flex items-center gap-1 text-sm">
                    <ShieldCheck className="h-4 w-4 text-primary" />
                    {user.is_staff ? "Admin" : "User"}
                  </span>
                </div>
                <div className="col-span-2">
                  <span className={user.is_active ? "text-green-400" : "text-destructive"}>
                    {user.is_active ? "Active" : "Locked"}
                  </span>
                </div>
                <div className="col-span-3 flex justify-end gap-2">
                  <button
                    className="px-3 py-2 rounded-lg border border-border text-xs font-bold hover:bg-muted"
                    onClick={() => updateUser(user.id, { is_staff: !user.is_staff })}
                  >
                    {user.is_staff ? "Make User" : "Make Admin"}
                  </button>
                  <button
                    className="px-3 py-2 rounded-lg border border-border text-xs font-bold hover:bg-muted inline-flex items-center gap-1"
                    onClick={() => updateUser(user.id, { is_active: !user.is_active })}
                  >
                    {user.is_active ? <UserX className="h-3 w-3" /> : <UserCheck className="h-3 w-3" />}
                    {user.is_active ? "Lock" : "Unlock"}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
    </AdminRoute>
  );
}
