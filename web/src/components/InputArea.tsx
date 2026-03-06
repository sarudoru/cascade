"use client";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import styles from "./InputArea.module.css";

interface InputAreaProps {
    onSubmit: (message: string, mode: string) => void;
    disabled?: boolean;
}

const URL_REGEX =
    /https?:\/\/(?:arxiv\.org|semanticscholar\.org|doi\.org|openreview\.net|aclanthology\.org|papers\.nips\.cc|proceedings\.mlr\.press|.*\.pdf\b)\S*/i;

type Mode = "auto" | "graph" | "research" | "review" | "gaps";

const MODE_INFO: Record<Mode, { label: string; icon: string; desc: string }> = {
    auto: { label: "Auto", icon: "◈", desc: "Cascade decides" },
    graph: { label: "Citation Graph", icon: "⬡", desc: "Map the research landscape" },
    research: { label: "Deep Research", icon: "◉", desc: "Thorough investigation" },
    review: { label: "Literature Review", icon: "▤", desc: "Synthesise the field" },
    gaps: { label: "Find Gaps", icon: "△", desc: "Identify open problems" },
};

export default function InputArea({ onSubmit, disabled }: InputAreaProps) {
    const [value, setValue] = useState("");
    const [mode, setMode] = useState<Mode>("auto");
    const [isFocused, setIsFocused] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const hasUrl = useMemo(() => URL_REGEX.test(value), [value]);

    // Auto-resize textarea
    useEffect(() => {
        const ta = textareaRef.current;
        if (!ta) return;
        ta.style.height = "auto";
        ta.style.height = `${Math.min(ta.scrollHeight, 240)}px`;
    }, [value]);

    // Auto-focus on mount (avoids Next.js autoFocus hydration warning)
    useEffect(() => {
        if (!disabled && textareaRef.current) {
            textareaRef.current.focus();
        }
    }, [disabled]);

    const handleSubmit = useCallback(() => {
        const trimmed = value.trim();
        if (!trimmed || disabled) return;

        const effectiveMode = mode === "auto" && hasUrl ? "graph" : mode;
        onSubmit(trimmed, effectiveMode);
        setValue("");
        setMode("auto");
    }, [value, mode, hasUrl, disabled, onSubmit]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div className={`${styles.container} ${isFocused ? styles.focused : ""}`}>
            {/* Input area */}
            <div className={styles.inputWrapper}>
                <textarea
                    ref={textareaRef}
                    className={styles.textarea}
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    onFocus={() => setIsFocused(true)}
                    onBlur={() => setIsFocused(false)}
                    placeholder="paste a paper link, or ask anything about your research..."
                    disabled={disabled}
                    rows={1}
                />

                {/* Submit button */}
                <button
                    className={styles.submitButton}
                    onClick={handleSubmit}
                    disabled={!value.trim() || disabled}
                    title="Send (⌘ + Enter)"
                >
                    <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    >
                        <line x1="5" y1="12" x2="19" y2="12" />
                        <polyline points="12 5 19 12 12 19" />
                    </svg>
                </button>
            </div>

            {/* URL detection indicator */}
            {hasUrl && (
                <div className={styles.urlDetected}>
                    <span className={styles.urlDot} />
                    <span className={styles.urlText}>Paper URL detected</span>
                </div>
            )}

            {/* Mode pills */}
            <div className={styles.modes}>
                {(Object.entries(MODE_INFO) as [Mode, typeof MODE_INFO.auto][]).map(
                    ([key, { label, icon }]) => (
                        <button
                            key={key}
                            className={`${styles.modePill} ${mode === key ? styles.active : ""}`}
                            onClick={() => setMode(key)}
                            title={MODE_INFO[key].desc}
                        >
                            <span className={styles.modeIcon}>{icon}</span>
                            <span>{label}</span>
                        </button>
                    ),
                )}
            </div>

            {/* Hint */}
            <div className={styles.hint}>
                <span className={styles.hintKey}>⌘ Enter</span> to send
            </div>
        </div>
    );
}
