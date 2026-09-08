import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AppShell } from '@/components/AppShell';
import { LoginPage } from '@/features/auth/LoginPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { EsgOverviewPage } from '@/features/esg/EsgOverviewPage';
import { PillarPage } from '@/features/esg/PillarPage';
import { MetricLibraryPage } from '@/features/metrics/MetricLibraryPage';
import { KpiTrackingPage } from '@/features/metrics/KpiTrackingPage';
import { CalculationsPage } from '@/features/metrics/CalculationsPage';
import { TargetsPage } from '@/features/metrics/TargetsPage';
import { MetricDetailPage } from '@/features/metrics/MetricDetailPage';
import { SourcesPage } from '@/features/data/SourcesPage';
import { DatasetsPage } from '@/features/data/DatasetsPage';
import { DatasetDetailPage } from '@/features/data/DatasetDetailPage';
import { DataQualityPage } from '@/features/data/DataQualityPage';
import { LineagePage } from '@/features/data/LineagePage';
import { FrameworksPage } from '@/features/standards/FrameworksPage';
import { RequirementsPage } from '@/features/standards/RequirementsPage';
import { MappingPage } from '@/features/standards/MappingPage';
import { CompliancePage } from '@/features/standards/CompliancePage';
import { MaterialityPage } from '@/features/materiality/MaterialityPage';
import { MatrixPage } from '@/features/materiality/MatrixPage';
import { EvidencePage } from '@/features/evidence/EvidencePage';
import { EvidenceDetailPage } from '@/features/evidence/EvidenceDetailPage';
import { EvidenceGapsPage } from '@/features/evidence/EvidenceGapsPage';
import { AgentsPage } from '@/features/ai/AgentsPage';
import { RunsPage } from '@/features/ai/RunsPage';
import { RunDetailPage } from '@/features/ai/RunDetailPage';
import { KnowledgePage } from '@/features/ai/KnowledgePage';
import { RagPage } from '@/features/ai/RagPage';
import { EvaluationPage } from '@/features/ai/EvaluationPage';
import { CopilotPage } from '@/features/ai/CopilotPage';
import { PoliciesPage } from '@/features/governance/PoliciesPage';
import { RulesPage } from '@/features/governance/RulesPage';
import { ApprovalsPage } from '@/features/governance/ApprovalsPage';
import { IssuesPage } from '@/features/governance/IssuesPage';
import { AuditPage } from '@/features/governance/AuditPage';
import { ReportBuilderPage } from '@/features/reports/ReportBuilderPage';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { ReportPreviewPage } from '@/features/reports/ReportPreviewPage';
import { OrganizationPage } from '@/features/admin/OrganizationPage';
import { UsersPage } from '@/features/admin/UsersPage';
import { RolesPage } from '@/features/admin/RolesPage';
import { SystemPage } from '@/features/admin/SystemPage';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { AuthProvider, useAuth } from './auth';
import { AppContextProvider } from './context';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 4xx will not become a 2xx on retry: surface it immediately instead of leaving the
      // user on a loading skeleton while the request is repeated.
      retry: (failureCount, error) => {
        const status = (error as { status?: number } | null)?.status ?? 0;
        if (status >= 400 && status < 500) return false;
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

function RequireAuth() {
  const { isAuthenticated } = useAuth();
  const loc = useLocation();
  if (!isAuthenticated) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return (
    <AppContextProvider>
      <AppShell />
    </AppContextProvider>
  );
}

function RequireCap({ cap }: { cap: string }) {
  const { hasCap } = useAuth();
  if (!hasCap(cap)) {
    return (
      <div className="card p-6 text-sm text-gray-700">
        <div className="font-semibold text-navy">Not authorised</div>
        <p>Your roles do not include the capability <span className="font-mono">{cap}</span> required for this page.</p>
      </div>
    );
  }
  return <Outlet />;
}

export function App() {
  return (
    <ErrorBoundary label="The application">
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route index element={<DashboardPage />} />
                <Route path="esg/overview" element={<EsgOverviewPage />} />
                <Route path="esg/:pillar" element={<PillarPage />} />
                <Route path="data/sources" element={<SourcesPage />} />
                <Route path="data/datasets" element={<DatasetsPage />} />
                <Route path="data/datasets/:id" element={<DatasetDetailPage />} />
                <Route path="data/quality" element={<DataQualityPage />} />
                <Route path="data/lineage" element={<LineagePage />} />
                <Route path="metrics" element={<MetricLibraryPage />} />
                <Route path="metrics/kpis" element={<KpiTrackingPage />} />
                <Route path="metrics/calculations" element={<CalculationsPage />} />
                <Route path="metrics/targets" element={<TargetsPage />} />
                <Route path="metrics/:code" element={<MetricDetailPage />} />
                <Route path="standards/frameworks" element={<FrameworksPage />} />
                <Route path="standards/frameworks/:code" element={<RequirementsPage />} />
                <Route path="standards/mapping" element={<MappingPage />} />
                <Route path="standards/compliance" element={<CompliancePage />} />
                <Route path="materiality" element={<MaterialityPage />} />
                <Route path="materiality/matrix" element={<MatrixPage />} />
                <Route path="evidence" element={<EvidencePage />} />
                <Route path="evidence/gaps" element={<EvidenceGapsPage />} />
                <Route path="evidence/:code" element={<EvidenceDetailPage />} />
                <Route path="ai/agents" element={<AgentsPage />} />
                <Route path="ai/runs" element={<RunsPage />} />
                <Route path="ai/runs/:id" element={<RunDetailPage />} />
                <Route path="ai/knowledge" element={<KnowledgePage />} />
                <Route path="ai/rag" element={<RagPage />} />
                <Route path="ai/evaluation" element={<EvaluationPage />} />
                <Route element={<RequireCap cap="ai.run" />}>
                  <Route path="ai/copilot" element={<CopilotPage />} />
                </Route>
                <Route path="governance/policies" element={<PoliciesPage />} />
                <Route path="governance/rules" element={<RulesPage />} />
                <Route path="governance/approvals" element={<ApprovalsPage />} />
                <Route path="governance/issues" element={<IssuesPage />} />
                <Route element={<RequireCap cap="audit.read" />}>
                  <Route path="governance/audit" element={<AuditPage />} />
                </Route>
                <Route path="reports" element={<ReportsPage />} />
                <Route element={<RequireCap cap="report.build" />}>
                  <Route path="reports/builder" element={<ReportBuilderPage />} />
                </Route>
                <Route path="reports/:id/preview" element={<ReportPreviewPage />} />
                <Route element={<RequireCap cap="admin" />}>
                  <Route path="admin/organization" element={<OrganizationPage />} />
                  <Route path="admin/users" element={<UsersPage />} />
                  <Route path="admin/roles" element={<RolesPage />} />
                  <Route path="admin/system" element={<SystemPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
            </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
