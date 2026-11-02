import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from insightai.auth.redact import redact_secrets, redact_text
from insightai.auth.session_capture import (
    default_profile_id,
    persist_open_browser_session,
    resume_confirmed,
)
from insightai.auth.storage_state import StorageStateError, normalize_origin
from insightai.auth.store import AuthStoreError
from insightai.evidence.session import (
    apply_auth_if_needed,
    mark_auth_applied,
    release,
    session_for,
    thread_id_from_config,
)
from insightai.evidence import context as evidence_context
from insightai.evidence.capture import capture_console
from insightai.mcp_clients.playwright import PlaywrightToolError
from insightai.utils.edges import AUTH_EXPIRED
from insightai.utils.model import llm
from insightai.utils.objects import (
    ArtifactRef,
    Plan,
    Report,
    StepFindings,
    normalize_report_verdict,
    summarize_evidence,
    summarize_run_status,
)
from insightai.utils.prompts import auth_note, execute_plan_prompt, plan_intruction_prompt, report_prompt
from insightai.utils.states import CreateGraphState, ExecutionState, InsightGraphState, ReportState




def _merge_artifacts(
    findings: StepFindings, artifacts: list[dict]
) -> StepFindings:
    if not artifacts:
        return findings
    existing = list(findings.artifacts or [])
    seen = {(a.kind, a.bucket, a.object_key) for a in existing}
    for item in artifacts:
        key = (item.get("kind"), item.get("bucket"), item.get("object_key"))
        if None in key or key in seen:
            continue
        existing.append(ArtifactRef(**item))
        seen.add(key)
    return findings.model_copy(update={"artifacts": existing})


def _redact_findings(findings: StepFindings) -> StepFindings:
    updates: dict[str, object] = {}
    for field in ("findings", "page_snapshot", "error"):
        value = getattr(findings, field)
        if isinstance(value, str):
            updates[field] = redact_text(value)
    if findings.console_messages:
        updates["console_messages"] = [
            redact_text(item) if isinstance(item, str) else item
            for item in findings.console_messages
        ]
    if not updates:
        return findings
    return findings.model_copy(update=updates)


def _stopped(message: str, code: str) -> InsightGraphState:
    return {
        "step_findings": [StepFindings(findings="", error=message)],
        "completed": True,
        "error": code,
    }


def _needs_login(message: str) -> InsightGraphState:
    """Pause the plan step so wait_for_login can interrupt for Continue."""
    return {
        "step_findings": [StepFindings(findings="", error=message)],
        "completed": False,
        "error": AUTH_EXPIRED,
    }


_SENSITIVE_URL_PARAMETER = re.compile(
    r"(?:token|secret|password|passwd|auth|credential|session|cookie|signature|^sig$|^code$|^state$|^key$|^jwt$)",
    re.IGNORECASE,
)


def _safe_resume_url(value: str | None, fallback: str) -> str:
    """Keep a navigable URL while removing credentials and auth query values."""
    candidate = (value or "").strip() or fallback
    try:
        parts = urlsplit(candidate)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("URL must be HTTP(S)")
        host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        netloc = f"{host}:{parts.port}" if parts.port is not None else host
        query = urlencode(
            [
                (key, item)
                for key, item in parse_qsl(parts.query, keep_blank_values=True)
                if not _SENSITIVE_URL_PARAMETER.search(key)
            ]
        )
        return urlunsplit((parts.scheme, netloc, parts.path, query, ""))
    except (TypeError, ValueError):
        if candidate != fallback:
            return _safe_resume_url(fallback, fallback)
        return fallback


async def _current_page_url(playwright, fallback: str) -> str:
    """Read the active page URL through Playwright MCP without exposing secrets."""
    try:
        result = await playwright.call_mcp(
            "browser_evaluate", {"function": "() => window.location.href"}
        )
        content = getattr(result, "content", None) or []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                # MCP evaluate results may wrap the returned string as JSON.
                try:
                    value = json.loads(text)
                except json.JSONDecodeError:
                    value = text.strip().strip('"')
                if isinstance(value, str):
                    return _safe_resume_url(value, fallback)
    except Exception:
        pass
    return _safe_resume_url(fallback, fallback)

def create_plan(state: CreateGraphState) -> ExecutionState:
    url = state["url"]
    bug = state["bug_description"]

    system_message = plan_intruction_prompt.format(
        url=url,
        bug=bug,
        auth_note=auth_note(state.get("auth_profile_id"), stage="plan"),
    )

    plan_llm = llm.with_structured_output(Plan)

    plan = plan_llm.invoke(
        [SystemMessage(content=system_message)]
        + [HumanMessage(content="Please give me a plan to find this bug")]
    )

    return {"plan": plan, "current_step": 1, "completed": False, "step_findings": []}

async def execute_plan(
    state: ExecutionState, config: RunnableConfig
) -> [ExecutionState, ReportState]:
    """Run one plan step via Playwright MCP tools."""

    thread_id = thread_id_from_config(config)
    plan = state.get("plan")
    max_turns = state.get("max_tools_turns") or 30
    tools_turns = state.get("tools_turns") or 0
    if plan is None:
        await release(thread_id, finished=True)
        return {
            "step_findings": [
                StepFindings(findings="", error="No plan provided. Run create_plan first.")
            ],
            "completed": True,
            "error": "missing_plan",
        }

    if tools_turns >= max_turns:
        plan.completed = True
        await release(thread_id, finished=True)
        return {
            "plan": plan,
            "step_findings": [StepFindings(findings="", error="Max tools turns reached")],
            "completed": True,
            "error": "max_tools_turns_reached",
        }

    url = state["url"]
    bug = state["bug_description"]
    current_step = state["current_step"]
    step = plan.instructions[current_step - 1]

    if step.completed:
        return {
            "step_findings": [step.findings] if step.findings else [],
            "completed": True,
            "error": None,
            "tools_turns": 0,
        }

    profile_id = (state.get("auth_profile_id") or "").strip()
    system_prompt = execute_plan_prompt.format(
        url=url,
        bug=bug,
        plan=plan.formatted_plan,
        current_step=current_step,
        auth_note=auth_note(profile_id, stage="execute"),
    )

    evidence_context.begin_step(thread_id, current_step)
    try:
        from insightai.evidence.timeline import EVENT_STEP_START, emit_event

        emit_event(
            thread_id,
            EVENT_STEP_START,
            f"Step {current_step}: {step.action}",
            step=current_step,
            detail=step.action,
        )
    except Exception:
        pass
    try:
        playwright = await session_for(thread_id)
        if profile_id:
            await apply_auth_if_needed(thread_id, profile_id, url)
        agent = create_agent(
            llm,
            playwright.tools,
            system_prompt=system_prompt,
            response_format=StepFindings,
        )
        result = await agent.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            f"Execute only step {current_step}: {step.action}. "
                            "Use browser tools as needed, then return findings."
                        )
                    )
                ]
            },
            config={"recursion_limit": max_turns * 2},
        )
    except ConnectionError as exc:
        evidence_context.clear_step()
        await release(thread_id, finished=True)
        return {
            "step_findings": [StepFindings(findings="", error=str(exc))],
            "completed": True,
            "error": "mcp_unreachable",
        }
    except AuthStoreError as exc:
        evidence_context.clear_step()
        if exc.code == AUTH_EXPIRED:
            return _needs_login(str(exc))
        await release(thread_id, finished=True)
        return _stopped(str(exc), exc.code)
    except PlaywrightToolError as exc:
        evidence_context.clear_step()
        await release(thread_id, finished=True)
        return _stopped(str(exc), exc.code)

    findings = result.get("structured_response")
    if findings is None:
        content = result.get("messages", [])[-1].content
        if isinstance(content, str):
            try:
                payload = json.loads(content)
                findings = StepFindings(**payload)
            except (json.JSONDecodeError, TypeError, ValueError):
                findings = StepFindings(
                    findings=str(content), error="missing_structured_response"
                )
        else:
            findings = StepFindings(
                findings=str(content), error="missing_structured_response"
            )

    # End-of-step console pull (best-effort); merge harness artifacts.
    try:
        console_summary = await capture_console(playwright)
        if console_summary and not findings.console_messages:
            findings = findings.model_copy(
                update={"console_messages": console_summary.splitlines()[:30]}
            )
    except Exception:
        pass

    harness_artifacts = evidence_context.take_artifacts()
    evidence_context.clear_step()
    if (findings.error or "").strip() == AUTH_EXPIRED:
        login_url = await _current_page_url(playwright, url)
        harness_artifacts = [
            a for a in harness_artifacts if a.get("kind") != "screenshot"
        ]
    # Artifacts returned by the model are untrusted; only the evidence harness
    # can establish durable object-storage references.
    findings = findings.model_copy(update={"artifacts": []})
    findings = _merge_artifacts(findings, harness_artifacts)
    findings = _redact_findings(findings)
    try:
        from insightai.evidence.timeline import EVENT_STEP_END, emit_event

        emit_event(
            thread_id,
            EVENT_STEP_END,
            f"Step {current_step} finished",
            step=current_step,
            detail=(findings.error or findings.findings or "")[:800] or None,
            status="error" if findings.error else "ok",
        )
    except Exception:
        pass
    if (findings.error or "").strip() == AUTH_EXPIRED:
        try:
            from insightai.evidence.timeline import EVENT_AUTH_LOGIN, emit_event

            emit_event(
                thread_id,
                EVENT_AUTH_LOGIN,
                "Login wall — waiting for human Continue",
                step=current_step,
                status="paused",
            )
        except Exception:
            pass
        return {
            "step_findings": [findings],
            "plan": plan,
            "completed": False,
            "error": AUTH_EXPIRED,
            "login_url": login_url,
            "tools_turns": tools_turns + 1,
        }

    plan.instructions[current_step - 1].completed = True
    plan.instructions[current_step - 1].findings = findings
    plan.completed = all(s.completed for s in plan.instructions)

    updates: InsightGraphState = {
        "step_findings": [findings],
        "plan": plan,
        "completed": plan.completed,
        "error": findings.error,
        "tools_turns": tools_turns + 1,
    }
    if not plan.completed and not findings.error:
        updates["current_step"] = current_step + 1

    # Keep the client open across steps and login walls; stop on plan end or fatal error.
    if plan.completed or findings.error:
        video_artifact = await release(thread_id, finished=True)
        if video_artifact:
            findings = _merge_artifacts(findings, [video_artifact])
            plan.instructions[current_step - 1].findings = findings
            updates["step_findings"] = [findings]
            updates["plan"] = plan
    return updates


async def wait_for_login(
    state: InsightGraphState, config: RunnableConfig
) -> InsightGraphState:
    """Pause for a frontend Continue after a login wall, then save the browser session.

    The password is typed in the headed Playwright window only. Resume payload must
    not include credentials — Studio Continue with an empty value is enough.
    """
    thread_id = thread_id_from_config(config)
    url = state["url"]
    login_url = _safe_resume_url(state.get("login_url"), url)
    try:
        origin = normalize_origin(url)
    except StorageStateError as exc:
        await release(thread_id, finished=True)
        return _stopped(str(exc), exc.code)

    profile_id = (state.get("auth_profile_id") or "").strip() or default_profile_id(url)

    # A restarted process has no held browser session. Recreate it and open the
    # checkpointed login page before interrupting, so the user can sign in.
    try:
        playwright, created = await session_for(thread_id, with_status=True)
        if created:
            await playwright.call_mcp("browser_navigate", {"url": login_url})
    except ConnectionError as exc:
        await release(thread_id, finished=True)
        return _stopped(str(exc), "mcp_unreachable")
    except PlaywrightToolError as exc:
        await release(thread_id, finished=True)
        return _stopped(str(exc), exc.code)

    resume = interrupt(
        {
            "type": "auth_login",
            "message": (
                "A login page appeared. Sign in in the headed Playwright browser "
                f"(use {login_url} if the window is blank), then click Continue. "
                "Do not type the password into this chat or the resume payload."
            ),
            "login_url": login_url,
            "origin": origin,
            "auth_profile_id": profile_id,
        }
    )
    if not resume_confirmed(resume):
        await release(thread_id, finished=True)
        return _stopped("Sign-in was cancelled", "auth_cancelled")

    try:
        await persist_open_browser_session(
            playwright,
            profile_id=profile_id,
            page_url=url,
        )
        mark_auth_applied(thread_id, profile_id)
        try:
            from insightai.evidence.timeline import EVENT_AUTH_SAVED, emit_event

            emit_event(
                thread_id,
                EVENT_AUTH_SAVED,
                f"Saved auth profile {profile_id}",
                detail=profile_id,
            )
        except Exception:
            pass
    except ConnectionError as exc:
        await release(thread_id, finished=True)
        return _stopped(str(exc), "mcp_unreachable")
    except AuthStoreError as exc:
        await release(thread_id, finished=True)
        return _stopped(str(exc), exc.code)
    except PlaywrightToolError as exc:
        await release(thread_id, finished=True)
        return _stopped(str(exc), exc.code)

    return {
        "auth_profile_id": profile_id,
        "error": None,
        "completed": False,
    }


def finalize_report(
    state: ReportState, config: RunnableConfig
) -> InsightGraphState:
    report_llm = llm.with_structured_output(Report)
    findings = state.get("step_findings") or []
    safe_findings = [
        redact_secrets(item.model_dump()) if hasattr(item, "model_dump") else redact_secrets(item)
        for item in findings
    ]
    plan = state.get("plan")
    plan_completed = bool(plan and plan.completed)
    timeline = state.get("timeline")
    if timeline is None:
        try:
            from insightai.evidence.timeline import assemble_timeline

            timeline = assemble_timeline(thread_id_from_config(config))
        except Exception:
            timeline = None
    report = report_llm.invoke(
        report_prompt.format(
            step_findings=safe_findings,
            expected_behavior=state.get("expected_behavior"),
            url=state.get("url"),
            bug=state.get("bug_description"),
            timeline=timeline,
            plan_completed=plan_completed,
        )
    )
    run_status = summarize_run_status(state.get("error"), bool(state.get("completed")))
    evidence_status = summarize_evidence(findings, timeline)
    report = report.model_copy(
        update={
            "verdict": normalize_report_verdict(
                report.verdict, run_status, plan_completed
            ),
            "run_status": run_status,
            "evidence_status": evidence_status,
        }
    )

    try:
        from insightai.evidence.runs import save_run_from_state

        save_run_from_state(
            {**dict(state), "timeline": timeline},
            config=config,
            report=report,
            completed=True,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to persist run summary",
            exc_info=True,
        )

    return {
        "report": report,
        "run_status": run_status,
        "evidence_status": evidence_status,
    }

