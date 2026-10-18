import type { FC } from "react";

export interface BpmnDiagramProps {
  xml: string;
  activeStepId?: string | null;
  completedStepIds?: string[];
  firedRuleIds?: Record<string, string>;
  algorithmCards?: Record<string, unknown>;
  height?: number;
}

declare const BpmnDiagram: FC<BpmnDiagramProps>;
export default BpmnDiagram;
