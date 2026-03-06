"use client";

import { useEffect, useRef } from "react";
import styles from "./ResponseStream.module.css";

interface ResponseStreamProps {
    /** Ongoing accumulated text from the streaming LLM response */
    text: string;
    /** Whether we're currently streaming */
    isStreaming: boolean;
    /** Status text (e.g. "Searching arXiv...") */
    status?: string;
    /** Any paper metadata that was detected */
    paper?: {
        title: string;
        authors: string[];
        year: number;
        url: string;
        abstract?: string;
    } | null;
    papers?: {
        title: string;
        authors: string[];
        year: number;
        url: string;
        abstract?: string;
        source?: string;
    }[];
    /** Error message */
    error?: string | null;
}

export default function ResponseStream({
    text,
    isStreaming,
    status,
    paper,
    papers = [],
    error,
}: ResponseStreamProps) {
    const endRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to bottom while streaming
    useEffect(() => {
        if (isStreaming) {
            endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
        }
    }, [text, isStreaming]);

    if (!text && !status && !paper && !papers.length && !error) return null;

    return (
        <div className={styles.container}>
            {/* Status indicator */}
            {status && isStreaming && (
                <div className={styles.status}>
                    <span className={styles.statusDot} />
                    <span>{status}</span>
                </div>
            )}

            {/* Paper card (if detected) */}
            {paper && (
                <div className={styles.paperCard}>
                    <div className={styles.paperMeta}>
                        <span className={styles.paperYear}>{paper.year}</span>
                        <span className={styles.paperDivider}>·</span>
                        <span className={styles.paperAuthors}>
                            {paper.authors.length <= 3
                                ? paper.authors.join(", ")
                                : `${paper.authors[0]} et al.`}
                        </span>
                    </div>
                    <h3 className={styles.paperTitle}>
                        <a href={paper.url} target="_blank" rel="noopener noreferrer">
                            {paper.title}
                        </a>
                    </h3>
                    {paper.abstract && (
                        <p className={styles.paperAbstract}>{paper.abstract}</p>
                    )}
                </div>
            )}

            {/* Related papers list (for research/review/gap modes) */}
            {papers.length > 0 && (
                <div className={styles.paperList}>
                    <div className={styles.paperListTitle}>Related papers</div>
                    {papers.map((p, idx) => (
                        <a
                            key={`${p.url}-${idx}`}
                            href={p.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={styles.paperListItem}
                        >
                            <div className={styles.paperListItemMeta}>
                                <span>{p.year || "?"}</span>
                                <span>·</span>
                                <span>{p.source || "source"}</span>
                            </div>
                            <div className={styles.paperListItemTitle}>{p.title}</div>
                        </a>
                    ))}
                </div>
            )}

            {/* Error */}
            {error && (
                <div className={styles.error}>
                    <span className={styles.errorIcon}>✕</span>
                    <span>{error}</span>
                </div>
            )}

            {/* Streaming text */}
            {text && (
                <div className={styles.responseText}>
                    <div
                        className={styles.markdown}
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }}
                    />
                    {isStreaming && <span className={styles.cursor} />}
                </div>
            )}

            <div ref={endRef} />
        </div>
    );
}

/**
 * Very simple markdown → HTML renderer.
 * Handles: bold, italic, code, code blocks, headers, links, lists.
 */
function renderMarkdown(md: string): string {
    let html = md;

    // Code blocks
    html = html.replace(
        /```(\w*)\n([\s\S]*?)```/g,
        '<pre><code class="lang-$1">$2</code></pre>',
    );

    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Headers
    html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

    // Bold & italic
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

    // Links
    html = html.replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    );

    // Unordered lists
    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>");

    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

    // Paragraphs (lines separated by double newlines)
    html = html.replace(/\n\n/g, "</p><p>");
    html = `<p>${html}</p>`;

    // Clean up empty paragraphs
    html = html.replace(/<p><\/p>/g, "");
    html = html.replace(/<p>(<h[1-4]>)/g, "$1");
    html = html.replace(/(<\/h[1-4]>)<\/p>/g, "$1");
    html = html.replace(/<p>(<pre>)/g, "$1");
    html = html.replace(/(<\/pre>)<\/p>/g, "$1");
    html = html.replace(/<p>(<ul>)/g, "$1");
    html = html.replace(/(<\/ul>)<\/p>/g, "$1");

    return html;
}
