from pathlib import Path
from snow2lake_ai.orchestrator import run_migration
from snow2lake_ai.ai.provider import AIProvider, AIResponse, AIStatus

class NoAI(AIProvider):
    engine_name = "No AI (demo)"
    def status(self): return AIStatus.NOT_CONFIGURED
    def generate(self, prompt, context): return AIResponse(status=AIStatus.NOT_CONFIGURED, ai_engine=self.engine_name, confidence=0.0, warnings=["Demo run without Databricks AI"], manual_review=["Configure Databricks SQL AI for AI-assisted conversion."])

if __name__ == "__main__":
    root = Path(__file__).parent / "sample_snowflake_app"
    out = Path.cwd() / "snow2lake_output_demo"
    report = run_migration(str(root), str(out), NoAI(), application_name="sample_snowflake_app")
    print(f"Wrote migration output to: {out.resolve()}")
    print(report.to_dict())
