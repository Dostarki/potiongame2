import { PixelSheet } from "@/components/game/PixelSheet";
import { CARD_INFO, perMin } from "@/components/game/cards";

const MarketCard = ({ card, owned, busy, onBuy }) => (
  <article className="card" data-testid={`market-card-${card.level}`}>
    <div className="card-art">
      <img src={CARD_INFO[card.level].image} alt={card.name} loading="lazy" />
      <span className="card-level">LV {card.level}</span>
      {owned > 0 && <span className="card-owned" data-testid={`market-owned-${card.level}`}>x{owned}</span>}
    </div>
    <h3 className="card-name">{card.name}</h3>
    <p className="card-text">{CARD_INFO[card.level].text}</p>
    <p className="card-rate">{perMin(card.per_min)}</p>
    <button type="button" className="px-btn px-btn-pink card-buy" data-testid={`buy-button-${card.level}`} disabled={busy} onClick={() => onBuy(card.level)}>
      BUY <b data-testid={`market-price-${card.level}`}>${card.price}</b>
    </button>
  </article>
);

export const MarketPanel = ({ state, busy, onBuy, onClose }) => (
  <PixelSheet title="MARKET" badge="DEMO: NO PAYMENT IS TAKEN" testId="market-panel" onClose={onClose}>
    <div className="card-grid">
      {state.catalog.map((card) => (
        <MarketCard key={card.level} card={card} busy={busy} onBuy={onBuy} owned={state.items.filter((i) => i.level === card.level).length} />
      ))}
    </div>
  </PixelSheet>
);
