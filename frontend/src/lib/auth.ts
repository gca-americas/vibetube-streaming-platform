/**
 * Google sign-in for the admin console.
 *
 * Signing in here proves *who* someone is. It grants nothing on its own: the
 * server checks every admin request against the `admin_users` allowlist and
 * uses the email Google signed, never one this code sends. A user who signs in
 * successfully but is not on the list gets a 403 from every admin endpoint.
 *
 * The Firebase SDK is imported dynamically, and its configuration is fetched
 * from the server rather than compiled in. Two consequences worth keeping:
 * the ~200 kB SDK stays out of the bundle that viewers download for the gate
 * and the showroom, and the same container image can be pointed at a different
 * Firebase project without a rebuild.
 */

export interface FirebaseClientConfig {
  configured: boolean;
  apiKey: string;
  authDomain: string;
  projectId: string;
}

export interface SignedInUser {
  email: string;
  displayName: string;
  photoURL: string;
}

/** Thrown when the server has no Firebase configuration, so sign-in is impossible. */
export class AuthNotConfiguredError extends Error {}

type LoadedAuth = {
  auth: any;
  mod: typeof import("firebase/auth");
};

let loaded: Promise<LoadedAuth> | null = null;

const loadAuth = (): Promise<LoadedAuth> => {
  if (!loaded) {
    loaded = (async () => {
      const res = await fetch("/api/auth/config");
      if (!res.ok) {
        throw new AuthNotConfiguredError("Could not load the sign-in configuration.");
      }
      const config: FirebaseClientConfig = await res.json();
      if (!config.configured) {
        throw new AuthNotConfiguredError(
          "Google sign-in is not configured on this server."
        );
      }

      const [appMod, authMod] = await Promise.all([
        import("firebase/app"),
        import("firebase/auth"),
      ]);

      // getApps() guards against a double initialize under React strict mode's
      // deliberate double-invocation, which would otherwise throw.
      const existing = appMod.getApps();
      const app = existing.length
        ? existing[0]
        : appMod.initializeApp({
            apiKey: config.apiKey,
            authDomain: config.authDomain,
            projectId: config.projectId,
          });

      // localStorage, deliberately -- getAuth's default is IndexedDB, and we
      // opt out of it.
      //
      // All that is persisted is the session: an ID token, a refresh token and
      // a small user record, a few KB in total. localStorage holds that
      // comfortably, so IndexedDB buys nothing here and costs a failure mode.
      //
      // Opening the Google popup makes this document `hidden`, and the browser
      // may close its IndexedDB connection at that moment. The write Firebase
      // performs mid-sign-in then throws "Failed to execute 'transaction' on
      // 'IDBDatabase': The database connection is closing", and the sign-in
      // dies. That happens *after* initialisation, so an ordered persistence
      // fallback does not rescue it -- by then Firebase has committed to
      // IndexedDB. Not using it is the fix; falling back from it is not.
      //
      // The remaining entries cover storage being unwritable at all (private
      // windows, blocked site data). inMemory is last: the session then lasts
      // only as long as the tab, which is worse but still a working sign-in.
      let auth: any;
      try {
        auth = authMod.initializeAuth(app, {
          persistence: [
            authMod.browserLocalPersistence,
            authMod.browserSessionPersistence,
            authMod.inMemoryPersistence,
          ],
          popupRedirectResolver: authMod.browserPopupRedirectResolver,
        });
      } catch (error: any) {
        // Only "already initialised" is safe to swallow: getAuth then returns
        // the instance created above, persistence chain intact. Any other
        // failure means our options were rejected, and falling through to
        // getAuth would silently restore the IndexedDB default this block
        // exists to avoid -- so it is raised rather than papered over.
        if (error?.code !== "auth/already-initialized") throw error;
        auth = authMod.getAuth(app);
      }

      // Completes a sign-in that fell back to redirect. Harmless otherwise --
      // it resolves to null when no redirect is pending.
      try {
        await authMod.getRedirectResult(auth);
      } catch {
        // Surfaced through onAuthStateChanged staying signed-out instead; a
        // throw here would leave the console stuck on "checking your access".
      }

      return { auth, mod: authMod };
    })();
  }
  return loaded;
};

/** Whether this server can do Google sign-in at all. Never throws. */
export const authConfigured = async (): Promise<boolean> => {
  try {
    await loadAuth();
    return true;
  } catch {
    return false;
  }
};

const toUser = (user: any): SignedInUser | null =>
  user
    ? {
        email: user.email || "",
        displayName: user.displayName || "",
        photoURL: user.photoURL || "",
      }
    : null;

/**
 * Subscribes to sign-in state. Fires immediately with the restored session, so
 * a reload does not bounce an already-signed-in operator back to the gate.
 */
export const onAdminAuthChanged = (
  callback: (user: SignedInUser | null) => void
): (() => void) => {
  let cancelled = false;
  let unsubscribe = () => {};

  loadAuth()
    .then(({ auth, mod }) => {
      if (cancelled) return;
      unsubscribe = mod.onAuthStateChanged(auth, (user: any) =>
        callback(toUser(user))
      );
    })
    .catch(() => {
      // Unconfigured is not an error state for the caller -- it is simply
      // "nobody is signed in", and the page says so.
      if (!cancelled) callback(null);
    });

  return () => {
    cancelled = true;
    unsubscribe();
  };
};

export const signInWithGoogle = async (): Promise<void> => {
  const { auth, mod } = await loadAuth();
  const provider = new mod.GoogleAuthProvider();
  // Always offer the account chooser. Without this, a browser signed into one
  // Google account signs straight back in as that account, which makes
  // switching to an allowlisted address impossible without clearing cookies.
  provider.setCustomParameters({ prompt: "select_account" });

  try {
    await mod.signInWithPopup(auth, provider);
  } catch (error: any) {
    // The popup depends on this document staying scriptable and its storage
    // writable while another window has focus. When that is what failed --
    // rather than the user simply cancelling -- redirect is worth trying,
    // because it never needs the opener to survive.
    if (shouldRetryWithRedirect(error)) {
      try {
        await mod.signInWithRedirect(auth, provider);
        return; // The page navigates away; getRedirectResult finishes it.
      } catch (redirectError: any) {
        throw new Error(describeSignInError(redirectError));
      }
    }
    throw new Error(describeSignInError(error));
  }
};

/** Whether this failure is about the popup/storage mechanism, not the user. */
const shouldRetryWithRedirect = (error: any): boolean => {
  const code = error?.code || "";
  if (
    code === "auth/popup-blocked" ||
    code === "auth/operation-not-supported-in-this-environment" ||
    code === "auth/web-storage-unsupported" ||
    code === "auth/internal-error"
  ) {
    return true;
  }
  // The IndexedDB teardown described in loadAuth surfaces as a raw DOM
  // exception rather than a Firebase code, so it is matched on shape.
  return isStorageTeardown(error);
};

const isStorageTeardown = (error: any): boolean => {
  const text = `${error?.name || ""} ${error?.message || ""}`.toLowerCase();
  return (
    text.includes("database connection is closing") ||
    text.includes("idbdatabase") ||
    text.includes("invalidstateerror")
  );
};

export const signOutAdmin = async (): Promise<void> => {
  const { auth, mod } = await loadAuth();
  await mod.signOut(auth);
};

/**
 * A current Firebase ID token, or null when nobody is signed in.
 *
 * The SDK caches the token and refreshes it in the background when it is close
 * to its one-hour expiry, so calling this per request is cheap.
 */
export const getIdToken = async (): Promise<string | null> => {
  try {
    const { auth } = await loadAuth();
    const user = auth.currentUser;
    return user ? await user.getIdToken() : null;
  } catch {
    return null;
  }
};

/** Firebase error codes are not readable; these are the ones an operator hits. */
const describeSignInError = (error: any): string => {
  switch (error?.code) {
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "Sign-in was cancelled.";
    case "auth/popup-blocked":
      return "Your browser blocked the sign-in popup. Allow popups for this site and try again.";
    case "auth/unauthorized-domain":
      return (
        "This domain is not authorised in Firebase Authentication. " +
        "Add it under Authentication -> Settings -> Authorized domains."
      );
    case "auth/operation-not-allowed":
      return (
        "Google sign-in is not enabled for this Firebase project. " +
        "Enable it under Authentication -> Sign-in method."
      );
    case "auth/network-request-failed":
      return "Network error reaching Google. Check your connection and try again.";
    default:
      if (isStorageTeardown(error)) {
        // Last resort: both popup and redirect failed to keep storage alive.
        // The raw text ("The database connection is closing") reads like the
        // site's own database is broken, which is misleading, so it is
        // replaced with something the operator can act on.
        return (
          "Your browser closed its local storage during sign-in. " +
          "This usually means private browsing, a blocked-storage setting, " +
          "or another tab of this site. Close other tabs of this site, or " +
          "allow cookies and site data for this domain, then try again."
        );
      }
      return error?.message || "Sign-in failed.";
  }
};
