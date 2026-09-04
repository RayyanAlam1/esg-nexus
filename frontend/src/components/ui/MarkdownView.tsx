import ReactMarkdown from 'react-markdown';
import { cn } from '@/lib/utils';

export function MarkdownView({ content, className }: { content: string | null | undefined; className?: string }) {
  if (!content) return <p className="text-gray-400 italic">No content.</p>;
  return (
    <div className={cn('md', className)}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
