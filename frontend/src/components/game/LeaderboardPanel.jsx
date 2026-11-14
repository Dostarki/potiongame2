import { useQuery } from "@tanstack/react-query";
import { PixelSheet } from "@/components/game/PixelSheet";
import { errorText, fetchLeaderboard } from "@/lib/gameApi";

const LeaderRow = ({ row, max, testId }) => (
  <li className={`lb-row${row.me ? " lb-me" : ""}`} data-testid={testId}>
    <span className="lb-rank" data-testid={`${testId}-rank`}>#{row.rank}</span>
    <span className="lb-wallet" data-testid={`${testId}-wallet`}>
      {row.wallet}
      {row.me && <b className="lb-you">YOU</b>}
    </span>
    <span className="lb-stat" data-testid={`${testId}-characters`}>{row.characters} chars</span>
    <span className="lb-stat" data-testid={`${testId}-island`}>Island {row.expansions}/{max}</span>
  </li>
);

export const LeaderboardPanel = ({ token, onClose }) => {
  const { data, error, isLoading } = useQuery({ queryKey: ["leaderboard"], queryFn: () => fetchLeaderboard(token), staleTime: 0 });
  const outside = data?.me && data.me.rank > data.leaders.length;
  return (
    <PixelSheet title="LEADERBOARD" badge={data ? `${data.total} WALLETS` : null} testId="leaderboard-panel" onClose={onClose}>
      {isLoading && <p className="lb-note" data-testid="leaderboard-loading">Loading ranking…</p>}
      {error && <p className="lb-note inv-full" data-testid="leaderboard-error">{errorText(error)}</p>}
      {data && data.leaders.length === 0 && <p className="lb-note" data-testid="leaderboard-empty">No wallets ranked yet. Buy a character to take first place.</p>}
      {data && (
        <ol className="lb-list" data-testid="leaderboard-list">
          {data.leaders.map((row) => <LeaderRow key={row.rank} row={row} max={data.max_expansions} testId={`leaderboard-row-${row.rank}`} />)}
          {outside && <LeaderRow row={data.me} max={data.max_expansions} testId="leaderboard-row-me" />}
        </ol>
      )}
    </PixelSheet>
  );
};
