import asyncio
import os
from insightai import InsightAgent, NeedsLogin

AUTH_PROFILE = "lumenshop"


async def main():
    agent = InsightAgent()
    state = {
        "bug_description": "redeeming 100 points deducts 150",
        "url": "http://localhost:5500/rewards.html",
    }
    if (
        os.environ.get("AUTH_DATA_KEY", "").strip()
        and (
            os.environ.get("AUTH_DATABASE_URL", "").strip()
            or os.environ.get("DATABASE_URL", "").strip()
        )
    ):
        # Match `insightai.auth.capture save` so an available session is restored.
        state["auth_profile_id"] = AUTH_PROFILE

    result = await agent.arun(state=state)
    while isinstance(result, NeedsLogin):
        print("Needs login")
        logged_in = await asyncio.to_thread(input, "Logged in? (y/n): ")
        if logged_in.strip().lower() == "y":
            result = await agent.acontinue(result.thread_id)
            if not isinstance(result, NeedsLogin):
                persisted = result.state.get("auth_session_persisted")
                if persisted is True:
                    print(f"Login session saved as profile: {AUTH_PROFILE}")
                elif persisted is False:
                    print(
                        "Login is active for this run only (browser kept open). "
                        "To save it for later runs: start MCP via "
                        "scripts/start-playwright-mcp.bat (--caps=storage), and set "
                        "AUTH_DATA_KEY plus AUTH_DATABASE_URL or DATABASE_URL in .env."
                    )
        else:
            print("Login failed")
            return

    if result.report:
        print("Report: ", result.report.formatted_report + "\n")
    else:
        print("Run stopped: ", result.error or "No report was produced")

if __name__ == "__main__":
    asyncio.run(main())
