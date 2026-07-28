import { Route, Routes } from "react-router-dom";

import { AuthProvider } from "./components/Auth";
import { ApiDocsPage } from "./pages/ApiDocsPage";
import { AccountSettingsPage } from "./pages/AccountSettingsPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetWorkspace } from "./pages/DatasetWorkspace";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<DatasetsPage />} />
        <Route path="/docs/api" element={<ApiDocsPage />} />
        <Route path="/settings" element={<AccountSettingsPage />} />
        <Route path="/datasets/:namespace/:dataset/*" element={<DatasetWorkspace />} />
      </Routes>
    </AuthProvider>
  );
}
