import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  Building2,
  CheckSquare,
  ClipboardList,
  Database,
  FileCheck2,
  FileText,
  Gauge,
  GitBranch,
  Globe2,
  Landmark,
  Layers,
  Leaf,
  LibraryBig,
  ListChecks,
  MessageSquare,
  Network,
  Scale,
  ScrollText,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Wallet,
  Workflow,
  AlertTriangle,
  Sigma,
  Boxes,
} from 'lucide-react';

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  cap?: string;
  end?: boolean;
}

export interface NavGroup {
  label: string;
  cap?: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  { label: 'Overview', items: [{ label: 'Dashboard', to: '/', icon: Gauge, end: true }] },
  {
    label: 'ESG Intelligence',
    items: [
      { label: 'Overview', to: '/esg/overview', icon: Globe2 },
      { label: 'Environment', to: '/esg/environment', icon: Leaf },
      { label: 'Social', to: '/esg/social', icon: Users },
      { label: 'Governance', to: '/esg/governance', icon: Landmark },
      { label: 'Prosperity', to: '/esg/prosperity', icon: Wallet },
    ],
  },
  {
    label: 'Data',
    items: [
      { label: 'Data Sources', to: '/data/sources', icon: Database },
      { label: 'Datasets', to: '/data/datasets', icon: Boxes },
      { label: 'Data Quality', to: '/data/quality', icon: Activity },
      { label: 'Data Lineage', to: '/data/lineage', icon: GitBranch },
    ],
  },
  {
    label: 'Metrics',
    items: [
      { label: 'Metric Library', to: '/metrics', icon: LibraryBig, end: true },
      { label: 'KPI Tracking', to: '/metrics/kpis', icon: TrendingUp },
      { label: 'Calculations', to: '/metrics/calculations', icon: Sigma },
      { label: 'Targets', to: '/metrics/targets', icon: Target },
    ],
  },
  {
    label: 'Standards',
    items: [
      { label: 'Frameworks', to: '/standards/frameworks', icon: BookOpen },
      { label: 'Mapping', to: '/standards/mapping', icon: Network },
      { label: 'Compliance', to: '/standards/compliance', icon: FileCheck2 },
    ],
  },
  {
    label: 'Materiality',
    items: [
      { label: 'Assessment', to: '/materiality', icon: Layers, end: true },
      { label: 'Matrix', to: '/materiality/matrix', icon: BarChart3 },
    ],
  },
  {
    label: 'Evidence',
    items: [
      { label: 'Repository', to: '/evidence', icon: ScrollText, end: true },
      { label: 'Gaps', to: '/evidence/gaps', icon: AlertTriangle },
    ],
  },
  {
    label: 'AI',
    items: [
      { label: 'Agents', to: '/ai/agents', icon: Bot },
      { label: 'Agent Runs', to: '/ai/runs', icon: Workflow },
      { label: 'Knowledge Base', to: '/ai/knowledge', icon: LibraryBig },
      { label: 'RAG Search', to: '/ai/rag', icon: Search },
      { label: 'Evaluation', to: '/ai/evaluation', icon: ListChecks },
      { label: 'Copilot', to: '/ai/copilot', icon: MessageSquare, cap: 'ai.run' },
    ],
  },
  {
    label: 'Governance',
    items: [
      { label: 'Policies', to: '/governance/policies', icon: Scale },
      { label: 'Rules', to: '/governance/rules', icon: Shield },
      { label: 'Approvals', to: '/governance/approvals', icon: CheckSquare },
      { label: 'Issues', to: '/governance/issues', icon: ShieldAlert },
      { label: 'Audit Trail', to: '/governance/audit', icon: ClipboardList, cap: 'audit.read' },
    ],
  },
  {
    label: 'Reports',
    items: [
      { label: 'Report Builder', to: '/reports/builder', icon: Sparkles, cap: 'report.build' },
      { label: 'Generated Reports', to: '/reports', icon: FileText, end: true },
    ],
  },
  {
    label: 'Administration',
    cap: 'admin',
    items: [
      { label: 'Organization', to: '/admin/organization', icon: Building2 },
      { label: 'Users', to: '/admin/users', icon: Users },
      { label: 'Roles', to: '/admin/roles', icon: Shield },
      { label: 'System', to: '/admin/system', icon: Settings },
    ],
  },
];

/** Breadcrumb titles by path segment. */
export const SEGMENT_TITLES: Record<string, string> = {
  esg: 'ESG Intelligence',
  overview: 'Overview',
  environment: 'Environment',
  social: 'Social',
  governance: 'Governance',
  prosperity: 'Prosperity',
  data: 'Data',
  sources: 'Data Sources',
  datasets: 'Datasets',
  quality: 'Data Quality',
  lineage: 'Data Lineage',
  metrics: 'Metrics',
  kpis: 'KPI Tracking',
  calculations: 'Calculations',
  targets: 'Targets',
  standards: 'Standards',
  frameworks: 'Frameworks',
  mapping: 'Mapping',
  compliance: 'Compliance',
  materiality: 'Materiality',
  matrix: 'Matrix',
  evidence: 'Evidence',
  gaps: 'Gaps',
  ai: 'AI',
  agents: 'Agents',
  runs: 'Agent Runs',
  knowledge: 'Knowledge Base',
  rag: 'RAG Search',
  evaluation: 'Evaluation Centre',
  copilot: 'Copilot',
  policies: 'Policies',
  rules: 'Rules',
  approvals: 'Approvals',
  issues: 'Issues',
  audit: 'Audit Trail',
  reports: 'Reports',
  builder: 'Report Builder',
  preview: 'Preview',
  admin: 'Administration',
  organization: 'Organization',
  users: 'Users',
  roles: 'Roles',
  system: 'System',
};
