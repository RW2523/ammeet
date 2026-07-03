"use client";

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { workspaceApi } from "@/lib/api-client";
import { useWorkspaceStore } from "@/lib/store";

/**
 * Hydrates the current workspace for every /workspaces/[id]/* page. Without this, a
 * direct load or reload of a sub-page (e.g. /meetings, /test-join) left the store's
 * current workspace null and the per-workspace sidebar nav disappeared.
 */
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const setCurrent = useWorkspaceStore((s) => s.setCurrent);

  const { data: workspace } = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => workspaceApi.get(workspaceId),
    enabled: !!workspaceId,
  });

  useEffect(() => {
    if (workspace) setCurrent(workspace);
  }, [workspace, setCurrent]);

  return <>{children}</>;
}
