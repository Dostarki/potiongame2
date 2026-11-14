import { motion } from "framer-motion";
import { X } from "lucide-react";

export const PixelSheet = ({ title, badge, testId, onClose, children }) => (
  <motion.div className="sheet-veil" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
    <motion.section
      className="sheet"
      data-testid={testId}
      initial={{ y: 60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 60, opacity: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 30 }}
      onClick={(e) => e.stopPropagation()}
    >
      <header className="sheet-head">
        <h2 className="sheet-title">{title}</h2>
        {badge && <span className="sheet-badge" data-testid={`${testId}-badge`}>{badge}</span>}
        <button type="button" className="sheet-close" data-testid={`${testId}-close`} aria-label="Close" onClick={onClose}>
          <X size={18} strokeWidth={3} />
        </button>
      </header>
      <div className="sheet-body">{children}</div>
    </motion.section>
  </motion.div>
);
