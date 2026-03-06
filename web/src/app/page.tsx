"use client";

import { useState, useCallback } from "react";
import InputArea from "@/components/InputArea";
import ResponseStream from "@/components/ResponseStream";
import GraphView from "@/components/GraphView";
import { streamChat, crawlGraph } from "@/lib/api";
import type { GraphData, ChatEvent } from "@/lib/api";
import styles from "./page.module.css";

type ViewState = "idle" | "streaming" | "graph-loading" | "graph";

export default function Home() {
  const [viewState, setViewState] = useState<ViewState>("idle");

  // Chat state
  const [responseText, setResponseText] = useState("");
  const [statusText, setStatusText] = useState("");
  const [paperData, setPaperData] = useState<{
    title: string;
    authors: string[];
    year: number;
    url: string;
    abstract?: string;
  } | null>(null);
  const [papersData, setPapersData] = useState<
    {
      title: string;
      authors: string[];
      year: number;
      url: string;
      abstract?: string;
      source?: string;
    }[]
  >([]);
  const [errorText, setErrorText] = useState<string | null>(null);

  // Graph state
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);

  // Conversation history
  const [conversation, setConversation] = useState<
    { role: string; content: string }[]
  >([]);

  const resetState = useCallback(() => {
    setResponseText("");
    setStatusText("");
    setPaperData(null);
    setPapersData([]);
    setErrorText(null);
    setGraphData(null);
    setGraphError(null);
  }, []);

  const handleSubmit = useCallback(
    async (message: string, mode: string) => {
      resetState();

      // Add user message to conversation
      setConversation((prev) => [...prev, { role: "user", content: message }]);

      if (mode === "graph") {
        // --- Graph mode ---
        setViewState("graph-loading");
        setStatusText("Building citation graph...");

        try {
          const data = await crawlGraph(message, 2, 100, "both");
          setGraphData(data);
          setViewState("graph");
          setStatusText("");
        } catch (err: unknown) {
          const errMsg =
            err instanceof Error ? err.message : "Graph crawl failed";
          setGraphError(errMsg);
          setErrorText(errMsg);
          setViewState("idle");
        }
      } else {
        // --- Chat / Research mode ---
        setViewState("streaming");

        try {
          let fullText = "";
          await streamChat(message, mode, conversation, (event: ChatEvent) => {
            const data = event.data;
            switch (event.event) {
              case "status":
                setStatusText((data.text as string) || "");
                break;
              case "paper":
                setPaperData(data as typeof paperData);
                break;
              case "papers":
                setPapersData(
                  ((data.items as typeof papersData) || []).slice(0, 8),
                );
                break;
              case "chunk":
                fullText += (data.content as string) || "";
                setResponseText(fullText);
                break;
              case "text":
                fullText = (data.content as string) || "";
                setResponseText(fullText);
                break;
              case "error":
                setErrorText((data.message as string) || "Unknown error");
                break;
              case "done":
                setStatusText("");
                break;
            }
          });

          // Save assistant response to conversation
          if (fullText) {
            setConversation((prev) => [
              ...prev,
              { role: "assistant", content: fullText },
            ]);
          }
        } catch (err: unknown) {
          setErrorText(
            err instanceof Error ? err.message : "Connection failed",
          );
        } finally {
          setViewState((prev) => (prev === "streaming" ? "idle" : prev));
        }
      }
    },
    [conversation, resetState],
  );

  const showInput = viewState !== "graph" || graphError;

  return (
    <main className={styles.main}>
      {/* Ambient background gradient */}
      <div className={styles.ambientGlow} />

      {/* Header area */}
      <header className={styles.header}>
        <h1 className={styles.wordmark}>CASCADE</h1>
        <p className={styles.subtitle}>Research Intelligence</p>
      </header>

      {/* Central input */}
      {showInput && (
        <InputArea
          onSubmit={handleSubmit}
          disabled={viewState === "streaming" || viewState === "graph-loading"}
        />
      )}

      {/* Loading state for graph */}
      {viewState === "graph-loading" && (
        <div className={styles.graphLoading}>
          <div className={styles.loadingSpinner} />
          <span className={styles.loadingText}>
            Crawling citation network...
          </span>
          <span className={styles.loadingHint}>
            This may take a moment depending on the paper
          </span>
        </div>
      )}

      {/* Graph view */}
      {viewState === "graph" && graphData && (
        <div className={styles.graphSection}>
          <div className={styles.graphHeader}>
            <button
              className={styles.backButton}
              onClick={() => {
                setViewState("idle");
                resetState();
              }}
            >
              ← Back
            </button>
            <span className={styles.graphTitle}>Citation Network</span>
          </div>
          <GraphView data={graphData} />
        </div>
      )}

      {/* Response stream */}
      {(responseText || statusText || paperData || errorText) &&
        viewState !== "graph" && (
          <ResponseStream
            text={responseText}
            isStreaming={viewState === "streaming"}
            status={statusText}
            paper={paperData}
            papers={papersData}
            error={errorText}
          />
        )}

      {/* Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerLine} />
        <span className={styles.footerText}>
          cascade v0.3.0 — research intelligence
        </span>
      </footer>
    </main>
  );
}
