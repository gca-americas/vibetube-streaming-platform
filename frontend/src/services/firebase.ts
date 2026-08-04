const firebase = (window as any).firebase;

const isConfigured =
  import.meta.env.VITE_FIREBASE_API_KEY &&
  import.meta.env.VITE_FIREBASE_API_KEY !== "your-api-key";

class MockAuth {
  private listeners: Array<(user: any) => void> = [];
  public currentUser: any = null;

  constructor() {
    const savedUser = localStorage.getItem("mock_user");
    if (savedUser) {
      try {
        const parsed = JSON.parse(savedUser);
        // Bind the getIdToken method back since functions don't serialize
        this.currentUser = {
          ...parsed,
          getIdToken: async () => `mock-token-${parsed.email.split("@")[0]}`
        };
      } catch (e) {
        localStorage.removeItem("mock_user");
      }
    }
  }

  onAuthStateChanged(callback: (user: any) => void) {
    this.listeners.push(callback);
    callback(this.currentUser);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== callback);
    };
  }

  private notify() {
    this.listeners.forEach((l) => l(this.currentUser));
  }

  async signInWithEmailAndPassword(email: string, _: string) {
    const username = email.split("@")[0];
    this.currentUser = {
      uid: `mock-uid-${username}`,
      email: email,
      displayName: username.charAt(0).toUpperCase() + username.slice(1),
      photoURL: "/images/avatars/v1.jpg",
      getIdToken: async () => `mock-token-${username}`
    };
    localStorage.setItem("mock_user", JSON.stringify(this.currentUser));
    this.notify();
    return { user: this.currentUser };
  }

  async createUserWithEmailAndPassword(email: string, _: string) {
    return this.signInWithEmailAndPassword(email, "");
  }

  async signOut() {
    this.currentUser = null;
    localStorage.removeItem("mock_user");
    this.notify();
  }

  async signInWithPopup(_provider: any) {
    return this.signInWithEmailAndPassword("googleuser@example.com", "");
  }
}

let authInstance: any = null;

export const getAuth = () => {
  if (!isConfigured) {
    if (!authInstance) {
      authInstance = new MockAuth();
    }
    return authInstance;
  }

  if (!firebase.apps.length) {
    firebase.initializeApp({
      apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
      authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
      storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
      messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
      appId: import.meta.env.VITE_FIREBASE_APP_ID
    });
  }

  const rawAuth = firebase.auth();
  return {
    onAuthStateChanged: (callback: any) => rawAuth.onAuthStateChanged(callback),
    signInWithEmailAndPassword: (e: string, p: string) => rawAuth.signInWithEmailAndPassword(e, p),
    createUserWithEmailAndPassword: (e: string, p: string) => rawAuth.createUserWithEmailAndPassword(e, p),
    signInWithPopup: (provider: any) => rawAuth.signInWithPopup(provider),
    signOut: () => rawAuth.signOut(),
    get currentUser() {
      const user = rawAuth.currentUser;
      if (!user) return null;
      return {
        uid: user.uid,
        email: user.email,
        displayName: user.displayName || user.email?.split("@")[0],
        photoURL: user.photoURL || "/images/avatars/v1.jpg",
        getIdToken: async () => user.getIdToken()
      };
    }
  };
};
