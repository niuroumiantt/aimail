import { useEffect, useState } from "react";
import type { ListCaption, Thread } from "./types";

export type LoadCaptions = (ids: string[], generate: boolean, retry?: boolean) => Promise<Record<string, ListCaption | null>>;

/** Queue bounded batches on demand; switching scope/view stops polling, not saved work. */
export function useListCaptions(threads: Thread[], enabled: boolean, load?: LoadCaptions) {
  const [state, setState] = useState<{ key: string; values: Record<string, ListCaption | null>; error: string }>({ key: "", values: {}, error: "" });
  const [retry, setRetry] = useState(0);
  const key = JSON.stringify(threads.map(t => [t.id, t.updated_at, t.message_count]));
  useEffect(() => {
    if (!enabled || !load) return;
    let stopped = false;
    const run = async () => {
      const ids = (JSON.parse(key) as string[][]).map(item => item[0]);
      setState({ key, values: {}, error: "" });
      const update = (values: Record<string, ListCaption | null>) => {
        if (!stopped) setState(current => ({ key, values: { ...(current.key === key ? current.values : {}), ...values }, error: "" }));
      };
      try {
        for (let start = 0; start < ids.length && !stopped; start += 40) {
          const batch = ids.slice(start, start + 40);
          let values = await load(batch, true, retry > 0);
          update(values);
          let polls = 0;
          while (!stopped && Object.values(values).some(value => value?.status === "pending")) {
            if (++polls > 240) throw new Error("中文描述仍在生成，稍后重试即可读取已保存的结果");
            await new Promise(resolve => setTimeout(resolve, 1500));
            if (stopped) return;
            values = await load(batch, false);
            update(values);
          }
        }
      } catch (e) {
        if (!stopped) setState(current => ({ ...current, key, error: e instanceof Error ? e.message : String(e) }));
      }
    };
    void run();
    return () => { stopped = true; };
  }, [key, enabled, load, retry]);
  const values = state.key === key ? state.values : {};
  return { values, error: state.key === key ? state.error : "", failed: Object.values(values).some(v => v?.status === "failed"), retry: () => setRetry(value => value + 1) };
}
