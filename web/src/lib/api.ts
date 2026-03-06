const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/* ------------------------------------------------------------------ */
/* Chat — SSE streaming                                                */
/* ------------------------------------------------------------------ */
export interface ChatEvent {
    event: string;
    data: Record<string, unknown>;
}

export async function streamChat(
    message: string,
    mode: string,
    conversation: { role: string; content: string }[],
    onEvent: (e: ChatEvent) => void,
): Promise<void> {
    const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, mode, conversation }),
    });

    if (!res.ok) throw new Error(`Chat failed: ${res.status}`);

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
            const lines = part.split("\n");
            let event = "message";
            let data = "";

            for (const line of lines) {
                if (line.startsWith("event: ")) event = line.slice(7);
                else if (line.startsWith("data: ")) data = line.slice(6);
            }

            if (data) {
                try {
                    onEvent({ event, data: JSON.parse(data) });
                } catch {
                    // skip malformed
                }
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* Graph                                                                */
/* ------------------------------------------------------------------ */
export interface GraphData {
    graphId?: string | null;
    nodes: GraphNode[];
    edges: { source: string; target: string }[];
    stats: Record<string, number>;
}

export interface GraphNode {
    id: string;
    title: string;
    authors: string[];
    year: number;
    citationCount: number;
    abstract: string;
    url: string;
    depth: number;
    label: string;
}

export async function crawlGraph(
    paper: string,
    depth = 2,
    maxPapers = 100,
    direction = "both",
): Promise<GraphData> {
    const res = await fetch(`${API_BASE}/api/graph/crawl`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            paper,
            depth,
            max_papers: maxPapers,
            direction,
        }),
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Graph crawl failed");
    }

    return res.json();
}

/* ------------------------------------------------------------------ */
/* Search                                                               */
/* ------------------------------------------------------------------ */
export interface PaperResult {
    title: string;
    authors: string[];
    abstract: string;
    url: string;
    year: number;
    source: string;
    categories: string[];
    citationCount: number | null;
    arxivId: string | null;
    doi: string | null;
    pdfUrl: string | null;
}

export async function searchPapers(
    query: string,
    sources = "arxiv,scholar",
    limit = 10,
): Promise<{ papers: PaperResult[]; total: number }> {
    const params = new URLSearchParams({ q: query, sources, limit: String(limit) });
    const res = await fetch(`${API_BASE}/api/search?${params}`);
    if (!res.ok) throw new Error("Search failed");
    return res.json();
}

/* ------------------------------------------------------------------ */
/* Health                                                               */
/* ------------------------------------------------------------------ */
export async function checkHealth(): Promise<boolean> {
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        return res.ok;
    } catch {
        return false;
    }
}
