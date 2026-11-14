import { useCallback, useEffect, useRef, useState } from "react";
import { useAccount, useSignMessage } from "wagmi";
import { createSiweMessage } from "viem/siwe";
import { robinhood } from "@/lib/wallet";
import { errorText, fetchNonce, verifyWallet } from "@/lib/gameApi";

const keyOf = (address) => `potion.session.${address.toLowerCase()}`;

function readToken(address) {
  try {
    const token = localStorage.getItem(keyOf(address));
    const { exp } = JSON.parse(atob(token.split(".")[1]));
    return exp * 1000 > Date.now() + 60_000 ? token : null;
  } catch {
    return null;
  }
}

export function useSession() {
  const { address, isConnected, chainId } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const [session, setSession] = useState({ address: null, token: null });
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState("");
  const tried = useRef(new Set());

  const onChain = isConnected && chainId === robinhood.id;
  const token = address && session.address === address ? session.token : null;

  useEffect(() => {
    setError("");
    setSession({ address: address || null, token: address ? readToken(address) : null });
  }, [address]);

  const signIn = useCallback(async () => {
    if (!address) return;
    setSigning(true);
    setError("");
    try {
      const nonce = await fetchNonce(address);
      const message = createSiweMessage({
        address,
        chainId: robinhood.id,
        domain: window.location.host,
        uri: window.location.origin,
        nonce,
        version: "1",
        statement: "Sign in to PotionRH on Robinhood Chain.",
        expirationTime: new Date(Date.now() + 10 * 60_000),
      });
      const signature = await signMessageAsync({ message });
      const data = await verifyWallet(message, signature);
      localStorage.setItem(keyOf(address), data.token);
      setSession({ address, token: data.token });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSigning(false);
    }
  }, [address, signMessageAsync]);

  const signOut = useCallback(() => {
    if (address) localStorage.removeItem(keyOf(address));
    setSession({ address: address || null, token: null });
  }, [address]);

  // Ask for the signature once, right after the wallet connects on the right chain.
  useEffect(() => {
    if (!onChain || !address || session.address !== address || session.token || tried.current.has(address)) return;
    tried.current.add(address);
    signIn();
  }, [onChain, address, session, signIn]);

  return { address, isConnected, wrongChain: isConnected && !onChain, token, ready: onChain && Boolean(token), signing, error, signIn, signOut };
}
