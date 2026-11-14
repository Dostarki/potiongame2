import { useConnectModal } from "@rainbow-me/rainbowkit";
import { useDisconnect, useSwitchChain } from "wagmi";
import { toast } from "sonner";
import { robinhood } from "@/lib/wallet";
import { errorText } from "@/lib/gameApi";

export const MainMenu = ({ session }) => {
  const { openConnectModal } = useConnectModal();
  const { switchChain, isPending: switching } = useSwitchChain();
  const { disconnect } = useDisconnect();

  let label = "CONNECT WALLET";
  let action = openConnectModal;
  let note = "Connect your wallet to enter the island.";
  if (session.wrongChain) {
    label = switching ? "CHECK YOUR WALLET..." : "SWITCH TO ROBINHOOD CHAIN";
    action = () => switchChain({ chainId: robinhood.id }, { onError: (e) => toast.error(errorText(e)) });
    note = "Your wallet is on another network. Only Robinhood Chain mainnet is accepted.";
  } else if (session.isConnected) {
    label = session.signing ? "CHECK YOUR WALLET..." : "SIGN TO ENTER";
    action = session.signIn;
    note = "Approve the sign-in message in your wallet. It is free and sends no transaction.";
  }

  return (
    <div className="menu-veil" data-testid="main-menu">
      <div className="menu-card">
        <img className="menu-potion" src="/assets/potion.png" alt="" />
        <p className="menu-kicker">PINK DREAM ISLAND</p>
        <h1 className="menu-title" data-testid="main-menu-title">POTIONRH</h1>
        <p className="menu-note" data-testid="main-menu-note">{note}</p>
        <button
          type="button"
          className="px-btn px-btn-pink menu-cta"
          data-testid="connect-wallet-button"
          disabled={session.signing || switching}
          onClick={action}
        >
          {label}
        </button>
        {session.error && <p className="menu-error" data-testid="main-menu-error">{session.error}</p>}
        <div className="menu-foot">
          <span className="chain-pill" data-testid="chain-pill"><i />ROBINHOOD CHAIN ONLY</span>
          {session.isConnected && (
            <button type="button" className="menu-link" data-testid="disconnect-wallet-button" onClick={() => disconnect()}>
              Disconnect
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
