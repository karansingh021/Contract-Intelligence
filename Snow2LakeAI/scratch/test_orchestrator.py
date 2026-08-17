from snow2lake_ai.orchestrator import _run_local

input_dir = r"d:\Snow2LakeAI\output\my_snowflake_app\_source_from_stage"
out_dir = r"d:\Snow2LakeAI\output\test_run"

print(f"Running migration on local files from: {input_dir}")
report = _run_local(input_dir, out_dir, None, "my_snowflake_app")

print(f"\nMigration completed! Total objects found: {len(report.objects)}\n")

for obj in report.objects:
    status = "🔴" if "HIGH_COMPLEXITY" in obj.migration_type.value else ("🟠" if "REDESIGN" in obj.migration_type.value else "🟢")
    print(f"{status} {obj.object_name:<30} | {obj.source_type.value:<16} -> {obj.target_type:<24} | {obj.migration_type.value}")

print("\nValidating results for RAW_SQL leakage...")
leaked = [o for o in report.objects if "RAW_SQL" in o.object_name]
if leaked:
    print(f"❌ FAILED: Found {len(leaked)} RAW_SQL objects that leaked through:")
    for o in leaked:
        print(f"  - {o.object_name}")
else:
    print("✅ SUCCESS: No RAW_SQL objects found in the final report! The filter worked perfectly.")
