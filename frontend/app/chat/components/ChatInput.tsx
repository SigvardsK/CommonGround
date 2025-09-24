import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface ChatInputProps {
  currentInput: string;
  onInputChange: (value: string) => void;
  onKeyPress: (e: React.KeyboardEvent) => void;
  onSendMessage: () => void;
  isStreaming: boolean;
  isLoading: boolean;
  onStopExecution: () => void;
}

export function ChatInput({
  currentInput,
  onInputChange,
  onKeyPress,
  onSendMessage,
  isStreaming,
  isLoading,
  onStopExecution,
}: ChatInputProps) {
  return (
    <div className="p-3">
      <div className="flex gap-2 bg-card rounded-lg border overflow-hidden p-2 focus-within:ring-1 focus-within:ring-ring transition-colors">
        <Input
          value={currentInput}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyPress={onKeyPress}
          placeholder="Enter message..."
          disabled={isStreaming || isLoading}
          className="flex-1 border-0 focus-visible:ring-0 focus-visible:ring-offset-0 shadow-none px-2"
        />
        {isStreaming ? (
          <Button
            variant="default"
            size="icon"
            className="rounded-full !px-2 !py-1"
            onClick={onStopExecution}
          >
            <div className="w-3 h-3 bg-primary-foreground" />
          </Button>
        ) : (
          <Button 
            onClick={onSendMessage}
            disabled={!currentInput.trim() || isLoading}
          >
            Send
          </Button>
        )}
      </div>
    </div>
  );
}
