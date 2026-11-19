export interface DagNode {
  id: string;
  dependencies: readonly string[];
}

export type DagAnalysis =
  | { status: "valid"; order: string[]; ancestry: Map<string, Set<string>> }
  | { status: "invalid"; reason: "duplicate" | "unknown-dependency" | "cycle"; node: string };

export function analyzeDag(nodes: readonly DagNode[]): DagAnalysis {
  const remaining = new Map<string, ReadonlySet<string>>();
  const uniqueIds = new Set<string>();
  for (const { id, dependencies } of nodes) {
    const normalized = id.toLowerCase();
    if (uniqueIds.has(normalized)) return { status: "invalid", reason: "duplicate", node: id };
    uniqueIds.add(normalized);
    remaining.set(id, new Set(dependencies));
  }
  for (const [id, dependencies] of remaining) {
    if ([...dependencies].some((dependency) => !remaining.has(dependency))) {
      return { status: "invalid", reason: "unknown-dependency", node: id };
    }
  }

  const order: string[] = [];
  const ancestry = new Map<string, Set<string>>();
  for (let first = remaining.keys().next(); !first.done; first = remaining.keys().next()) {
    const sizeBefore = remaining.size;
    for (const [id, dependencies] of remaining) {
      if ([...dependencies].some((dependency) => !ancestry.has(dependency))) continue;
      const ancestors = new Set(dependencies);
      for (const dependency of dependencies) {
        for (const ancestor of ancestry.get(dependency) ?? []) ancestors.add(ancestor);
      }
      remaining.delete(id);
      ancestry.set(id, ancestors);
      order.push(id);
    }
    if (remaining.size === sizeBefore) {
      return { status: "invalid", reason: "cycle", node: first.value };
    }
  }
  return { status: "valid", order, ancestry };
}
