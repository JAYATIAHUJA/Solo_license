import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../../lib/api.js';
import { useStore } from '../../../lib/store.jsx';
import { toDate } from '../../../lib/format.js';
import { InboxFields } from '../components/IntegrationFields.jsx';
import '../components/plain-form.css';
import '../components/activity.css';
import './inbox.css';

/** Ticket outcomes in plain words, with a tone for the status pill. */
export const TICKET_STATUS = {
  new: { label: 'New', tone: 'muted' },
  done: { label: 'Done · verified', tone: 'ok' },
  waiting: { label: 'Waiting for your OK', tone: 'wait' },
  declined: { label: 'Declined by policy', tone: 'muted' },
  needs_info: { label: 'Asked the customer', tone: 'wait' },
  needs_human: { label: 'Needs a person', tone: 'bad' },
};

const STEP_NAMES = {
  read: 'Read the message',
  find_order: 'Found the order',
  policy: 'Checked your rules',
  act: 'Acted within its licence',
  reply: 'Wrote the reply',
};

const SOURCE = { paste: 'pasted', webhook: 'inbox address', sample: 'sample' };

/** The agent's steps for one message, as a short timeline. */
export function StepList({ steps }) {
  if (!steps?.length) return null;
  return (
    <ol className="ib-steps">
      {steps.map((s, i) => (
        <li key={i} className={`ib-step is-${s.status}`}>
          <b>{STEP_NAMES[s.name] || s.name}</b>
          <span>{s.detail}</span>
        </li>
      ))}
    </ol>
  );
}

function Ticket({ ticket }) {
  const { run, busy } = useStore();
  const [copied, setCopied] = useState(false);
  const status = TICKET_STATUS[ticket.status] || { label: ticket.status, tone: 'muted' };
  const when = toDate(ticket.handled_at || ticket.created_at);
  return (
    <article className="pl-card ib-ticket">
      <header className="ib-head">
        <div>
          <b>{ticket.subject || 'Customer message'}</b>
          <span className="pl-muted pl-small"> · {ticket.sender || 'no email'} · {SOURCE[ticket.source] || ticket.source}{when ? ` · ${when.toLocaleString()}` : ''}</span>
        </div>
        <span className={`pl-status ${status.tone}`}>{status.label}</span>
      </header>
      <blockquote className="ib-body">{ticket.body}</blockquote>
      {ticket.status === 'new' ? (
        <div className="pl-actions">
          <button type="button" className="btn btn-ink btn-sm" disabled={busy}
            onClick={() => run(() => api.handleTicket(ticket.id), (r) => r?.intake?.summary)}>
            Let the agent handle it
          </button>
        </div>
      ) : (
        <>
          {ticket.outcome && <p className="ib-outcome">{ticket.outcome}</p>}
          <details className="pl-more" open={ticket.status !== 'done'}>
            <summary>What the agent did</summary>
            <StepList steps={ticket.steps} />
            {ticket.run_id && <p className="pl-small"><Link className="app-link" to={`/app/runs/${ticket.run_id}`}>Open the run and its evidence</Link></p>}
          </details>
          {ticket.reply && (
            <div className="ib-reply">
              <p className="pl-small pl-muted">Reply to send</p>
              <p>{ticket.reply}</p>
              <button type="button" className="btn btn-line btn-sm"
                onClick={() => navigator.clipboard?.writeText(ticket.reply).then(() => setCopied(true))}>
                {copied ? '✓ Copied' : 'Copy reply'}
              </button>
            </div>
          )}
        </>
      )}
    </article>
  );
}

/** Customer messages in, verified outcomes and replies out. */
export function Inbox() {
  const { data, run, busy } = useStore();
  const tickets = data.tickets || [];
  const fresh = tickets.filter((t) => t.status === 'new').length;
  const [filter, setFilter] = useState('all');
  const shown = tickets.filter((t) => filter === 'all'
    || (filter === 'attention' ? ['waiting', 'needs_human', 'needs_info'].includes(t.status) : t.status === filter));

  return (
    <div className="pl-page">
      <header className="pl-head">
        <div>
          <h1>Inbox</h1>
          <p>Customer messages. The agent reads each one, finds the order, checks your rules and acts only as far as its licence allows.</p>
        </div>
        <div className="pl-actions">
          <Link to="/app/agent" className="btn btn-line btn-sm">Paste a message</Link>
          <button type="button" className="btn btn-ink btn-sm" disabled={busy || !fresh}
            onClick={() => run(() => api.handleNewTickets(), (r) => `Handled ${r?.handled?.length || 0} message${r?.handled?.length === 1 ? '' : 's'}.`)}>
            {fresh ? `Handle ${fresh} new message${fresh === 1 ? '' : 's'}` : 'No new messages'}
          </button>
        </div>
      </header>

      <div className="ib-filters" role="tablist" aria-label="Filter messages">
        {[['all', 'All'], ['attention', 'Needs you'], ['done', 'Done'], ['new', 'New']].map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={filter === id}
            className={`btn btn-sm ${filter === id ? 'btn-ink' : 'btn-ghost'}`} onClick={() => setFilter(id)}>
            {label}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="pl-empty" data-tour="inbox">
          {tickets.length ? 'Nothing here.' : 'No messages yet. Paste one, or connect your helpdesk below.'}
        </div>
      ) : (
        <div className="ib-list" data-tour="inbox">{shown.map((t) => <Ticket key={t.id} ticket={t} />)}</div>
      )}

      <section className="pl-section" aria-labelledby="h-inbox-connect">
        <h2 id="h-inbox-connect">Get messages here automatically</h2>
        <div className="pl-card"><InboxFields /></div>
      </section>
    </div>
  );
}
