import type { Kind } from "@/room/types"

/** The most text the bot takes (`server/config.py` MAX_TEXT_CHARS): past it, the rest is cut. */
export const MAX_TEXT_CHARS = 40_000
/** The biggest file read, and the most of a PDF's pages: a résumé or a PRD is well under both. */
const MAX_FILE_BYTES = 20 * 1024 * 1024
const MAX_PAGES = 80
/** Fewer words than this, and there's nothing to roast: a PDF that's a scan, say. */
const MIN_WORDS = 20

/** What can be uploaded, for the file picker. */
export const ACCEPT =
  ".pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown"

/** A file read for the panel: its text, how long it was, and whether it had to be cut. */
export interface Document {
  name: string
  text: string
  pages: number | null
  words: number
  truncated: boolean
}

/** A file that can't be roasted; the message is for the user. */
export class DocumentError extends Error {}

/**
 * The text of an uploaded file, as the panel will read it: a PDF's text layer, page by page, or a
 * text or markdown file as it is. Read in the browser, so the file itself never leaves it; only
 * its text is sent, as pasted text would be. pdf.js is loaded the first time a PDF is read.
 */
export async function readDocument(file: File): Promise<Document> {
  if (file.size > MAX_FILE_BYTES)
    throw new DocumentError(
      "That file is over 20 MB. A résumé or a PRD is much smaller: export just the text."
    )
  const pdf = /\.pdf$/i.test(file.name) || file.type === "application/pdf"
  const plain =
    /\.(txt|md|markdown)$/i.test(file.name) || file.type.startsWith("text/")
  if (!pdf && !plain)
    throw new DocumentError(
      "That isn't a PDF or a text file. Save it as a PDF, or paste its text."
    )
  const read = pdf
    ? await pdfText(file)
    : { text: await file.text(), pages: null }
  const text = tidy(read.text)
  const words = countWords(text)
  if (words < MIN_WORDS)
    throw new DocumentError(
      pdf
        ? "There's no text in that PDF to read: it may be a scan or an image. Export it as a text PDF, or paste the text."
        : "That file is nearly empty: there's nothing to roast."
    )
  const truncated = text.length > MAX_TEXT_CHARS
  const kept = truncated ? text.slice(0, MAX_TEXT_CHARS) : text
  return {
    name: file.name,
    text: kept,
    pages: read.pages,
    words: truncated ? countWords(kept) : words,
    truncated,
  }
}

async function pdfText(file: File): Promise<{ text: string; pages: number }> {
  const [pdfjs, worker] = await Promise.all([
    import("pdfjs-dist"),
    import("pdfjs-dist/build/pdf.worker.min.mjs?url"),
  ])
  pdfjs.GlobalWorkerOptions.workerSrc = worker.default
  const task = pdfjs.getDocument({ data: await file.arrayBuffer() })
  let doc
  try {
    doc = await task.promise
  } catch (error) {
    const name = error instanceof Error ? error.name : ""
    throw new DocumentError(
      name === "PasswordException"
        ? "That PDF is password-protected. Save a copy without the password, or paste the text."
        : "That PDF couldn't be opened: it may be damaged. Try saving it again, or paste the text."
    )
  }
  try {
    const pages: string[] = []
    let length = 0
    const count = Math.min(doc.numPages, MAX_PAGES)
    // Page by page, until there's more than the panel will read.
    for (let n = 1; n <= count && length <= MAX_TEXT_CHARS; n++) {
      const page = await doc.getPage(n)
      const content = await page.getTextContent()
      let text = ""
      for (const item of content.items) {
        if (!("str" in item)) continue
        text += item.str + (item.hasEOL ? "\n" : "")
      }
      pages.push(text)
      length += text.length
      page.cleanup()
    }
    return { text: pages.join("\n\n"), pages: doc.numPages }
  } finally {
    void task.destroy()
  }
}

/** Each line's spaces collapsed, blank lines collapsed to one (as `server/scout.py` clean_text). */
function tidy(text: string): string {
  return text
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.split(/\s+/).filter(Boolean).join(" "))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

export function countWords(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

const CV_HEADINGS = /\b(Experience|Education|Skills|Summary)\b/g
const PLAN_HEADINGS =
  /\b(Requirements?|User stor(?:y|ies)|Goals?|Non-goals?|Scope|Milestones?|Stakeholders?|Success metrics?|Problem statement|Objectives?|Assumptions|Risks|Timeline|Roadmap|Acceptance criteria|Personas?|KPIs?|Business requirements?|Functional requirements?)\b/gi
const CV_FILE = /(?<![a-z])(cv|resume|résumé)(?![a-z])/i
const PLAN_FILE =
  /(?<![a-z])(prd|brd|mrd|spec|specs|plan|proposal|roadmap|strategy|requirements)(?![a-z])/i

/** What an uploaded file is, from its name and its text, as the bot guesses it
 * (`server/scout.py` detect_kind): a résumé, a plan (a PRD, a BRD, a spec), or anything else. */
export function guessDocumentKind(name: string, text: string): Kind {
  if (CV_FILE.test(name)) return "profile"
  if (PLAN_FILE.test(name)) return "document"
  const cv = new Set(text.match(CV_HEADINGS) ?? []).size
  const plan = new Set(
    (text.match(PLAN_HEADINGS) ?? []).map((h) => h.toLowerCase())
  ).size
  if (plan >= 3 && plan > cv) return "document"
  return cv >= 2 ? "profile" : "website"
}
