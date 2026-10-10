import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useStore } from '../../../lib/store.jsx';
import { PageHeader } from '../components/Bits.jsx';
import { LicenseCard } from '../components/mission/LicenseCard.jsx';
import { classCards } from '../components/mission/derive.js';

/** One "Agent Driving License" per task class — shareable as a PNG. */
export function License() {
  const { data } = useStore();
  const { hash } = useLocation();
  const cards = classCards(data);
  const threshold = data.config.promotion_clean_runs;

  useEffect(() => {
    if (!hash) return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [hash]);

  return (
    <>
      <PageHeader eyebrow={`${data.settings.business_name || 'Workspace'} · licenses`} title={<>The agent’s <em className="italic">driving licenses.</em></>}>
        One license per task class, earned run by run and revoked the moment a detection fires. Download one as a PNG or copy a post for #neatHack.
      </PageHeader>
      <div className="mc-lic-grid">
        {cards.map((card) => <LicenseCard key={card.key} data={data} card={card} threshold={threshold} />)}
      </div>
    </>
  );
}
