import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2, ShieldCheck } from "lucide-react";
import {
  AdminUser, listAdminUsers, addAdminUser, removeAdminUser,
} from "../lib/admin";
import { formatUploadTime } from "../lib/api";

/**
 * The admin allowlist.
 *
 * This panel decides who else can reach this console, so it is the most
 * dangerous thing on the page. The server refuses to remove the last admin or
 * to let anyone remove themselves; both are re-checked there rather than only
 * hidden here, because a disabled button is a hint, not a control.
 */
interface AdminUsersProps {
  /** The signed-in operator, so their own row can be marked and protected. */
  currentEmail: string;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

export const AdminUsers = ({ currentEmail, onError, onNotice }: AdminUsersProps) => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUsers(await listAdminUsers());
    } catch (err: any) {
      onError(err.message);
    }
  }, [onError]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try {
      await action();
      onNotice(success);
      await refresh();
    } catch (err: any) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const address = email.trim().toLowerCase();
    if (!address) return;
    run(() => addAdminUser(address), `${address} can now sign in`).then(() =>
      setEmail("")
    );
  };

  const activeCount = users.filter((u) => u.active).length;

  return (
    <div className="rounded-2xl border border-hairline bg-card overflow-hidden">
      <div className="px-4 py-3 border-b border-hairline flex items-center gap-2">
        <ShieldCheck className="w-4 h-4 text-fg-muted" />
        <h2 className="text-sm font-bold">Admins ({users.length})</h2>
      </div>

      <form onSubmit={submit} className="p-4 flex gap-2 border-b border-hairline">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@example.com"
          aria-label="Email address to grant admin access"
          className="flex-1 bg-input border border-hairline rounded-xl px-3 py-2 text-sm text-fg focus:outline-none focus:border-vibe-purple transition-colors"
        />
        <button
          type="submit"
          disabled={busy || !email.trim()}
          className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-gradient-to-r from-vibe-blue to-vibe-purple text-white text-xs font-bold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Plus className="w-3.5 h-3.5" />
          Add
        </button>
      </form>

      <ul className="divide-y divide-hairline">
        {users.map((user) => {
          const isSelf = user.email === currentEmail;
          // Mirrors the server's two guards, so the button explains itself
          // rather than producing a 400 on click.
          const blocked = isSelf || activeCount <= 1;
          return (
            <li key={user.email} className="px-4 py-3 flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-fg truncate">
                  {user.email}
                  {isSelf && (
                    <span className="ml-2 text-[9px] uppercase tracking-wider font-bold text-fg-muted">
                      you
                    </span>
                  )}
                </p>
                <p className="text-[11px] text-fg-muted">
                  Added by {user.addedBy || "unknown"}
                  {user.addedAt && ` · ${formatUploadTime(user.addedAt)}`}
                </p>
              </div>
              <button
                onClick={() =>
                  run(
                    () => removeAdminUser(user.email),
                    `${user.email} can no longer sign in`
                  )
                }
                disabled={busy || blocked}
                title={
                  isSelf
                    ? "You cannot remove your own access"
                    : activeCount <= 1
                      ? "Cannot remove the last admin"
                      : `Remove ${user.email}`
                }
                className="shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-red-600/40 text-red-600 text-xs font-bold hover:bg-red-500/10 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Remove
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
