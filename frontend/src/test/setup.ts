// Vitest setup — runs before test modules are imported.
// The zustand store uses persist(createJSONStorage(() => localStorage)); make sure a
// working localStorage exists at module-eval time regardless of environment quirks.
class MemoryStorage implements Storage {
    private map = new Map<string, string>();
    get length() { return this.map.size; }
    clear() { this.map.clear(); }
    getItem(key: string) { return this.map.has(key) ? this.map.get(key)! : null; }
    key(index: number) { return [...this.map.keys()][index] ?? null; }
    removeItem(key: string) { this.map.delete(key); }
    setItem(key: string, value: string) { this.map.set(key, String(value)); }
}

if (typeof globalThis.localStorage === "undefined" || globalThis.localStorage === null) {
    Object.defineProperty(globalThis, "localStorage", {
        value: new MemoryStorage(),
        writable: true,
    });
}
