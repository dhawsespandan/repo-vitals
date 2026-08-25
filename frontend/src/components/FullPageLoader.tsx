/**
 * Shown while the session is being resolved. It deliberately says nothing
 * about being signed in or out — that is the whole question it is waiting on.
 */
export function FullPageLoader({ label }: { label: string }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        gap: "14px",
      }}
      role="status"
      aria-live="polite"
    >
      <div style={{ display: "grid", justifyItems: "center", gap: "14px" }}>
        <div
          style={{
            width: 32,
            height: 32,
            border: "3px solid var(--color-divider)",
            borderTopColor: "var(--color-accent)",
            borderRadius: "50%",
            animation: "dsspin .9s linear infinite",
          }}
        />
        <span
          className="text-muted"
          style={{
            fontSize: 11,
            letterSpacing: ".15em",
            textTransform: "uppercase",
          }}
        >
          {label}
        </span>
      </div>
    </div>
  );
}
