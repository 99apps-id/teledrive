import { useQuery } from "@tanstack/react-query";
import { getDevStackStatus } from "./api";

function statusLabel(ok: boolean | undefined) {
  if (ok === undefined) return "…";
  return ok ? "OK" : "Down";
}

export function DevHealthBadge() {
  const isDev = import.meta.env.DEV;
  const statusQuery = useQuery({
    queryKey: ["dev-stack-status"],
    queryFn: getDevStackStatus,
    enabled: isDev,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });

  if (!isDev) {
    return null;
  }

  const status = statusQuery.data;

  return (
    <footer className="dev-health-badge" aria-label="Development stack status" role="status">
      <span className="dev-health-badge__label">Dev stack</span>
      <span className={status?.api ? "dev-health-badge__ok" : "dev-health-badge__bad"}>
        API {statusLabel(status?.api)}
      </span>
      <span className={status?.redis ? "dev-health-badge__ok" : "dev-health-badge__bad"}>
        Redis {statusLabel(status?.redis)}
      </span>
      <span className={status?.worker ? "dev-health-badge__ok" : "dev-health-badge__bad"}>
        Worker {statusLabel(status?.worker)}
      </span>
    </footer>
  );
}
