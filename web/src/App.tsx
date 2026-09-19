import { BrowserRouter, HashRouter, Route, Routes } from "react-router";
import { TipProvider } from "@/components/tip";
import { DataProvider } from "@/data/provider";
import InboxPage from "@/pages/inbox";
import KitPage from "@/pages/kit";
import LeadsPage from "@/pages/leads";

/** 在线预览是静态托管,用 hash 路由;正式部署由服务端兜底,用 history 路由。 */
const Router = import.meta.env.VITE_ROUTER === "hash" ? HashRouter : BrowserRouter;

export default function App() {
  return (
    <Router>
      <TipProvider delayDuration={300}>
        <DataProvider>
          <Routes>
            <Route path="/" element={<InboxPage />} />
            <Route path="/t/:id" element={<InboxPage />} />
            <Route path="/leads" element={<LeadsPage />} />
            <Route path="/kit" element={<KitPage />} />
          </Routes>
        </DataProvider>
      </TipProvider>
    </Router>
  );
}
