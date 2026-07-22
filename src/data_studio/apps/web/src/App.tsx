import { Route, Routes } from "react-router-dom";

import { DatasetsPage } from "./pages/DatasetsPage";
import { DatasetWorkspace } from "./pages/DatasetWorkspace";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<DatasetsPage />} />
      <Route path="/datasets/:namespace/:dataset/*" element={<DatasetWorkspace />} />
    </Routes>
  );
}

