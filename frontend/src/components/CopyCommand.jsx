import { useState } from 'react';
import './copy-command.css';

/** A command you click to copy: the whole row is the button, with the Copy
 *  chip on the right. `n` numbers it inside a `.cc-list`; `block` is for a
 *  multi-line prompt. */
export function CopyCommand({ text, block = false, n }) {
  const [copied, setCopied] = useState(false);
  const copy = () => navigator.clipboard?.writeText(text)
    .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
    .catch(() => {});
  return (
    <button type="button" className={`cc ${block ? 'is-block' : ''} ${copied ? 'is-copied' : ''}`} onClick={copy} title="Click to copy">
      <span className="cc-mark" aria-hidden="true">{n ?? '$'}</span>
      {block ? <pre>{text}</pre> : <code>{text}</code>}
      <span className="cc-btn">{copied ? 'Copied ✓' : 'Copy'}</span>
    </button>
  );
}

/** Several commands as one numbered, bordered list. */
export function CopyList({ lines }) {
  return (
    <div className="cc-list">
      {lines.map((line, i) => <CopyCommand key={line} text={line} n={i + 1} />)}
    </div>
  );
}
