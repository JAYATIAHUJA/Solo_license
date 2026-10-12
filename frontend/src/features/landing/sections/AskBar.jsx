import { useState } from 'react';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

const COMMAND = 'uvx --from git+https://github.com/JAYATIAHUJA/Solo_license solo-license onboard';

/** The one install command, shown in full. One click copies it and the button
 *  says so. */
export function AskBar() {
  const [copied, setCopied] = useState(false);

  function copy(e) {
    e.preventDefault();
    navigator.clipboard?.writeText(COMMAND)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); })
      .catch(() => {});
  }

  return (
    <form className={`lp-ask ${copied ? 'is-copied' : ''}`} onSubmit={copy}>
      <HandIcon name="play" size={18} />
      <code className="lp-ask-cmd">{COMMAND}</code>
      <button className="btn btn-ink btn-sm" type="submit" aria-live="polite">
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
    </form>
  );
}
