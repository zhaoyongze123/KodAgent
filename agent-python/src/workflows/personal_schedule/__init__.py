from .contracts import PersonalScheduleWorkflowInput, PersonalScheduleWorkflowOutcome, PersonalScheduleWorkflowStatus
__all__ = ["PersonalScheduleWorkflowInput", "PersonalScheduleWorkflowOutcome", "PersonalScheduleWorkflowStatus", "run_personal_schedule_workflow"]


def __getattr__(name):
    if name == "run_personal_schedule_workflow":
        from .graph import run_personal_schedule_workflow
        return run_personal_schedule_workflow
    raise AttributeError(name)
