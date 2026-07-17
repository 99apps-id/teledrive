import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Compartment, EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { autocompletion, closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
import { bracketMatching, defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { searchKeymap } from "@codemirror/search";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { oneDark } from "@codemirror/theme-one-dark";
import type { SaveTextFilePayload, TextFileContent } from "./api";

type EditorMode = "text" | "code" | "markdown";
type Syntax = "auto" | "plain" | "javascript" | "json" | "html" | "css" | "markdown" | "python" | "sql";

interface TextEditorDialogProps {
  document: TextFileContent | null;
  fileName: string;
  loading?: boolean;
  saving?: boolean;
  error?: string;
  onClose: () => void;
  onSave: (payload: SaveTextFilePayload) => void;
  onReload?: () => void;
}

function inferredSyntax(name: string): Exclude<Syntax, "auto"> {
  const extension = name.split(".").pop()?.toLowerCase();
  if (["js", "jsx", "ts", "tsx", "mjs", "cjs"].includes(extension ?? "")) return "javascript";
  if (extension === "json") return "json";
  if (["html", "htm", "svg"].includes(extension ?? "")) return "html";
  if (extension === "css") return "css";
  if (["md", "mdx", "markdown"].includes(extension ?? "")) return "markdown";
  if (["py", "pyw"].includes(extension ?? "")) return "python";
  if (["sql", "sqlite"].includes(extension ?? "")) return "sql";
  return "plain";
}

function syntaxExtension(syntax: Syntax, fileName: string) {
  switch (syntax === "auto" ? inferredSyntax(fileName) : syntax) {
    case "javascript":
      return javascript({ jsx: /\.(jsx|tsx)$/i.test(fileName), typescript: /\.(ts|tsx)$/i.test(fileName) });
    case "json": return json();
    case "html": return html();
    case "css": return css();
    case "markdown": return markdown();
    case "python": return python();
    case "sql": return sql();
    default: return [];
  }
}

function renderMarkdown(content: string) {
  return content.split("\n").map((line, index) => {
    if (line.startsWith("### ")) return <h3 key={index}>{line.slice(4)}</h3>;
    if (line.startsWith("## ")) return <h2 key={index}>{line.slice(3)}</h2>;
    if (line.startsWith("# ")) return <h1 key={index}>{line.slice(2)}</h1>;
    if (line.startsWith("- ")) return <li key={index}>{line.slice(2)}</li>;
    return line ? <p key={index}>{line}</p> : <br key={index} />;
  });
}

function useDebouncedValue<T>(value: T, delay = 180) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedValue(value), delay);
    return () => window.clearTimeout(timeout);
  }, [delay, value]);

  return debouncedValue;
}

export function TextEditorDialog({
  document,
  fileName,
  loading = false,
  saving = false,
  error,
  onClose,
  onSave,
  onReload,
}: TextEditorDialogProps) {
  const host = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const syntaxCompartment = useRef(new Compartment());
  const editableCompartment = useRef(new Compartment());
  const dialogRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [content, setContent] = useState(document?.content ?? "");
  const [encoding, setEncoding] = useState<TextFileContent["encoding"]>(document?.encoding ?? "utf-8");
  const [newline, setNewline] = useState<TextFileContent["newline"]>(document?.newline ?? "lf");
  const [mode, setMode] = useState<EditorMode>(inferredSyntax(fileName) === "markdown" ? "markdown" : "text");
  const [syntax, setSyntax] = useState<Syntax>("auto");
  const hasDocument = Boolean(document);

  useEffect(() => {
    if (!document) return;
    setContent(document.content);
    setEncoding(document.encoding);
    setNewline(document.newline);
    const view = viewRef.current;
    if (view && view.state.doc.toString() !== document.content) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: document.content } });
    }
  }, [document]);

  useEffect(() => {
    if (!host.current || viewRef.current || !document) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: document.content,
        extensions: [
          lineNumbers(),
          history(),
          bracketMatching(),
          closeBrackets(),
          autocompletion(),
          syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
          oneDark,
          keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap, ...closeBracketsKeymap, indentWithTab]),
          syntaxCompartment.current.of(syntaxExtension(syntax, fileName)),
          editableCompartment.current.of(EditorView.editable.of(!saving)),
          EditorView.lineWrapping,
          EditorView.updateListener.of((update) => {
            if (update.docChanged) setContent(update.state.doc.toString());
          }),
        ],
      }),
      parent: host.current,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [fileName, hasDocument]);

  useEffect(() => {
    if (!document) return;
    viewRef.current?.dispatch({
      effects: syntaxCompartment.current.reconfigure(syntaxExtension(syntax, fileName)),
    });
  }, [document, fileName, syntax]);

  useEffect(() => {
    viewRef.current?.dispatch({
      effects: editableCompartment.current.reconfigure(EditorView.editable.of(!saving)),
    });
  }, [saving]);

  const dirty = document
    ? content !== document.content || encoding !== document.encoding || newline !== document.newline
    : false;
  const isMarkdown = mode === "markdown";
  const previewContent = useDebouncedValue(content);

  function close() {
    if (!dirty || window.confirm("Discard unsaved changes?")) onClose();
  }

  useEffect(() => {
    previousFocusRef.current = window.document.activeElement instanceof HTMLElement ? window.document.activeElement : null;
    const focusEditor = () => viewRef.current?.focus() ?? dialogRef.current?.focus();
    const timeout = window.setTimeout(focusEditor);
    return () => {
      window.clearTimeout(timeout);
      previousFocusRef.current?.focus();
    };
  }, []);

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      if (document && dirty && !saving) onSave({ content, encoding, newline });
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
      'button:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hasAttribute("hidden"));
    if (!focusable.length) return;
    const currentIndex = focusable.indexOf(window.document.activeElement as HTMLElement);
    const nextIndex = event.shiftKey
      ? (currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1)
      : (currentIndex === focusable.length - 1 ? 0 : currentIndex + 1);
    event.preventDefault();
    focusable[nextIndex].focus();
  }

  return (
    <div className="text-editor-backdrop" role="presentation" onMouseDown={close}>
      <section ref={dialogRef} className="text-editor-dialog" role="dialog" aria-modal="true" aria-label={`Edit ${fileName}`} tabIndex={-1} onKeyDown={handleKeyDown} onMouseDown={(event) => event.stopPropagation()}>
        <header className="text-editor-header">
          <div><h2>{fileName}</h2><p>Browser editor</p></div>
          <button type="button" className="icon-button" onClick={close} aria-label="Close editor">×</button>
        </header>
        {document && <div className="text-editor-controls">
          <label>Mode
            <select value={mode} disabled={saving} onChange={(event) => setMode(event.target.value as EditorMode)}>
              <option value="text">Plain text</option><option value="code">Code</option><option value="markdown">Markdown</option>
            </select>
          </label>
          <label>Syntax
            <select value={syntax} disabled={saving} onChange={(event) => setSyntax(event.target.value as Syntax)}>
              <option value="auto">Auto ({inferredSyntax(fileName)})</option><option value="plain">Plain text</option><option value="javascript">JavaScript / TypeScript</option><option value="json">JSON</option><option value="html">HTML</option><option value="css">CSS</option><option value="markdown">Markdown</option><option value="python">Python</option><option value="sql">SQL</option>
            </select>
          </label>
          <label>Save encoding
            <select value={encoding} disabled={saving} onChange={(event) => setEncoding(event.target.value as TextFileContent["encoding"])}>
              <option value="utf-8">UTF-8</option><option value="utf-8-bom">UTF-8 with BOM</option><option value="utf-16le">UTF-16 LE</option><option value="utf-16be">UTF-16 BE</option><option value="windows-1252">Windows-1252</option>
            </select>
          </label>
          <label>Line endings
            <select value={newline} disabled={saving} onChange={(event) => setNewline(event.target.value as TextFileContent["newline"])}>
              <option value="lf">LF</option><option value="crlf">CRLF</option>
            </select>
          </label>
        </div>}
        {document ? <div className={`text-editor-workspace ${isMarkdown ? "is-markdown" : ""}`}>
          <div className="codemirror-host" ref={host} />
          {isMarkdown && <article className="text-editor-preview">{renderMarkdown(previewContent)}</article>}
        </div> : <div className="text-editor-loading" aria-live="polite">{loading ? "Opening file…" : "File could not be opened."}</div>}
        {error && <p className="text-editor-error" role="alert">{error}</p>}
        <footer className="text-editor-footer">
          <span>{document ? (dirty ? "Unsaved changes" : "All changes saved") : loading ? "Loading" : "Open failed"}</span>
          <div>
            <button type="button" className="button" onClick={close}>{document ? "Cancel" : "Close"}</button>
            {onReload && error && <button type="button" className="button" onClick={onReload}>Reload latest</button>}
            {document && <button type="button" className="button text-editor-save" disabled={!dirty || saving} onClick={() => onSave({ content, encoding, newline })}>{saving ? "Saving…" : "Save"}</button>}
          </div>
        </footer>
      </section>
    </div>
  );
}
