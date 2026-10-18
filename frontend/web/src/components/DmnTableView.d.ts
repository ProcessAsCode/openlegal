import type { FC } from "react";

export interface DmnTableViewProps {
  xml: string;
  firedRuleId?: string;
}

declare const DmnTableView: FC<DmnTableViewProps>;
export default DmnTableView;
