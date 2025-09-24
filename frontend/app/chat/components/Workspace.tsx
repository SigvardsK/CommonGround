import React, { useState } from 'react';
import { observer } from 'mobx-react-lite';
import { Button } from '@/components/ui/button';
import { Info, Workflow, LayoutDashboard } from "lucide-react";
import { Node, NodeMouseHandler } from 'reactflow';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { sessionStore } from '@/app/stores/sessionStore';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ConversationDetailView } from './details/ConversationDetailView';
import { FlowView } from './FlowView';
import { KanbanView } from './KanbanView';
import { TimelineView } from './TimelineView';

interface WorkspaceProps {
  runId: string;
  selectedNode: Node | null;
  isNodeDetailOpen: boolean;
  onNodeClick: NodeMouseHandler;
  onCloseNodeDetail: () => void;
}

const TokenUsageDisplay = observer(() => {
    const stats = sessionStore.tokenUsageStats;
    if (!stats) return null;

    const totalCalls = stats.total_successful_calls + stats.total_failed_calls;

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground cursor-help">
                        <Info size={14} />
                        <span>Token Usage</span>
                    </div>
                </TooltipTrigger>
                <TooltipContent>
                    <div className="p-2 text-sm space-y-1">
                        <p><strong>Total Token Count:</strong> {stats.total_prompt_tokens + stats.total_completion_tokens}</p>
                        <p className="pl-2">Up: {stats.total_prompt_tokens} / Down: {stats.total_completion_tokens}</p>
                        <p><strong>Used Context Window:</strong> {stats.max_context_window}</p>
                        <p><strong>Total LLM Calls:</strong> {totalCalls} ({stats.total_successful_calls} success, {stats.total_failed_calls} fail)</p>
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
});

export const Workspace = observer((props: WorkspaceProps) => {
  const [activeTab, setActiveTab] = useState<'flow' | 'kanban'>('flow');
  const [groupMode, setGroupMode] = useState<'task' | 'agent'>('task');

  // The useEffect hook for managing subscriptions has been removed from here
  // and its logic is now centralized in `sessionStore.ts` to prevent race conditions.

  return (
    <div className="flex-1 flex flex-col bg-background h-[calc(100vh-46px)] min-w-0">
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className={`flex items-center gap-2 ${
              activeTab === 'flow' ? 'bg-muted shadow-sm' : ''
            }`}
            onClick={() => setActiveTab('flow')}
          >
            <Workflow size={24} />
            <span className="text-base">Flow</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className={`flex items-center gap-2 ${
              activeTab === 'kanban' ? 'bg-muted shadow-sm' : ''
            }`}
            onClick={() => setActiveTab('kanban')}
          >
            <LayoutDashboard size={24} />
            <span className="text-base">Kanban & Timeline</span>
          </Button>
        </div>
        
        <div className="flex items-center gap-4">
          {activeTab === 'kanban' && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Group by:</span>
              <Select
                value={groupMode}
                onValueChange={(value: 'task' | 'agent') => setGroupMode(value)}
              >
                <SelectTrigger className="w-14 h-auto p-0 border-none bg-transparent text-sm text-muted-foreground hover:text-foreground focus:ring-0 shadow-none">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="task">Status</SelectItem>
                  <SelectItem value="agent">Agent</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          <TokenUsageDisplay />
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative">
        {activeTab === 'flow' && (
          <div className="relative h-full w-full px-3 pb-3 overflow-hidden">
            <FlowView onNodeClick={props.onNodeClick} />
          </div>
        )}
        {activeTab === 'kanban' && (
          <div className="relative h-full w-full px-3 pb-3 overflow-hidden">
            <div className="w-full h-full bg-card rounded-lg border p-4 pt-8 overflow-y-auto">
              <div className="min-h-[400px]">
                <KanbanView runId={props.runId} groupMode={groupMode} />
              </div>
              <div className="border-t pt-6 mt-8">
                <h3 className="text-lg font-semibold mb-4">Execution Timeline</h3>
                <TimelineView />
              </div>
            </div>
          </div>
        )}
        
        <div
          className={`absolute top-0 right-0 h-full w-[720px] bg-card border-l border shadow-lg transform transition-transform duration-300 ease-in-out z-20 ${
            props.isNodeDetailOpen ? 'translate-x-0' : 'translate-x-full'
          }`}
        >
          {props.isNodeDetailOpen && (
            <ConversationDetailView
              turns={sessionStore.activityStreamTurns}
              highlightedNodeId={props.selectedNode?.data.turn_id || null}
              onClose={props.onCloseNodeDetail}
              onNodeIdClick={props.onNodeClick}
            />
          )}
        </div>
      </div>
    </div>
  );
});
