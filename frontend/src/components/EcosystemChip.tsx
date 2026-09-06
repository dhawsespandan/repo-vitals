import type { DependencyOccurrence, ManifestFile } from "../types";

/**
 * Which package ecosystem a row, or a whole repository, belongs to.
 *
 * Phase 6's only visible surface, and it earns its place twice over.
 *
 * On a repository, the chip is the answer to "did this even scan?" for a
 * Python project — every other number on the page looks identical whichever
 * ecosystem produced it, which is precisely the phase's claim, and precisely
 * what makes the claim unverifiable without one label saying so.
 *
 * On a *row*, it is load-bearing rather than decorative. A mixed repository
 * pools npm and PyPI occurrences into one table (§5.1), and the two registries
 * publish different packages under the same names: `requests` and `flask` and
 * `six` all exist on npm as well as PyPI. Two rows reading `requests 2.31.0`
 * and `requests 2.88.1` are not the same dependency at two versions, and
 * without the chip nothing on screen says so.
 *
 * The two ecosystems get *the same* chip treatment — same shape, same weight,
 * different word. Styling one as the primary and the other as an annexe would
 * quietly contradict the design claim the phase exists to make.
 */

const ECOSYSTEM_LABEL: Record<string, string> = {
  npm: "npm",
  pypi: "PyPI",
};

/** The word for one ecosystem, or the code itself if a third ever arrives. */
export function ecosystemLabel(ecosystem: string): string {
  return ECOSYSTEM_LABEL[ecosystem] ?? ecosystem;
}

/**
 * What to call a set of ecosystems: one of them, or "Mixed".
 *
 * Returns null for an empty set rather than an empty chip — a scan that read
 * no manifests has nothing to label, and a blank chip reads as a missing
 * value rather than an absent question.
 */
export function summarizeEcosystems(
  sources: Pick<ManifestFile | DependencyOccurrence, "ecosystem">[],
): string | null {
  const [only, ...rest] = presentEcosystems(sources);
  if (only === undefined) return null;
  return rest.length === 0 ? ecosystemLabel(only) : "Mixed";
}

/** The distinct ecosystems in a set of rows, in a stable order. */
function presentEcosystems(
  sources: Pick<ManifestFile | DependencyOccurrence, "ecosystem">[],
): string[] {
  return [...new Set(sources.map((source) => String(source.ecosystem)))].sort();
}

interface EcosystemChipProps {
  ecosystem: string;
  /** Overrides the label — used for the "Mixed" repository-level chip. */
  label?: string;
  title?: string;
}

export function EcosystemChip({ ecosystem, label, title }: EcosystemChipProps) {
  return (
    <span
      className="tag tag-neutral"
      data-testid="ecosystem-chip"
      data-ecosystem={ecosystem}
      title={title}
      style={{ whiteSpace: "nowrap", fontVariant: "none" }}
    >
      {label ?? ecosystemLabel(ecosystem)}
    </span>
  );
}

/**
 * The repository-level chip, computed from the manifests the scan read.
 *
 * From the manifests rather than from the dependency rows the browser happens
 * to hold: the manifest list is complete in one response, while the rows are
 * paged, and a repository whose only Python manifest sat on page three would
 * otherwise be labelled npm.
 */
export function ScanEcosystemChip({ manifests }: { manifests: ManifestFile[] }) {
  const [only, ...rest] = presentEcosystems(manifests);
  if (only === undefined) return null;

  if (rest.length === 0) {
    return <EcosystemChip ecosystem={only} />;
  }
  return (
    <EcosystemChip
      ecosystem="mixed"
      label="Mixed"
      title={`${[only, ...rest].map(ecosystemLabel).join(" and ")} manifests in one scan`}
    />
  );
}
