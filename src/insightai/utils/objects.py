from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class ArtifactRef(BaseModel):
    """Pointer to an evidence object in Neon Object Storage (no bytes)."""

    kind: str = Field(description="screenshot | video")
    bucket: str = Field(description="Neon bucket name")
    object_key: str = Field(description="Object key within the bucket")


class StepFindings(BaseModel):
    findings: Optional[str] = Field(None, description="Findings of the step")
    page_snapshot: Optional[str] = Field(None, description="Page snapshot of the step")
    error: Optional[str] = Field(None, description="Error of the step")
    network_messages: Optional[List[str]] = Field(
        None, description="Network messages of the step"
    )
    console_messages: Optional[List[str]] = Field(
        None, description="Console messages of the step"
    )
    artifacts: List[ArtifactRef] = Field(
        default_factory=list,
        description="Evidence object keys (screenshots, video). No binaries.",
    )



class Steps(BaseModel):
    step: Optional[int] = Field(None, description="Step number")
    action: Optional[str] = Field(None, description="Action to perform")
    completed: bool = Field(False, description="Whether the step is completed")
    findings: Optional[StepFindings] = Field(None, description="Findings of the step")


class Plan(BaseModel):
    goal: Optional[str] = Field(None, description="Goal of the plan")
    instructions: Optional[List[Steps]] = Field(None, description="Steps to follow")
    steps: Optional[int] = Field(None, description="Total number of steps")
    completed: bool = Field(False, description="Whether the plan is completed")

    @property
    def formatted_plan(self) -> str:
        return "\n".join(
            ["Goal: " + (self.goal or "") + "\n"]
            + [f"{step.step}. {step.action} \n" for step in (self.instructions or [])]
        )


class BrowserAssessment(BaseModel):
    """Evidence-based summary of the browser reproduction, before code analysis."""

    verdict: Literal["bug_confirmed", "not_reproduced", "inconclusive"] = Field(
        "inconclusive", description="Verdict supported by browser evidence only"
    )
    summary: str = Field("", description="Short summary of the observed browser behavior")
    key_observations: List[str] = Field(
        default_factory=list,
        description="Observed facts with step references; do not include code hypotheses",
    )


class SourceCandidate(BaseModel):
    """A likely source location, pinned to the tested commit."""

    path: str = Field(description="Repository-relative source path")
    start_line: int = Field(ge=1, description="First relevant line")
    end_line: int = Field(ge=1, description="Last relevant line")
    commit_sha: str = Field(description="Immutable Git commit inspected")
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(description="Why this location may cause the observed behavior")
    evidence_steps: List[int] = Field(
        default_factory=list,
        description="Browser step numbers that support this hypothesis",
    )


class SourceDiagnosis(BaseModel):
    """Read-only, evidence-linked code hypotheses; never a confirmed browser verdict."""

    status: Literal["available", "unavailable", "revision_mismatch", "insufficient_evidence"] = (
        "insufficient_evidence"
    )
    summary: str = ""
    candidates: List[SourceCandidate] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class Report(BaseModel):
    report: Optional[str] = Field(None, description="Report of the bug")
    verdict: Literal["bug_confirmed", "not_reproduced", "inconclusive"] = Field(
        "inconclusive",
        description="Whether the reported bug was confirmed by browser evidence",
    )
    run_status: Literal["completed", "failed", "cancelled", "unknown"] = Field(
        "unknown", description="Terminal lifecycle status for this run"
    )
    evidence_status: Literal["available", "partial", "unavailable", "unknown"] = Field(
        "unknown", description="Availability of persisted browser evidence"
    )
    source_diagnosis: Optional[SourceDiagnosis] = Field(
        None, description="Optional read-only source-code hypotheses"
    )

    @property
    def formatted_report(self) -> str:
        return self.report or "No report found"


class TimelineRef(BaseModel):
    """Optional object-storage pointer attached to a timeline event."""

    kind: Optional[str] = None
    bucket: Optional[str] = None
    object_key: Optional[str] = None


class TimelineEvent(BaseModel):
    """One ordered breadcrumb on the run timeline / action log."""

    id: str
    t: Optional[str] = Field(None, description="ISO-8601 timestamp")
    step: Optional[int] = None
    event_type: str
    tool: Optional[str] = None
    title: str
    detail: Optional[str] = None
    status: Optional[str] = "ok"
    ref: Optional[TimelineRef] = None
    source: Optional[str] = Field(
        None, description="run_events | run_artifacts | run_logs"
    )


class TimelineArtifact(BaseModel):
    id: str
    t: Optional[str] = None
    step: Optional[int] = None
    kind: str
    bucket: str
    object_key: str
    content_type: Optional[str] = None
    byte_size: Optional[int] = None


class TimelineLog(BaseModel):
    id: str
    t: Optional[str] = None
    step: Optional[int] = None
    kind: str
    source: Optional[str] = None
    message: str


class TimelineChapter(BaseModel):
    step: Optional[int] = None
    label: str
    events: List[TimelineEvent] = Field(default_factory=list)


class Timeline(BaseModel):
    """Merged timeline view for a QA run thread (events + artifacts + logs)."""

    thread_id: str
    events: List[TimelineEvent] = Field(default_factory=list)
    actions: List[TimelineEvent] = Field(default_factory=list)
    artifacts: List[TimelineArtifact] = Field(default_factory=list)
    logs: List[TimelineLog] = Field(default_factory=list)
    chapters: List[TimelineChapter] = Field(default_factory=list)
    error: Optional[str] = None

    @property
    def formatted_timeline(self) -> str:
        return "\n".join([chapter.label for chapter in self.chapters])
    @property
    def formatted_events(self) -> str:
        return "\n".join([event.title for event in self.events])
    @property
    def formatted_actions(self) -> str:
        return "\n".join([action.title for action in self.actions])
    @property
    def formatted_artifacts(self) -> str:
        return "\n".join([artifact.object_key for artifact in self.artifacts])
    @property
    def formatted_logs(self) -> str:
        return "\n".join([log.message for log in self.logs])



class Run(BaseModel):
    """Persisted summary of one QA run (graph inputs + outcomes + timeline)."""

    thread_id: str
    bug_description: str
    url: str
    expected_behavior: Optional[str] = None
    plan: Optional[Plan] = None
    step_findings: List[StepFindings] = Field(default_factory=list)
    timeline: Optional[Timeline] = None
    report: Optional[Report] = None
    error: Optional[str] = None
    completed: bool = False
    run_status: Literal["completed", "failed", "cancelled", "unknown"] = "unknown"
    evidence_status: Literal["available", "partial", "unavailable", "unknown"] = "unknown"
    id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> "Run":
        report = Report.model_validate(row.report) if row.report else None
        findings = [
            StepFindings.model_validate(item) for item in (row.step_findings or [])
        ]
        return cls(
            id=str(row.id) if getattr(row, "id", None) is not None else None,
            thread_id=row.thread_id,
            bug_description=row.bug_description,
            url=row.url,
            expected_behavior=row.expected_behavior,
            plan=Plan.model_validate(row.plan) if row.plan else None,
            step_findings=findings,
            timeline=Timeline.model_validate(row.timeline) if row.timeline else None,
            report=report,
            error=row.error,
            completed=bool(row.completed),
            run_status=(report.run_status if report is not None and report.run_status != "unknown"
                        else summarize_run_status(row.error, bool(row.completed))),
            evidence_status=(
                report.evidence_status
                if report is not None and report.evidence_status != "unknown"
                else summarize_evidence(findings)
            ),
            created_at=row.created_at.isoformat() if row.created_at else None,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )


def summarize_run_status(
    error: str | None, completed: bool,
) -> Literal["completed", "failed", "cancelled", "unknown"]:
    if error == "auth_cancelled":
        return "cancelled"
    if error:
        return "failed"
    return "completed" if completed else "unknown"


def normalize_report_verdict(
    verdict: str,
    run_status: Literal["completed", "failed", "cancelled", "unknown"],
    plan_completed: bool,
) -> Literal["bug_confirmed", "not_reproduced", "inconclusive"]:
    if run_status != "completed" or not plan_completed:
        return "inconclusive"
    if verdict == "bug_confirmed":
        return "bug_confirmed"
    if verdict == "not_reproduced":
        return "not_reproduced"
    return "inconclusive"


def summarize_evidence(
    findings: list[StepFindings],
    timeline: Timeline | None = None,
) -> Literal["available", "partial", "unavailable", "unknown"]:
    """Summarize durable artifact references across findings and persisted events."""
    if not findings:
        return "available" if timeline and timeline.artifacts else "unknown"

    artifact_steps = {
        index
        for index, finding in enumerate(findings, start=1)
        if finding.artifacts
    }
    if timeline:
        artifact_steps.update(
            artifact.step
            for artifact in timeline.artifacts
            if artifact.step is not None
        )
    if not artifact_steps and not (timeline and timeline.artifacts):
        return "unavailable"
    if len(artifact_steps) < len(findings):
        return "partial"
    return "available"
