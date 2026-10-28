import React from 'react';

/**
 * Minimal, safe markdown for chat answers: **bold**, *italic* / _italic_, `code`, headings (#..###),
 * bullet and numbered lists, > quotes, and [S1]-style citation chips. Builds React elements only -
 * never injects HTML, so answer text cannot carry markup or scripts. Also turns stray HTML entities
 * such as &rarr; into their characters.
 */

const ENTITIES: Record<string, string> = {
  '&rarr;': '→', '&larr;': '←', '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'", '&nbsp;': ' ',
  '&mdash;': '—', '&ndash;': '–', '&hellip;': '…',
};

export const decodeEntities = (s: string) => s.replace(/&(rarr|larr|amp|lt|gt|quot|#39|nbsp|mdash|ndash|hellip);/g, (m) => ENTITIES[m] ?? m);

const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_|\[S\d+\])/g;

function inline(text: string, keyBase: string, onCite?: (n: number) => void): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of decodeEntities(text).matchAll(INLINE)) {
    const tok = m[0];
    const at = m.index ?? 0;
    if (at > last) out.push(decodeEntities(text).slice(last, at));
    const key = `${keyBase}-${i++}`;
    if (tok.startsWith('**') || tok.startsWith('__')) out.push(<strong key={key}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith('`')) out.push(<code key={key} className="px-1 rounded bg-slate-100 text-[0.95em]">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith('[S')) {
      const n = Number(tok.slice(2, -1));
      out.push(
        <button key={key} type="button" onClick={() => onCite?.(n)} disabled={!onCite}
          className="mx-0.5 px-1 rounded bg-blue-50 text-blue-700 border border-blue-200 text-[0.85em] font-semibold align-baseline disabled:cursor-default">
          S{n}
        </button>,
      );
    } else out.push(<em key={key}>{tok.slice(1, -1)}</em>);
    last = at + tok.length;
  }
  const decoded = decodeEntities(text);
  if (last < decoded.length) out.push(decoded.slice(last));
  return out;
}

export const MarkdownText: React.FC<{ text: string; onCite?: (n: number) => void; className?: string }> = ({ text, onCite, className }) => {
  const blocks: React.ReactNode[] = [];
  let seq = 0;
  const nextKey = () => `b${seq++}`;  // one counter for every block, so keys never collide
  const lines = (text || '').replace(/\r\n/g, '\n').split('\n');
  let list: { ordered: boolean; items: string[] } | null = null;
  let quote: string[] = [];
  const flush = () => {
    if (list) {
      const items = list.items.map((it, k) => <li key={k}>{inline(it, `li${blocks.length}-${k}`, onCite)}</li>);
      blocks.push(list.ordered
        ? <ol key={nextKey()} className="list-decimal pl-5 space-y-0.5">{items}</ol>
        : <ul key={nextKey()} className="list-disc pl-5 space-y-0.5">{items}</ul>);
      list = null;
    }
    if (quote.length) {
      blocks.push(
        <blockquote key={nextKey()} className="border-l-2 border-slate-300 pl-2 text-slate-600 space-y-0.5">
          {quote.map((q, k) => <p key={k}>{inline(q, `q${blocks.length}-${k}`, onCite)}</p>)}
        </blockquote>,
      );
      quote = [];
    }
  };
  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    const q = line.match(/^\s*>\s?(.*)$/);
    if (bullet || numbered) {
      if (quote.length) flush();
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flush();
      if (!list) list = { ordered, items: [] };
      list.items.push((bullet || numbered)![1]);
    } else if (q) {
      if (list) flush();
      quote.push(q[1]);
    } else {
      flush();
      if (heading) {
        blocks.push(<p key={nextKey()} className="font-bold text-slate-900">{inline(heading[2], `h${idx}`, onCite)}</p>);
      } else if (line.trim()) {
        blocks.push(<p key={nextKey()}>{inline(line, `p${idx}`, onCite)}</p>);
      }
    }
  });
  flush();
  return <div className={`space-y-1.5 ${className || ''}`}>{blocks}</div>;
};
