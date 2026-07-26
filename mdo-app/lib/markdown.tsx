"use client"

// Minimal markdown renderer for MDO Brain answers — headings, bold/italic,
// inline code, fenced code, lists, pipe tables, blockquotes, hr, links.
// No external deps; output is styled by the `.md` rules in globals.css.

import React from "react"

function inline(text: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = []
  // tokenize: `code`, **bold**, *italic*, [label](url)
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(\[[^\]]+\]\((?:https?:\/\/)[^)\s]+\))/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const tok = m[0]
    const k = `${keyBase}-${i++}`
    if (tok.startsWith("`")) out.push(<code key={k}>{tok.slice(1, -1)}</code>)
    else if (tok.startsWith("**")) out.push(<strong key={k}>{inline(tok.slice(2, -2), k)}</strong>)
    else if (tok.startsWith("[")) {
      const mm = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
      if (mm) out.push(<a key={k} href={mm[2]} target="_blank" rel="noreferrer" style={{ color: "var(--accent2)", textDecoration: "underline", textUnderlineOffset: 2 }}>{mm[1]}</a>)
      else out.push(tok)
    } else out.push(<em key={k}>{inline(tok.slice(1, -1), k)}</em>)
    last = m.index + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function isTableRow(l: string) {
  const t = l.trim()
  return t.startsWith("|") && t.endsWith("|") && t.length > 2
}
function splitRow(l: string): string[] {
  return l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(c => c.trim())
}
function isDivider(l: string) {
  return isTableRow(l) && splitRow(l).every(c => /^:?-{2,}:?$/.test(c))
}

export function Markdown({ text }: { text: string }) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n")
  const blocks: React.ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]
    const t = line.trim()

    if (!t) { i++; continue }

    // fenced code
    if (t.startsWith("```")) {
      const buf: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith("```")) { buf.push(lines[i]); i++ }
      i++ // closing fence
      blocks.push(<pre key={key++}><code>{buf.join("\n")}</code></pre>)
      continue
    }

    // table
    if (isTableRow(line) && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const header = splitRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && isTableRow(lines[i])) { rows.push(splitRow(lines[i])); i++ }
      blocks.push(
        <div className="md-table-wrap" key={key++}>
          <table>
            <thead><tr>{header.map((h, j) => <th key={j}>{inline(h, `th${key}-${j}`)}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{header.map((_, ci) => <td key={ci}>{inline(r[ci] ?? "", `td${key}-${ri}-${ci}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      continue
    }

    // heading
    const h = t.match(/^(#{1,3})\s+(.*)$/)
    if (h) {
      const Tag = (["h1", "h2", "h3"] as const)[h[1].length - 1]
      blocks.push(<Tag key={key++}>{inline(h[2], `h${key}`)}</Tag>)
      i++
      continue
    }

    // hr
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) { blocks.push(<hr key={key++} />); i++; continue }

    // blockquote
    if (t.startsWith(">")) {
      const buf: string[] = []
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        buf.push(lines[i].trim().replace(/^>\s?/, ""))
        i++
      }
      blocks.push(<blockquote key={key++}>{inline(buf.join(" "), `bq${key}`)}</blockquote>)
      continue
    }

    // lists (unordered / ordered), single level
    const ul = /^[-*•]\s+/.test(t)
    const ol = /^\d+[.)]\s+/.test(t)
    if (ul || ol) {
      const items: string[] = []
      const test = ul ? /^[-*•]\s+/ : /^\d+[.)]\s+/
      while (i < lines.length && test.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(test, ""))
        i++
      }
      const L = ul ? "ul" : "ol"
      blocks.push(
        React.createElement(
          L,
          { key: key++ },
          items.map((it, j) => <li key={j}>{inline(it, `li${key}-${j}`)}</li>)
        )
      )
      continue
    }

    // paragraph — merge consecutive plain lines
    const buf: string[] = [t]
    i++
    while (i < lines.length) {
      const nt = lines[i].trim()
      if (!nt || nt.startsWith("#") || nt.startsWith(">") || nt.startsWith("```") ||
          /^[-*•]\s+/.test(nt) || /^\d+[.)]\s+/.test(nt) || isTableRow(lines[i]) ||
          /^(-{3,}|\*{3,}|_{3,})$/.test(nt)) break
      buf.push(nt)
      i++
    }
    blocks.push(<p key={key++}>{inline(buf.join(" "), `p${key}`)}</p>)
  }

  return <div className="md">{blocks}</div>
}
