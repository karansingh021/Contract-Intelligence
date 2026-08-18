#!/usr/bin/env python3
"""
Snowflake Native App to Databricks App Migrator - CLI

Command-line tool for migrating Snowflake Native Applications to Databricks Apps.

Usage:
    python app_migrator_cli.py --input /path/to/snowflake/app --output ./databricks_app
    
    # With Snowflake stage download:
    python app_migrator_cli.py \
        --snowflake-stage @APP_STAGE \
        --snowflake-config config.json \
        --output ./databricks_app
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app_analyzer import SnowflakeAppAnalyzer
from app_converter import DatabricksAppConverter


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"\u274c Failed to load config: {e}")
        sys.exit(1)


def download_from_snowflake_stage(stage: str, config: dict, local_dir: str):
    """Download app from Snowflake stage"""
    print(f"\n📥 Downloading from Snowflake stage: {stage}")
    
    try:
        import snowflake.connector
        
        conn = snowflake.connector.connect(
            account=config['snowflake']['account'],
            user=config['snowflake']['user'],
            password=config.get('snowflake', {}).get('password'),
            warehouse=config['snowflake']['warehouse'],
            database=config['snowflake']['database'],
            schema=config['snowflake']['schema']
        )
        
        cursor = conn.cursor()
        
        # List files in stage
        print(f"  Listing files in {stage}...")
        cursor.execute(f"LIST {stage}")
        files = cursor.fetchall()
        print(f"  Found {len(files)} files")
        
        # Download files
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        print(f"  Downloading to {local_dir}...")
        cursor.execute(f"GET {stage} file://{Path(local_dir).absolute()}/")
        
        cursor.close()
        conn.close()
        
        print(f"  ✅ Download complete")
        return local_dir
        
    except ImportError:
        print("\u274c snowflake-connector-python not installed")
        print("  Install with: pip install snowflake-connector-python")
        sys.exit(1)
    except Exception as e:
        print(f"\u274c Failed to download from Snowflake: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Snowflake Native App to Databricks App",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate from local directory
  python app_migrator_cli.py --input ./my_snowflake_app --output ./databricks_app
  
  # Download from Snowflake stage first
  python app_migrator_cli.py \
    --snowflake-stage @APP_PACKAGE_STAGE \
    --snowflake-config config.json \
    --output ./databricks_app
  
  # Just analyze without converting
  python app_migrator_cli.py --input ./my_snowflake_app --analyze-only
        """
    )
    
    parser.add_argument(
        "--input",
        help="Path to Snowflake Native App directory (local)"
    )
    parser.add_argument(
        "--snowflake-stage",
        help="Snowflake stage to download from (e.g., @APP_STAGE)"
    )
    parser.add_argument(
        "--snowflake-config",
        help="JSON config file with Snowflake connection details"
    )
    parser.add_argument(
        "--output",
        default="./databricks_app",
        help="Output directory for Databricks App (default: ./databricks_app)"
    )
    parser.add_argument(
        "--app-name",
        help="Override app name (defaults to directory name)"
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Only analyze, don't convert"
    )
    parser.add_argument(
        "--report",
        help="Output path for JSON analysis report"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.input and not args.snowflake_stage:
        parser.error("Either --input or --snowflake-stage must be provided")
    
    if args.snowflake_stage and not args.snowflake_config:
        parser.error("--snowflake-config required when using --snowflake-stage")
    
    print("\n" + "="*70)
    print(" SNOWFLAKE NATIVE APP → DATABRICKS APP MIGRATOR")
    print("="*70)
    
    # Handle Snowflake stage download
    input_dir = args.input
    if args.snowflake_stage:
        config = load_config(args.snowflake_config)
        temp_dir = Path(args.output).parent / "_snowflake_download"
        input_dir = download_from_snowflake_stage(
            args.snowflake_stage,
            config,
            str(temp_dir)
        )
    
    if not input_dir or not Path(input_dir).exists():
        print(f"\u274c Input directory does not exist: {input_dir}")
        sys.exit(1)
    
    # Step 1: Analyze
    print(f"\n🔍 STEP 1: ANALYZING SNOWFLAKE APP")
    print(f"  Source: {input_dir}")
    
    analyzer = SnowflakeAppAnalyzer()
    try:
        analysis = analyzer.analyze(input_dir)
    except Exception as e:
        print(f"\u274c Analysis failed: {e}")
        sys.exit(1)
    
    # Print analysis summary
    analyzer.print_summary()
    
    # Save analysis report if requested
    if args.report:
        report_data = {
            "app_name": analysis.app_name,
            "migration_complexity": analysis.migration_complexity,
            "components": len(analysis.components),
            "python_files": len(analysis.python_files),
            "sql_files": len(analysis.sql_files),
            "has_streamlit": analysis.has_streamlit,
            "has_api": analysis.has_api,
            "has_stored_procedures": analysis.has_stored_procedures,
            "has_udfs": analysis.has_udfs,
            "snowpark_usage": analysis.snowpark_usage,
            "warnings": analysis.warnings,
            "recommendations": analysis.recommendations
        }
        
        try:
            with open(args.report, 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"\n✅ Analysis report saved to: {args.report}")
        except Exception as e:
            print(f"\u26a0️  Failed to save report: {e}")
    
    # Exit if analyze-only
    if args.analyze_only:
        print("\n✓ Analysis complete (--analyze-only specified)")
        return 0
    
    # Step 2: Convert
    print(f"\n♻️  STEP 2: CONVERTING TO DATABRICKS APP")
    print(f"  Output: {args.output}")
    
    converter = DatabricksAppConverter()
    try:
        databricks_app = converter.convert(analysis, args.output)
    except Exception as e:
        print(f"\u274c Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Print conversion summary
    print("\n" + "="*70)
    print(" MIGRATION COMPLETE")
    print("="*70)
    print(f"\n✅ Databricks App created at: {databricks_app.app_path}")
    print(f"\n📝 Migration Notes:")
    for note in databricks_app.migration_notes:
        print(f"   • {note}")
    
    print("\n🚀 Next Steps:")
    print("   1. Review the generated files, especially:")
    print(f"      - {Path(databricks_app.app_yaml_path).name}")
    print(f"      - {Path(databricks_app.app_py_path).name}")
    print("      - databricks/unity_catalog_setup.sql")
    print("\n   2. Install dependencies:")
    print(f"      cd {args.output} && pip install -r requirements.txt")
    print("\n   3. Set up Unity Catalog:")
    print("      databricks sql execute -f databricks/unity_catalog_setup.sql")
    print("\n   4. Deploy the app:")
    print("      databricks apps deploy")
    print("\n   5. Test thoroughly and review migration warnings above")
    
    print("\n" + "="*70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
