import { PixelSheet } from "@/components/game/PixelSheet";
import { CARD_INFO, perMin } from "@/components/game/cards";

const InventoryRow = ({ card, items, expansion, busy, onPlace, onRecall, onExpand, onFind }) => {
  const placed = items.filter((i) => i.placed);
  const waiting = items.length - placed.length;
  const full = placed.length >= card.max_placed;
  const canExpand = full && expansion.count < expansion.max;
  return (
    <article className="inv-row" data-testid={`inventory-row-${card.level}`}>
      <img className="inv-art" src={CARD_INFO[card.level].image} alt={card.name} loading="lazy" />
      <div className="inv-info">
        <h3 className="card-name">LV {card.level} · {card.name}</h3>
        <p className="inv-count">
          <span data-testid={`inventory-owned-${card.level}`}>Owned {items.length}</span>
          <span data-testid={`inventory-placed-${card.level}`}>On island {placed.length}/{card.max_placed}</span>
          <span>{perMin(card.per_min)} each</span>
        </p>
        {full && (
          <p className="inv-full" data-testid={`inventory-full-${card.level}`}>
            {canExpand ? "Island full for this level. Expand the island to add more spots." : "Island full and already at its maximum size."}
          </p>
        )}
        <div className="inv-actions">
          {canExpand ? (
            <button type="button" className="px-btn px-btn-mint" data-testid={`expand-button-${card.level}`} disabled={busy} onClick={onExpand}>
              EXPAND ISLAND <b>${expansion.price}</b>
            </button>
          ) : (
            <button type="button" className="px-btn px-btn-pink" data-testid={`place-button-${card.level}`} disabled={busy || !waiting || full} onClick={() => onPlace(card.level)}>
              {full ? "ISLAND FULL" : `PLACE (${waiting})`}
            </button>
          )}
          <button type="button" className="px-btn px-btn-peach" data-testid={`recall-button-${card.level}`} disabled={busy || !placed.length} onClick={() => onRecall(card.level)}>
            RECALL
          </button>
          <button type="button" className="px-btn px-btn-ghost" data-testid={`find-button-${card.level}`} disabled={!placed.length} onClick={() => onFind(placed[placed.length - 1].id)}>
            FIND
          </button>
        </div>
      </div>
    </article>
  );
};

export const InventoryPanel = ({ state, busy, onPlace, onRecall, onExpand, onFind, onClose, onMarket }) => {
  const owned = state.catalog.filter((card) => state.items.some((i) => i.level === card.level));
  return (
    <PixelSheet title="INVENTORY" badge={`${state.items.length} OWNED · ISLAND ${state.expansion.count}/${state.expansion.max}`} testId="inventory-panel" onClose={onClose}>
      {owned.length === 0 && (
        <div className="inv-empty" data-testid="inventory-empty">
          <p>No characters yet. Buy your first worker in the market.</p>
          <button type="button" className="px-btn px-btn-pink" data-testid="inventory-open-market" onClick={onMarket}>OPEN MARKET</button>
        </div>
      )}
      <div className="inv-list">
        {owned.map((card) => (
          <InventoryRow key={card.level} card={card} busy={busy} onPlace={onPlace} onRecall={onRecall} onExpand={onExpand} expansion={state.expansion} onFind={onFind} items={state.items.filter((i) => i.level === card.level)} />
        ))}
      </div>
    </PixelSheet>
  );
};
