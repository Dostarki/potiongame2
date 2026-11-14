import { connectorsForWallets, getDefaultConfig } from "@rainbow-me/rainbowkit";
import { injectedWallet } from "@rainbow-me/rainbowkit/wallets";
import { createConfig, http } from "wagmi";

export const robinhood = {
  id: 4663,
  name: "Robinhood Chain",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: { default: { http: ["https://rpc.mainnet.chain.robinhood.com"] } },
  blockExplorers: { default: { name: "Blockscout", url: "https://robinhoodchain.blockscout.com" } },
};

const appName = "PotionRH";
const projectId = process.env.REACT_APP_WALLETCONNECT_PROJECT_ID;
const chains = [robinhood];
const transports = { [robinhood.id]: http() };

export const hasWalletConnect = Boolean(projectId);

// Without a WalletConnect project id only wallets injected into the browser can connect.
export const walletConfig = projectId
  ? getDefaultConfig({ appName, appUrl: window.location.origin, projectId, chains, transports })
  : createConfig({
      chains,
      transports,
      connectors: connectorsForWallets([{ groupName: "Installed", wallets: [injectedWallet] }], { appName, projectId: "none" }),
    });
