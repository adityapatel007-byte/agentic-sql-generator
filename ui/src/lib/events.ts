// Mirrors backend/app/models/events.py. If you change one, change the other.

export type IterationEvent = {
  type: "iteration";
  iteration: number;
};

export type AssistantTextEvent = {
  type: "assistant";
  iteration: number;
  content: string | null;
  has_tool_calls: boolean;
};

export type ToolCallEvent = {
  type: "tool_call";
  iteration: number;
  tool_call_id: string;
  name: string;
  arguments: Record<string, unknown>;
};

export type ToolResultEvent = {
  type: "tool_result";
  iteration: number;
  tool_call_id: string;
  name: string;
  result: Record<string, unknown>;
};

export type FinalEvent = {
  type: "final";
  success: boolean;
  stop_reason: string;
  iterations_used: number;
  final_sql: string | null;
  final_columns: string[] | null;
  final_rows: unknown[][] | null;
  row_count: number | null;
  answer_text: string | null;
};

export type StreamEvent =
  | IterationEvent
  | AssistantTextEvent
  | ToolCallEvent
  | ToolResultEvent
  | FinalEvent;
