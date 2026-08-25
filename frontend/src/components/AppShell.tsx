import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { useLogoutFlow } from "../auth/LogoutFlow";
import { PulseIcon } from "./Icons";

function initials(user: { name: string; username: string }): string {
  const source = (user.name || user.username).trim();
  const parts = source.split(/[\s-_]+/).filter(Boolean);
  const letters =
    parts.length >= 2
      ? `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}`
      : source.slice(0, 2);
  return letters.toUpperCase();
}

/** The sticky top bar every signed-in page sits under. */
export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { requestLogout } = useLogoutFlow();
  const navigate = useNavigate();

  return (
    <>
      <nav
        style={{
          position: "sticky",
          top: 0,
          zIndex: 30,
          display: "flex",
          alignItems: "center",
          gap: 22,
          padding: "12px 26px",
          background: "color-mix(in srgb, var(--color-bg) 84%, transparent)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid var(--color-divider)",
        }}
      >
        <div
          style={{ display: "flex", alignItems: "center", gap: 9, cursor: "pointer" }}
          onClick={() => navigate("/dashboard")}
        >
          <span
            style={{
              width: 26,
              height: 26,
              display: "grid",
              placeItems: "center",
              border: "1px solid var(--color-accent)",
              color: "var(--color-accent)",
            }}
          >
            <PulseIcon size={15} />
          </span>
          <span
            style={{
              fontFamily: "var(--font-heading)",
              fontWeight: 600,
              fontSize: 17,
              letterSpacing: ".04em",
              whiteSpace: "nowrap",
            }}
          >
            REPO VITALS
          </span>
        </div>

        <NavLink
          to="/dashboard"
          className="nav-link"
          style={{ color: "inherit", textDecoration: "none", fontSize: 14 }}
        >
          Repositories
        </NavLink>
        {/* Documentation is a Phase 14 deliverable; shown inert so the nav
            does not shift shape when it lands. */}
        <span className="text-muted" style={{ fontSize: 14 }}>
          Documentation
        </span>

        <div
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: 14,
          }}
        >
          {user && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {user.avatarUrl ? (
                <img
                  src={user.avatarUrl}
                  alt=""
                  width={26}
                  height={26}
                  style={{ borderRadius: "50%" }}
                />
              ) : (
                <span
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: "50%",
                    background: "var(--color-accent)",
                    color: "var(--color-bg)",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 11,
                    fontFamily: "var(--font-heading)",
                    fontWeight: 600,
                  }}
                >
                  {initials(user)}
                </span>
              )}
              <span style={{ fontSize: 14 }}>{user.username}</span>
            </div>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            style={{ height: 34 }}
            onClick={requestLogout}
          >
            Sign out
          </button>
        </div>
      </nav>
      {children}
    </>
  );
}
