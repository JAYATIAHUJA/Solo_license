import { useEffect } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useStore } from '../../../lib/store.jsx';
import { HandIcon } from '../../../components/icons/HandIcon.jsx';

export function Toast() {
  const { toast, setToast } = useStore();
  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), toast.kind === 'error' ? 6000 : 3200);
    return () => clearTimeout(t);
  }, [toast, setToast]);

  return (
    <div className="app-toast-wrap" aria-live="polite">
      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.at}
            className={`app-toast ${toast.kind === 'error' ? 'is-error' : ''}`}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
          >
            <HandIcon name={toast.kind === 'error' ? 'warn' : 'check'} size={16} />
            <span>{toast.text}</span>
            <button onClick={() => setToast(null)} aria-label="Dismiss"><HandIcon name="cross" size={12} /></button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
