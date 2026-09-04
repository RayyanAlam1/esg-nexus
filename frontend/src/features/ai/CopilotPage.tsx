import { useExperts } from '@/api/agents';
import { Card, PageHeader } from '@/components/ui';
import { CopilotChat } from './CopilotChat';

export function CopilotPage() {
  const experts = useExperts();
  return (
    <div className="space-y-4 h-full flex flex-col">
      <PageHeader title="ESG Copilot" description="Mixture-of-experts assistant over governed metrics, evidence and approved knowledge. Every answer carries sources, metrics used, confidence, guardrail and governance outcomes." />
      <div className="grid gap-3 lg:grid-cols-[1fr_300px] flex-1 min-h-0">
        <Card bodyClassName="p-3 h-[calc(100vh-220px)] min-h-[480px]">
          <CopilotChat />
        </Card>
        <Card title="Experts" bodyClassName="p-0">
          <ul>
            {(experts.data ?? []).map((e) => (
              <li key={e.code} className="px-3 py-2 border-b border-gray-100 text-xs">
                <div className="font-medium text-navy">{e.name}</div>
                <div className="text-gray-600">{e.description}</div>
                <div className="text-gray-400 font-mono mt-0.5">{e.agent}</div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
