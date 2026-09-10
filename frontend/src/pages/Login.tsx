import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { BlueprintCorners } from "../components/Blueprint";
import {
  BookIcon,
  ChartIcon,
  GitHubIcon,
  LockIcon,
  PackageIcon,
  PulseIcon,
} from "../components/Icons";

/** A claim row in the left column. */
function Claim({ icon, children }: { icon: ReactNode; children: string }) {
  return (
    <div style={{ display: "flex", gap: 9, alignItems: "flex-start", fontSize: 13 }}>
      {icon}
      <span>{children}</span>
    </div>
  );
}

/** One package row in the specimen panel. */
function SpecimenRow({
  label,
  tag,
  bg,
  fg,
}: {
  label: string;
  tag: string;
  bg: string;
  fg: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 8,
        fontSize: 12,
      }}
    >
      <code>{label}</code>
      <span className="tag" style={{ background: bg, color: fg, whiteSpace: "nowrap" }}>
        {tag}
      </span>
    </div>
  );
}

export function Login() {
  const { login } = useAuth();
  const [params] = useSearchParams();
  const oauthFailed = params.get("error") === "github_oauth_failed";

  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 32 }}>
      <div
        className="blueprint elev-lg"
        style={{
          width: "min(960px, 100%)",
          display: "grid",
          gridTemplateColumns: "1.06fr .94fr",
          border: "1px solid var(--color-divider)",
          background: "color-mix(in srgb, var(--color-bg) 72%, transparent)",
        }}
      >
        <BlueprintCorners />

        {/* ── Left: the pitch and the only action on the page ───────────── */}
        <div style={{ padding: "46px 42px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                width: 30,
                height: 30,
                display: "grid",
                placeItems: "center",
                border: "1px solid var(--color-accent)",
                color: "var(--color-accent)",
              }}
            >
              <PulseIcon size={17} />
            </span>
            <span
              style={{
                fontFamily: "var(--font-heading)",
                fontWeight: 600,
                fontSize: 19,
                letterSpacing: ".045em",
                whiteSpace: "nowrap",
              }}
            >
              REPO VITALS
            </span>
            <span className="tag tag-outline" style={{ marginLeft: 2 }}>
              v1.1
            </span>
          </div>

          <h1 style={{ fontSize: 39, margin: "30px 0 0", lineHeight: 1.04 }}>
            Turn a risk flag
            <br />
            into a fix.
          </h1>
          <p
            className="text-muted"
            style={{ marginTop: 13, maxWidth: "42ch", fontSize: 15 }}
          >
            Repo Vitals scores your repositories&apos; dependency health, then an
            agentic RAG pipeline explains every flagged package with grounded,
            cited remediation — never a guess.
          </p>

          {oauthFailed && (
            <div
              role="alert"
              className="tag"
              style={{
                background: "#efddda",
                color: "#6a2a23",
                marginTop: 18,
                display: "block",
                padding: "8px 12px",
                fontSize: 12.5,
                lineHeight: 1.45,
              }}
            >
              We couldn&apos;t complete the GitHub sign-in. Please try again.
            </div>
          )}

          <button
            type="button"
            className="btn btn-primary btn-block"
            style={{ marginTop: 26, height: 47, fontSize: 15 }}
            onClick={login}
          >
            <GitHubIcon size={17} />
            Continue with GitHub
          </button>

          <p
            className="text-muted"
            style={{
              fontSize: 12,
              marginTop: 13,
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
              lineHeight: 1.5,
            }}
          >
            <LockIcon size={14} style={{ flex: "none", marginTop: 2 }} />
            <span>
              We request the <code>repo</code> scope. Your token is encrypted at
              rest, stays server-side, and Repo Vitals only ever reads — it never
              writes to your code.
            </span>
          </p>

          <div
            style={{
              display: "grid",
              gap: 11,
              marginTop: 24,
              borderTop: "1px solid var(--color-divider)",
              paddingTop: 20,
            }}
          >
            <Claim
              icon={
                <ChartIcon
                  size={15}
                  style={{ flex: "none", marginTop: 2, color: "var(--color-accent)" }}
                />
              }
            >
              Deterministic 0–100 score — auditable, no LLM in the number.
            </Claim>
            <Claim
              icon={
                <BookIcon
                  size={15}
                  style={{ flex: "none", marginTop: 2, color: "var(--color-accent)" }}
                />
              }
            >
              Grounded remediation — every claim shown beside its source.
            </Claim>
            <Claim
              icon={
                <PackageIcon
                  size={15}
                  style={{ flex: "none", marginTop: 2, color: "var(--color-accent)" }}
                />
              }
            >
              npm + PyPI — one adapter interface, more ecosystems later.
            </Claim>
          </div>
        </div>

        {/* ── Right: a worked specimen of what the product produces ─────── */}
        <div
          style={{
            background: "color-mix(in srgb, var(--color-accent) 7%, transparent)",
            borderLeft: "1px solid var(--color-divider)",
            padding: "34px 30px",
            display: "flex",
            flexDirection: "column",
            gap: 14,
          }}
        >
          <div
            style={{
              fontSize: 10,
              letterSpacing: ".15em",
              textTransform: "uppercase",
              color: "var(--color-accent)",
            }}
          >
            Specimen · drill-down
          </div>

          <div
            className="blueprint"
            style={{
              border: "1px solid var(--color-divider)",
              background: "color-mix(in srgb, var(--color-bg) 60%, transparent)",
              padding: 15,
            }}
          >
            <BlueprintCorners />
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 10,
              }}
            >
              <div>
                <div
                  style={{
                    fontFamily: "var(--font-heading)",
                    fontWeight: 600,
                    fontSize: 16,
                  }}
                >
                  checkout-service
                </div>
                <div
                  className="text-muted"
                  style={{ fontSize: 11, whiteSpace: "nowrap" }}
                >
                  acme/checkout-service
                </div>
                <span
                  className="tag"
                  style={{
                    background: "#efddda",
                    color: "#6a2a23",
                    marginTop: 8,
                    whiteSpace: "nowrap",
                  }}
                >
                  High-Alert
                </span>
              </div>
              <div style={{ position: "relative", width: 56, height: 56, flex: "none" }}>
                <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden="true">
                  <circle
                    cx="28"
                    cy="28"
                    r="21"
                    fill="none"
                    stroke="var(--color-divider)"
                    strokeWidth="4.5"
                  />
                  <circle
                    cx="28"
                    cy="28"
                    r="21"
                    fill="none"
                    stroke="#a8524a"
                    strokeWidth="4.5"
                    strokeLinecap="round"
                    strokeDasharray="54.1 131.9"
                    transform="rotate(-90 28 28)"
                  />
                </svg>
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "grid",
                    placeItems: "center",
                    fontFamily: "var(--font-heading)",
                    fontWeight: 600,
                    fontSize: 18,
                  }}
                >
                  41
                </div>
              </div>
            </div>

            <div
              style={{
                marginTop: 12,
                borderTop: "1px solid var(--color-divider)",
                paddingTop: 10,
                display: "grid",
                gap: 8,
              }}
            >
              <SpecimenRow
                label="request@2.88.2"
                tag="Deprecated"
                bg="#efddda"
                fg="#6a2a23"
              />
              {/* The specimen mirrors the real findings chip, which counts
                  advisories rather than CVEs (`docs/decisions.md` §7.13). A
                  landing page that used the old word would teach a vocabulary
                  the product no longer speaks. */}
              <SpecimenRow
                label="lodash@4.17.15"
                tag="2 advisories"
                bg="#efddda"
                fg="#6a2a23"
              />
              <SpecimenRow
                label="express@4.17.1"
                tag="Outdated"
                bg="#efe8d5"
                fg="#6a4b16"
              />
            </div>
          </div>

          <div
            className="text-muted"
            style={{ fontSize: 11.5, lineHeight: 1.5, marginTop: 2 }}
          >
            Each flagged package opens a grounded remediation plan with the
            retrieved source shown alongside.
          </div>
        </div>
      </div>
    </div>
  );
}
