"use client";

import { useRef, useEffect, useState, useCallback, useMemo } from "react";
import type { GraphData, GraphNode } from "@/lib/api";
import styles from "./GraphView.module.css";

interface GraphViewProps {
    data: GraphData;
    onNodeClick?: (node: GraphNode) => void;
}

interface SimNode extends GraphNode {
    x: number;
    y: number;
    vx: number;
    vy: number;
    fx?: number | null;
    fy?: number | null;
}

interface SimEdge {
    source: SimNode;
    target: SimNode;
}

const DEPTH_COLORS = [
    "#c9a55a", // 0 — seed (amber)
    "#e8e4dc", // 1 — direct
    "#9a9590", // 2
    "#5a5550", // 3+
];

/**
 * Canvas-rendered force-directed citation graph.
 * Uses a simple force simulation instead of D3 to avoid the dependency.
 */
export default function GraphView({ data, onNodeClick }: GraphViewProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
    const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
    const maxDepthOverall = data.nodes.length
        ? Math.max(...data.nodes.map((n) => n.depth))
        : 0;
    const [depthLimit, setDepthLimit] = useState(maxDepthOverall);
    const [textFilter, setTextFilter] = useState("");

    // Mutable refs for simulation state
    const nodesRef = useRef<SimNode[]>([]);
    const edgesRef = useRef<SimEdge[]>([]);
    const transformRef = useRef({ x: 0, y: 0, k: 1 });
    const dragRef = useRef<{ node: SimNode | null; startX: number; startY: number }>({
        node: null,
        startX: 0,
        startY: 0,
    });
    const animRef = useRef<number>(0);

    useEffect(() => {
        setDepthLimit(maxDepthOverall);
        setTextFilter("");
        setSelectedNode(null);
    }, [maxDepthOverall, data.graphId]);

    const filtered = useMemo(() => {
        const q = textFilter.trim().toLowerCase();
        const nodes = data.nodes.filter((n) => {
            if (n.depth > depthLimit) return false;
            if (!q) return true;
            const haystack = `${n.title} ${n.authors.join(" ")}`.toLowerCase();
            return haystack.includes(q);
        });
        const ids = new Set(nodes.map((n) => n.id));
        const edges = data.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
        return { nodes, edges };
    }, [data.nodes, data.edges, depthLimit, textFilter]);

    // Initialize simulation nodes from filtered data
    useEffect(() => {
        const cx = dimensions.width / 2;
        const cy = dimensions.height / 2;

        const nodeMap = new Map<string, SimNode>();
        nodesRef.current = filtered.nodes.map((n, i) => {
            const angle = (2 * Math.PI * i) / Math.max(filtered.nodes.length, 1);
            const radius = n.depth === 0 ? 0 : 100 + n.depth * 80 + Math.random() * 60;
            const sn: SimNode = {
                ...n,
                x: cx + radius * Math.cos(angle),
                y: cy + radius * Math.sin(angle),
                vx: 0,
                vy: 0,
            };
            nodeMap.set(n.id, sn);
            return sn;
        });

        edgesRef.current = filtered.edges
            .map((e) => ({
                source: nodeMap.get(e.source),
                target: nodeMap.get(e.target),
            }))
            .filter((e): e is SimEdge => Boolean(e.source && e.target));

        // Center the seed node
        const seed = nodesRef.current.find((n) => n.depth === 0);
        if (seed) {
            seed.x = cx;
            seed.y = cy;
        }

        // Reset transform
        transformRef.current = { x: 0, y: 0, k: 1 };
    }, [filtered, dimensions]);

    // Resize observer
    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const obs = new ResizeObserver((entries) => {
            const { width, height } = entries[0].contentRect;
            setDimensions({ width, height });
        });
        obs.observe(el);
        return () => obs.disconnect();
    }, []);

    // Force simulation + rendering loop
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        let running = true;
        let tickCount = 0;

        const tick = () => {
            if (!running) return;
            const nodes = nodesRef.current;
            const edges = edgesRef.current;
            const alpha = Math.max(0.001, 0.1 * Math.pow(0.99, tickCount));
            tickCount++;

            // --- Forces ---
            const cx = dimensions.width / 2;
            const cy = dimensions.height / 2;

            // Repulsion (charge)
            for (let i = 0; i < nodes.length; i++) {
                for (let j = i + 1; j < nodes.length; j++) {
                    const a = nodes[i],
                        b = nodes[j];
                    const dx = b.x - a.x;
                    const dy = b.y - a.y;
                    let d2 = dx * dx + dy * dy;
                    if (d2 < 1) d2 = 1;
                    const d = Math.sqrt(d2);
                    const force = (-800 * alpha) / d2;
                    const fx = (dx / d) * force;
                    const fy = (dy / d) * force;
                    a.vx -= fx;
                    a.vy -= fy;
                    b.vx += fx;
                    b.vy += fy;
                }
            }

            // Spring (links)
            const desiredLength = 120;
            for (const e of edges) {
                const dx = e.target.x - e.source.x;
                const dy = e.target.y - e.source.y;
                const d = Math.sqrt(dx * dx + dy * dy) || 1;
                const force = ((d - desiredLength) / d) * 0.05 * alpha;
                const fx = dx * force;
                const fy = dy * force;
                e.source.vx += fx;
                e.source.vy += fy;
                e.target.vx -= fx;
                e.target.vy -= fy;
            }

            // Center gravity
            for (const n of nodes) {
                n.vx += (cx - n.x) * 0.001 * alpha;
                n.vy += (cy - n.y) * 0.001 * alpha;
            }

            // Integrate
            for (const n of nodes) {
                if (n.fx != null) {
                    n.x = n.fx;
                    n.vx = 0;
                } else {
                    n.vx *= 0.6;
                    n.x += n.vx;
                }
                if (n.fy != null) {
                    n.y = n.fy;
                    n.vy = 0;
                } else {
                    n.vy *= 0.6;
                    n.y += n.vy;
                }
            }

            // --- Render ---
            const t = transformRef.current;
            const dpr = window.devicePixelRatio || 1;
            canvas.width = dimensions.width * dpr;
            canvas.height = dimensions.height * dpr;
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, dimensions.width, dimensions.height);

            ctx.save();
            ctx.translate(t.x, t.y);
            ctx.scale(t.k, t.k);

            // Edges
            ctx.lineWidth = 0.5;
            ctx.strokeStyle = "rgba(232, 228, 220, 0.06)";
            for (const e of edges) {
                ctx.beginPath();
                ctx.moveTo(e.source.x, e.source.y);
                ctx.lineTo(e.target.x, e.target.y);
                ctx.stroke();
            }

            // Nodes
            for (const n of nodes) {
                const isHovered = hoveredNode?.id === n.id;
                const isSelected = selectedNode?.id === n.id;
                const radius = n.depth === 0
                    ? 10
                    : Math.max(3, Math.min(8, Math.log2((n.citationCount || 1) + 1) * 1.5));

                const color = DEPTH_COLORS[Math.min(n.depth, DEPTH_COLORS.length - 1)];

                // Glow for seed / hovered
                if (n.depth === 0 || isHovered || isSelected) {
                    ctx.beginPath();
                    ctx.arc(n.x, n.y, radius + 6, 0, 2 * Math.PI);
                    ctx.fillStyle =
                        n.depth === 0
                            ? "rgba(201, 165, 90, 0.15)"
                            : "rgba(232, 228, 220, 0.08)";
                    ctx.fill();
                }

                // Node circle
                ctx.beginPath();
                ctx.arc(n.x, n.y, radius, 0, 2 * Math.PI);
                ctx.fillStyle = isHovered || isSelected ? "#fff" : color;
                ctx.fill();

                // Label for seed + hovered
                if (n.depth === 0 || isHovered || isSelected) {
                    ctx.font = "11px 'JetBrains Mono', monospace";
                    ctx.fillStyle = "rgba(232, 228, 220, 0.8)";
                    ctx.textAlign = "center";
                    const label =
                        n.title.length > 40 ? n.title.slice(0, 37) + "..." : n.title;
                    ctx.fillText(label, n.x, n.y - radius - 8);
                }
            }

            ctx.restore();

            animRef.current = requestAnimationFrame(tick);
        };

        animRef.current = requestAnimationFrame(tick);
        return () => {
            running = false;
            cancelAnimationFrame(animRef.current);
        };
    }, [filtered, dimensions, hoveredNode, selectedNode]);

    useEffect(() => {
        if (selectedNode && !filtered.nodes.some((n) => n.id === selectedNode.id)) {
            setSelectedNode(null);
        }
    }, [filtered.nodes, selectedNode]);

    // Mouse interaction
    const screenToGraph = useCallback(
        (clientX: number, clientY: number) => {
            const canvas = canvasRef.current;
            if (!canvas) return { x: 0, y: 0 };
            const rect = canvas.getBoundingClientRect();
            const t = transformRef.current;
            return {
                x: (clientX - rect.left - t.x) / t.k,
                y: (clientY - rect.top - t.y) / t.k,
            };
        },
        [],
    );

    const findNodeAt = useCallback(
        (gx: number, gy: number): SimNode | null => {
            for (const n of nodesRef.current) {
                const dx = n.x - gx;
                const dy = n.y - gy;
                const r = n.depth === 0 ? 14 : 10;
                if (dx * dx + dy * dy < r * r) return n;
            }
            return null;
        },
        [],
    );

    const handleMouseMove = useCallback(
        (e: React.MouseEvent) => {
            const g = screenToGraph(e.clientX, e.clientY);

            // Dragging
            const dr = dragRef.current;
            if (dr.node) {
                dr.node.fx = g.x;
                dr.node.fy = g.y;
                return;
            }

            // Hover
            const n = findNodeAt(g.x, g.y);
            setHoveredNode(n);
            if (canvasRef.current) {
                canvasRef.current.style.cursor = n ? "pointer" : "grab";
            }
        },
        [screenToGraph, findNodeAt],
    );

    const handleMouseDown = useCallback(
        (e: React.MouseEvent) => {
            const g = screenToGraph(e.clientX, e.clientY);
            const n = findNodeAt(g.x, g.y);
            if (n) {
                dragRef.current = { node: n, startX: g.x, startY: g.y };
                n.fx = n.x;
                n.fy = n.y;
            } else {
                dragRef.current = { node: null, startX: e.clientX, startY: e.clientY };
            }
        },
        [screenToGraph, findNodeAt],
    );

    const handleMouseUp = useCallback(
        (e: React.MouseEvent) => {
            const dr = dragRef.current;
            if (dr.node) {
                const g = screenToGraph(e.clientX, e.clientY);
                const moved =
                    Math.abs(g.x - dr.startX) + Math.abs(g.y - dr.startY) > 5;
                if (!moved) {
                    setSelectedNode(dr.node);
                    onNodeClick?.(dr.node);
                }
                dr.node.fx = null;
                dr.node.fy = null;
            } else {
                // Pan
                const dx = e.clientX - dr.startX;
                const dy = e.clientY - dr.startY;
                if (Math.abs(dx) + Math.abs(dy) > 3) {
                    transformRef.current.x += dx;
                    transformRef.current.y += dy;
                }
            }
            dragRef.current = { node: null, startX: 0, startY: 0 };
        },
        [screenToGraph, onNodeClick],
    );

    const handleWheel = useCallback((e: React.WheelEvent) => {
        e.preventDefault();
        const t = transformRef.current;
        const factor = e.deltaY > 0 ? 0.92 : 1.08;
        const newK = Math.max(0.1, Math.min(5, t.k * factor));
        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        t.x = mx - ((mx - t.x) / t.k) * newK;
        t.y = my - ((my - t.y) / t.k) * newK;
        t.k = newK;
    }, []);

    const handleResetView = useCallback(() => {
        transformRef.current = { x: 0, y: 0, k: 1 };
        setSelectedNode(null);
    }, []);

    const handleExport = useCallback(() => {
        const payload = {
            graphId: data.graphId || null,
            stats: data.stats,
            nodes: filtered.nodes,
            edges: filtered.edges,
            exportedAt: new Date().toISOString(),
        };
        const blob = new Blob([JSON.stringify(payload, null, 2)], {
            type: "application/json",
        });
        const href = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = href;
        a.download = `${data.graphId || "citation-graph"}.json`;
        a.click();
        URL.revokeObjectURL(href);
    }, [data.graphId, data.stats, filtered.nodes, filtered.edges]);

    return (
        <div className={styles.container} ref={containerRef}>
            <div className={styles.controlsBar}>
                <label className={styles.controlGroup}>
                    <span>Depth</span>
                    <input
                        type="range"
                        min={0}
                        max={maxDepthOverall}
                        step={1}
                        value={depthLimit}
                        onChange={(e) => setDepthLimit(Number(e.target.value))}
                    />
                    <span>{depthLimit}</span>
                </label>
                <label className={styles.controlGroup}>
                    <span>Filter</span>
                    <input
                        type="text"
                        value={textFilter}
                        onChange={(e) => setTextFilter(e.target.value)}
                        placeholder="title or author"
                    />
                </label>
                <button className={styles.controlBtn} onClick={handleResetView}>
                    Reset view
                </button>
                <button className={styles.controlBtn} onClick={handleExport}>
                    Export JSON
                </button>
            </div>

            {/* Stats bar */}
            <div className={styles.statsBar}>
                <span className={styles.stat}>
                    {filtered.nodes.length}/{data.nodes.length} papers
                </span>
                <span className={styles.statDivider}>·</span>
                <span className={styles.stat}>
                    {filtered.edges.length}/{data.edges.length} citations
                </span>
                <span className={styles.statDivider}>·</span>
                <span className={styles.stat}>
                    depth {filtered.nodes.length ? Math.max(...filtered.nodes.map((n) => n.depth)) : 0}
                </span>
            </div>

            {/* Canvas */}
            <canvas
                ref={canvasRef}
                className={styles.canvas}
                style={{ width: dimensions.width, height: dimensions.height }}
                onMouseMove={handleMouseMove}
                onMouseDown={handleMouseDown}
                onMouseUp={handleMouseUp}
                onWheel={handleWheel}
            />

            {/* Selected node detail panel */}
            {selectedNode && (
                <div className={styles.detailPanel}>
                    <button
                        className={styles.closeButton}
                        onClick={() => setSelectedNode(null)}
                    >
                        ✕
                    </button>
                    <div className={styles.detailMeta}>
                        <span className={styles.detailYear}>{selectedNode.year}</span>
                        <span className={styles.detailDivider}>·</span>
                        <span>
                            {selectedNode.citationCount?.toLocaleString() || "?"} citations
                        </span>
                    </div>
                    <h3 className={styles.detailTitle}>{selectedNode.title}</h3>
                    <p className={styles.detailAuthors}>
                        {selectedNode.authors.join(", ")}
                    </p>
                    {selectedNode.abstract && (
                        <p className={styles.detailAbstract}>{selectedNode.abstract}</p>
                    )}
                    {selectedNode.url && (
                        <a
                            className={styles.detailLink}
                            href={selectedNode.url}
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            Open paper →
                        </a>
                    )}
                </div>
            )}

            {/* Legend */}
            <div className={styles.legend}>
                {DEPTH_COLORS.map((color, i) => (
                    <div key={i} className={styles.legendItem}>
                        <span
                            className={styles.legendDot}
                            style={{ background: color }}
                        />
                        <span>
                            {i === 0
                                ? "Seed"
                                : i === 1
                                    ? "Direct"
                                    : `Depth ${i}`}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}
