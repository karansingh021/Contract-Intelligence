#!/usr/bin/env python3
"""
Demo: Snowflake Native App to Databricks App Migration

This script demonstrates how to use the migrator with the example app.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app_analyzer import SnowflakeAppAnalyzer
from app_converter import DatabricksAppConverter

def main():
    print("\n" + "="*70)
    print(" SNOWFLAKE → DATABRICKS APP MIGRATION DEMO")
    print("="*70)
    
    # Path to example app
    example_app_path = Path(__file__).parent / "example_snowflake_app"
    output_path = Path(__file__).parent / "demo_output"
    
    print(f"\n📁 Source: {example_app_path}")
    print(f"📂 Output: {output_path}")
    
    # ========================================================================
    # STEP 1: ANALYZE
    # ========================================================================
    print("\n" + "="*70)
    print(" STEP 1: ANALYZING SNOWFLAKE APP")
    print("="*70)
    
    analyzer = SnowflakeAppAnalyzer()
    analysis = analyzer.analyze(str(example_app_path))
    
    # Print detailed analysis
    analyzer.print_summary()
    
    # ========================================================================
    # STEP 2: CONVERT
    # ========================================================================
    print("\n" + "="*70)
    print(" STEP 2: CONVERTING TO DATABRICKS APP")
    print("="*70)
    
    converter = DatabricksAppConverter()
    databricks_app = converter.convert(analysis, str(output_path))
    
    print(f"\n✅ Conversion complete!")
    print(f"\n📊 Migration Summary:")
    print(f"   App Name:         {databricks_app.name}")
    print(f"   Output Path:      {databricks_app.app_path}")
    print(f"   app.yaml:         {databricks_app.app_yaml_path}")
    print(f"   app.py:           {databricks_app.app_py_path}")
    
    print(f"\n📝 Migration Notes:")
    for note in databricks_app.migration_notes:
        print(f"   • {note}")
    
    # ========================================================================
    # STEP 3: REVIEW OUTPUTS
    # ========================================================================
    print("\n" + "="*70)
    print(" STEP 3: GENERATED FILES")
    print("="*70)
    
    print("\n📄 Key Files:")
    
    # Show app.yaml content
    app_yaml_path = Path(databricks_app.app_yaml_path)
    if app_yaml_path.exists():
        print(f"\n   ├── app.yaml:")
        with open(app_yaml_path, 'r') as f:
            for i, line in enumerate(f, 1):
                print(f"   │  {line.rstrip()}")
                if i >= 10:  # Show first 10 lines
                    print("   │  ...")
                    break
    
    # Show directory structure
    print(f"\n   └── Directory structure:")
    output_dir = Path(databricks_app.app_path)
    for item in sorted(output_dir.rglob('*')):
        if item.is_file():
            rel_path = item.relative_to(output_dir)
            indent = "      " + "  " * (len(rel_path.parts) - 1)
            print(f"{indent}└── {item.name}")
    
    # ========================================================================
    # NEXT STEPS
    # ========================================================================
    print("\n" + "="*70)
    print(" 🚀 NEXT STEPS")
    print("="*70)
    
    print("""
1. Review the generated Databricks App:
   cd demo_output
   cat README.md

2. Install dependencies:
   pip install -r requirements.txt

3. Test locally (for Streamlit apps):
   streamlit run src/streamlit_app.py

4. Set up Unity Catalog:
   databricks sql execute -f databricks/unity_catalog_setup.sql

5. Deploy to Databricks:
   databricks apps deploy

6. Review and adjust:
   - Check src/ for any manual conversion needed
   - Review databricks/*.sql for SQL syntax adjustments
   - Test thoroughly before production use
    """)
    
    print("="*70)
    print("✨ Demo complete! Check the demo_output/ directory.")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
