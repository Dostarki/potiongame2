import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { useSession } from "@/hooks/useSession";
import { errorText, fetchState, gameAction } from "@/lib/gameApi";
import { MainMenu } from "@/components/game/MainMenu";
import { GameHud } from "@/components/game/GameHud";
import { MarketPanel } from "@/components/game/MarketPanel";
import { InventoryPanel } from "@/components/game/InventoryPanel";
import { LeaderboardPanel } from "@/components/game/LeaderboardPanel";

const DONE = { buy: "Added to your inventory", place: "Placed on the island", recall: "Back in your inventory", expand: "Island expanded" };

export default function GamePage() {
  const session = useSession();
  const queryClient = useQueryClient();
  const frame = useRef(null);
  const [frameReady, setFrameReady] = useState(false);
  const [panel, setPanel] = useState(null);
  const [busy, setBusy] = useState(false);
  const queryKey = ["game-state", session.address];

  const { data: state, error } = useQuery({ queryKey, queryFn: () => fetchState(session.token), enabled: session.ready, staleTime: 0 });

  const post = useCallback((message) => frame.current?.contentWindow?.postMessage(message, window.location.origin), []);

  useEffect(() => {
    const onMessage = (e) => {
      if (e.origin === window.location.origin && e.data?.type === "potion:ready") setFrameReady(true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (error?.response?.status === 401 || error?.response?.status === 403) session.signOut();
  }, [error, session]);

  const live = session.ready ? state : null;
  useEffect(() => {
    if (!frameReady) return;
    post({
      type: "potion:state",
      placed: (live?.items || []).filter((i) => i.placed).map(({ id, level, slot }) => ({ id, level, slot })),
      potion: live?.potion || 0,
      rate: (live?.per_min || 0) / 60,
      focus: live?.focus,
      plots: live?.expansion?.count || 0,
      focusPlot: live?.focus_plot,
    });
  }, [frameReady, live, post]);

  const act = async (action, level) => {
    setBusy(true);
    try {
      const next = await gameAction(session.token, action, level);
      queryClient.setQueryData(queryKey, next);
      toast.success(DONE[action]);
      if (action === "place" || action === "expand") setPanel(null);
    } catch (err) {
      if (err?.response?.status === 401) session.signOut();
      toast.error(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const find = (id) => {
    post({ type: "potion:focus", id });
    setPanel(null);
  };

  return (
    <div className="game-shell" data-testid="game-page">
      <iframe ref={frame} data-testid="game-frame" title="PotionRH" src="/game.html" className="game-frame" />
      {!session.ready && <MainMenu session={session} />}
      {session.ready && state && (
        <>
          <GameHud address={session.address} owned={state.items.length} onMarket={() => setPanel("market")} onInventory={() => setPanel("inventory")} onLeaderboard={() => setPanel("leaderboard")} />
          <AnimatePresence>
            {panel === "leaderboard" && <LeaderboardPanel key="leaderboard" token={session.token} onClose={() => setPanel(null)} />}
            {panel === "market" && <MarketPanel key="market" state={state} busy={busy} onBuy={(lv) => act("buy", lv)} onClose={() => setPanel(null)} />}
            {panel === "inventory" && (
              <InventoryPanel
                key="inventory"
                state={state}
                busy={busy}
                onPlace={(lv) => act("place", lv)}
                onRecall={(lv) => act("recall", lv)}
                onExpand={() => act("expand")}
                onFind={find}
                onMarket={() => setPanel("market")}
                onClose={() => setPanel(null)}
              />
            )}
          </AnimatePresence>
        </>
      )}
    </div>
  );
}
