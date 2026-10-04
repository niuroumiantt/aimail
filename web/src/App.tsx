import { BrowserRouter, HashRouter, Navigate, Route, Routes } from "react-router";
import { lazy, Suspense } from "react";
import { TipProvider } from "@/components/tip";
import { DataProvider } from "@/data/provider";
import InboxPage from "@/pages/inbox";
const KitPage = lazy(() => import("@/pages/kit"));
const LeadsPage = lazy(() => import("@/pages/leads"));
const DesignStudio = lazy(() => import("@/components/design-studio").then(module => ({ default: module.DesignStudio })));
const InboxDesignReview = lazy(() => import("@/components/inbox-design-review").then(module => ({ default: module.InboxDesignReview })));
const OutreachWorkspace = lazy(() => import("@/components/outreach-workspace").then(module => ({ default: module.OutreachWorkspace })));
const FollowupWorkspace = lazy(() => import("@/components/followup-workspace").then(module => ({ default: module.FollowupWorkspace })));
const RealMailbox = lazy(() => import("@/components/real-mailbox").then(module => ({ default: module.RealMailbox })));

/** 在线预览是静态托管,用 hash 路由;正式部署由服务端兜底,用 history 路由。 */
const Router = import.meta.env.VITE_ROUTER === "hash" ? HashRouter : BrowserRouter;
const productionData = import.meta.env.VITE_DATA_SOURCE === "api";

export default function App() {
  return (
    <Router>
      <TipProvider delayDuration={300}>
        <Suspense fallback={<p role="status">正在打开工作区…</p>}>
        <Routes>
          <Route path="/followups" element={<FollowupWorkspace />} />
          <Route path="/followups/:id" element={<FollowupWorkspace />} />
          <Route path="/outreach" element={<OutreachWorkspace />} />
          <Route path="/mail" element={productionData
            ? <Navigate replace to="/" />
            : <Suspense fallback={<p role="status">正在打开真实邮箱…</p>}><RealMailbox /></Suspense>} />
          <Route path="/design" element={<DesignStudio />} />
          <Route path="/design/inbox" element={<InboxDesignReview />} />
          <Route path="*" element={
            <DataProvider>
              <Routes>
                <Route path="/" element={<InboxPage />} />
                <Route path="/t/:id" element={<InboxPage />} />
                <Route path="/leads" element={<LeadsPage />} />
                <Route path="/kit" element={<KitPage />} />
              </Routes>
            </DataProvider>
          } />
        </Routes>
        </Suspense>
      </TipProvider>
    </Router>
  );
}
