import { ApprovalCard } from "./ApprovalCard";
import { ApprovalInboxCard } from "./ApprovalInboxCard";
import { ApprovalWorkflowCard } from "./ApprovalWorkflowCard";
import { ApprovalBatchCard } from "./ApprovalBatchCard";
import { ApprovalInsightsCard } from "./ApprovalInsightsCard";
import { CalendarCard } from "./CalendarCard";
import { PendingApprovalsCard } from "./PendingApprovalsCard";
import { PartyFileCard } from "./PartyFileCard";
import { PartyFileKnowledgeCard } from "./PartyFileKnowledgeCard";
import { PartyFileCompareCard } from "./PartyFileCompareCard";
import { PartyFileComplianceCard } from "./PartyFileComplianceCard";
import { BusinessReportCard } from "./BusinessReportCard";
import { ProjectCard } from "./ProjectCard";
import type { AgentCard } from "@/types/agent-block";

export function CardRenderer({
  card,
  interrupt,
}: {
  card: AgentCard;
  interrupt?: unknown;
}) {
  switch (card.type) {
    case "approval":
      return (
        <ApprovalCard
          payload={card.payload}
          interrupt={interrupt}
        />
      );
    case "approval_workflow":
      return <ApprovalWorkflowCard payload={card.payload} />;
    case "calendar":
      return <CalendarCard payload={card.payload} />;
    case "todo":
      return <PendingApprovalsCard payload={card.payload} />;
    case "approval_inbox":
      return <ApprovalInboxCard payload={card.payload} />;
    case "approval_batch_preview":
      return <ApprovalBatchCard payload={card.payload} />;
    case "approval_batch_result":
      return <ApprovalBatchCard payload={card.payload} result />;
    case "approval_insights":
      return <ApprovalInsightsCard payload={card.payload} />;
    case "party_file":
      return <PartyFileCard payload={card.payload} />;
    case "party_file_knowledge":
      return <PartyFileKnowledgeCard payload={card.payload} />;
    case "party_file_compare":
      return <PartyFileCompareCard payload={card.payload} />;
    case "party_file_compliance":
      return <PartyFileComplianceCard payload={card.payload} />;
    case "business_report":
      return <BusinessReportCard payload={card.payload} />;
    case "project_list":
    case "project_snapshot":
    case "project_analysis":
    case "project_tasks":
    case "project_activity":
    case "project_documents":
    case "project_knowledge":
    case "project_report":
      return <ProjectCard kind={card.type} payload={card.payload} />;
    default:
      return null;
  }
}
