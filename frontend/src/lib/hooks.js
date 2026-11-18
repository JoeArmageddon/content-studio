import { useCallback, useEffect, useRef, useState } from "react";

// Loads on mount, re-loads every `ms` (if given) and whenever `deps` change.
export function useLoad(fn, deps = [], ms = 0) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [updated, setUpdated] = useState(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const load = useCallback(() => {
    setLoading(true);
    return fnRef.current()
      .then((d) => { setData(d); setError(null); setUpdated(new Date()); })
      .catch((e) => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    if (!ms) return undefined;
    const t = setInterval(load, ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, ms]);

  return { data, error, loading, updated, reload: load };
}
