import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Agentiva",
    short_name: "Agentiva",
    description: "AI agent safety dashboard",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#0d1117",
    theme_color: "#0d1117",
    icons: [],
  };
}
