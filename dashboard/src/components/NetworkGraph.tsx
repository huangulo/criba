"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import {
  fetchNetworkGraph,
  NetworkGraphData,
  NetworkNode,
} from "@/lib/api";

const PLATFORM_COLORS: Record<string, string> = {
  twitter: "#1da1f2",
  x: "#1da1f2",
  telegram: "#0088cc",
  reddit: "#ff4500",
  facebook: "#1877f2",
  instagram: "#e1306c",
  tiktok: "#ff0050",
  truth_social: "#c19a6b",
  mastodon: "#6364ff",
  bluesky: "#0085ff",
  threads: "#000000",
  rss: "#22c55e",
};

function platformColor(platform: string | null): string {
  if (!platform) return "#71717a";
  return PLATFORM_COLORS[platform.toLowerCase()] || "#71717a";
}

function nodeRadius(node: NetworkNode): number {
  return Math.max(5, Math.min(20, Math.sqrt(node.degree) * 4));
}

function tooltipLine(className: string, text: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  el.textContent = text;
  return el;
}

interface SimNode extends NetworkNode, d3.SimulationNodeDatum {}
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  interaction: string;
  weight: number;
}

interface NetworkGraphProps {
  narrativeId: string | null;
  narrativeLabel?: string | null;
  projectId: string;
}

export default function NetworkGraph({
  narrativeId,
  narrativeLabel,
  projectId,
}: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<NetworkGraphData | null>(null);
  // True until the first response lands: skeleton on mount, then the
  // previous graph stays visible while a new narrative loads.
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const loadRequestId = useRef(0);

  // Deselecting a narrative clears the graph during render (the
  // React-documented pattern for resetting state on prop change) instead
  // of synchronously inside an effect.
  const [renderedNarrativeId, setRenderedNarrativeId] = useState(narrativeId);
  if (narrativeId !== renderedNarrativeId) {
    setRenderedNarrativeId(narrativeId);
    if (!narrativeId) {
      setData(null);
      setError(null);
    }
  }

  const load = useCallback(() => {
    if (!narrativeId) return;
    // Only the most recently issued request may apply its result: switching
    // narratives quickly can resolve responses out of order. No synchronous
    // state updates, so the effect can call this without cascading renders.
    const request = ++loadRequestId.current;
    fetchNetworkGraph(narrativeId, projectId)
      .then((result) => {
        if (loadRequestId.current !== request) return;
        setData(result);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        if (loadRequestId.current !== request) return;
        setError(err.message);
        setLoading(false);
      });
  }, [narrativeId, projectId]);

  useEffect(() => {
    if (!narrativeId) {
      loadRequestId.current++; // invalidate any in-flight load
      return;
    }
    load();
  }, [narrativeId, load]);

  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return;

    const containerWidth = containerRef.current.clientWidth;
    const width = containerWidth;
    const height = 500;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    svg.attr("width", width).attr("height", height);

    const g = svg.append("g");

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 5])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });

    svg.call(zoom);

    const nodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const links: SimLink[] = data.links.map((l) => ({
      source: l.source,
      target: l.target,
      interaction: l.interaction,
      weight: l.weight,
    }));

    const simulation = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(60),
      )
      .force("charge", d3.forceManyBody().strength(-120))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force(
        "collision",
        d3.forceCollide<SimNode>().radius((d) => nodeRadius(d) + 5),
      );

    const defs = svg.append("defs");

    const filter = defs.append("filter").attr("id", "cluster-glow");
    filter
      .append("feGaussianBlur")
      .attr("stdDeviation", "3")
      .attr("result", "coloredBlur");
    const feMerge = filter.append("feMerge");
    feMerge.append("feMergeNode").attr("in", "coloredBlur");
    feMerge.append("feMergeNode").attr("in", "SourceGraphic");

    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#1e1e2e")
      .attr("stroke-width", (d) => Math.max(1, Math.min(6, d.weight)))
      .attr("stroke-opacity", 0.6);

    const nodeGroup = g.append("g");

    const node = nodeGroup
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", (d) => nodeRadius(d))
      .attr("fill", (d) => platformColor(d.platform))
      .attr("stroke", (d) => (d.is_cluster ? "#ef4444" : "none"))
      .attr("stroke-width", (d) => (d.is_cluster ? 2.5 : 0))
      .attr("filter", (d) => (d.is_cluster ? "url(#cluster-glow)" : "none"))
      .style("cursor", "pointer");

    function dragstarted(
      event: d3.D3DragEvent<SVGCircleElement, SimNode, SimNode>,
    ) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }

    function dragged(
      event: d3.D3DragEvent<SVGCircleElement, SimNode, SimNode>,
    ) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }

    function dragended(
      event: d3.D3DragEvent<SVGCircleElement, SimNode, SimNode>,
    ) {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }

    const dragBehavior = d3
      .drag<SVGCircleElement, SimNode>()
      .on("start", dragstarted)
      .on("drag", dragged)
      .on("end", dragended);

    (
      node as d3.Selection<
        SVGCircleElement,
        SimNode,
        SVGGElement,
        unknown
      >
    ).call(dragBehavior);

    const tooltip = tooltipRef.current;

    node
      .on("mouseenter", (event: MouseEvent, d: SimNode) => {
        if (!tooltip) return;
        tooltip.style.display = "block";
        tooltip.style.left = `${event.offsetX + 12}px`;
        tooltip.style.top = `${event.offsetY - 8}px`;
        tooltip.replaceChildren(
          tooltipLine(
            "font-mono text-text-primary font-semibold text-xs",
            d.handle || d.id.slice(0, 8)
          ),
          tooltipLine(
            "text-text-muted font-mono text-[10px] mt-1",
            `${d.platform ? d.platform.toUpperCase() : "Unknown"} · Degree: ${d.degree}`
          ),
          ...(d.is_cluster
            ? [tooltipLine("text-danger font-mono text-[10px] mt-0.5", "Cluster node")]
            : []),
        );
      })
      .on("mousemove", (event: MouseEvent) => {
        if (!tooltip) return;
        tooltip.style.left = `${event.offsetX + 12}px`;
        tooltip.style.top = `${event.offsetY - 8}px`;
      })
      .on("mouseleave", () => {
        if (!tooltip) return;
        tooltip.style.display = "none";
      });

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);

      node.attr("cx", (d) => d.x ?? 0).attr("cy", (d) => d.y ?? 0);
    });

    return () => {
      simulation.stop();
    };
  }, [data]);

  const clusterCount = data?.clusters?.length ?? 0;

  return (
    <div className="rounded border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
            Network Topology
          </h2>
          {narrativeId && (
            <span className="text-xs font-mono text-text-primary opacity-70">
              {narrativeLabel || narrativeId.slice(0, 8)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {data && (
            <span className="text-xs font-mono text-text-muted">
              {data.total_authors} authors &middot;{" "}
              {data.total_interactions} interactions &middot; {clusterCount}{" "}
              clusters
            </span>
          )}
        </div>
      </div>

      {error && (
        <p className="text-danger text-xs font-mono mb-2">{error}</p>
      )}

      {!narrativeId && !loading && !error && (
        <div className="h-[500px] flex items-center justify-center text-text-muted text-sm">
          Select a narrative to view its interaction network
        </div>
      )}

      {loading && (
        <div className="h-[500px] flex items-center justify-center">
          <div className="w-full max-w-md space-y-3 animate-pulse">
            <div className="h-4 bg-surface-border rounded w-3/4" />
            <div className="h-[400px] bg-surface-border rounded-md" />
          </div>
        </div>
      )}

      {narrativeId && !loading && data && data.nodes.length === 0 && (
        <div className="h-[500px] flex items-center justify-center text-text-muted text-sm">
          No interaction data available for this narrative
        </div>
      )}

      {narrativeId && !loading && data && data.nodes.length > 0 && (
        <div ref={containerRef} className="relative rounded-md overflow-hidden">
          <svg
            ref={svgRef}
            className="w-full bg-[#08080d] block"
            style={{ height: 500 }}
          />
          <div
            ref={tooltipRef}
            className="absolute pointer-events-none rounded border border-surface-border bg-surface-card px-3 py-2 shadow-xl z-10"
            style={{ display: "none" }}
          />
        </div>
      )}
    </div>
  );
}
