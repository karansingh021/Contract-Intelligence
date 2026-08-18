#!/usr/bin/env python3
"""
Databricks App Converter

Converts analyzed Snowflake Native App to Databricks Apps format.
Generates app.yaml, app.py, and all necessary supporting files.
"""

from __future__ import annotations

import os
import re
import shutil
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

from app_analyzer import AppAnalysis, AppComponent


@dataclass
class DatabricksApp:
    """Represents a Databricks App"""
    name: str
    app_path: str
    app_yaml_path: str
    app_py_path: str
    source_analysis: AppAnalysis
    migration_notes: List[str]


class DatabricksAppConverter:
    """Converts Snowflake Native App to Databricks App"""
    
    def __init__(self):
        self.templates_dir = Path(__file__).parent / "templates"
    
    def convert(self, analysis: AppAnalysis, output_dir: str) -> DatabricksApp:
        """
        Convert analyzed Snowflake app to Databricks App format.
        
        Args:
            analysis: AppAnalysis from SnowflakeAppAnalyzer
            output_dir: Directory to write Databricks App files
            
        Returns:
            DatabricksApp object
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        migration_notes = []
        
        # Create directory structure
        self._create_directory_structure(output_path, analysis)
        
        # Generate app.yaml
        app_yaml_path = self._generate_app_yaml(output_path, analysis)
        migration_notes.append(f"Generated app.yaml at {app_yaml_path}")
        
        # Generate app.py (main entry point)
        app_py_path = self._generate_app_py(output_path, analysis)
        migration_notes.append(f"Generated app.py at {app_py_path}")
        
        # Generate requirements.txt
        self._generate_requirements(output_path, analysis)
        migration_notes.append("Generated requirements.txt")
        
        # Convert source files
        self._convert_source_files(output_path, analysis)
        migration_notes.append(f"Converted {len(analysis.components)} source files")
        
        # Generate Unity Catalog setup
        self._generate_uc_setup(output_path, analysis)
        migration_notes.append("Generated Unity Catalog setup scripts")
        
        # Generate deployment instructions
        self._generate_readme(output_path, analysis)
        migration_notes.append("Generated deployment README")
        
        return DatabricksApp(
            name=analysis.app_name,
            app_path=str(output_path),
            app_yaml_path=str(app_yaml_path),
            app_py_path=str(app_py_path),
            source_analysis=analysis,
            migration_notes=migration_notes
        )
    
    def _create_directory_structure(self, output_path: Path, analysis: AppAnalysis):
        """Create Databricks App directory structure"""
        dirs = [
            "src",
            "databricks",
            "databricks/init_scripts",
            "tests"
        ]
        
        if analysis.has_streamlit:
            dirs.append("src/pages")  # For multi-page Streamlit apps
        
        if analysis.has_api:
            dirs.extend(["src/api", "src/api/routes"])
        
        for dir_name in dirs:
            (output_path / dir_name).mkdir(parents=True, exist_ok=True)
    
    def _generate_app_yaml(self, output_path: Path, analysis: AppAnalysis) -> Path:
        """Generate app.yaml configuration"""
        app_yaml = {
            "name": analysis.app_name.lower().replace(' ', '_'),
            "description": f"Migrated from Snowflake Native App: {analysis.app_name}"
        }
        
        # Determine app type
        if analysis.has_streamlit:
            app_yaml["streamlit"] = {
                "app_file": "src/streamlit_app.py",
                "python_version": "3.10"
            }
        elif analysis.has_api:
            app_yaml["flask"] = {
                "app_file": "app.py",
                "python_version": "3.10"
            }
        
        # Add permissions
        if analysis.manifest and analysis.manifest.privileges:
            app_yaml["permissions"] = self._convert_privileges(analysis.manifest.privileges)
        
        # Write app.yaml
        yaml_path = output_path / "app.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(app_yaml, f, default_flow_style=False, sort_keys=False)
        
        return yaml_path
    
    def _generate_app_py(self, output_path: Path, analysis: AppAnalysis) -> Path:
        """Generate main app.py entry point"""
        
        if analysis.has_streamlit:
            # For Streamlit apps, app.py is minimal - main logic in src/streamlit_app.py
            content = self._generate_streamlit_app_py(analysis)
        elif analysis.has_api:
            content = self._generate_api_app_py(analysis)
        else:
            content = self._generate_generic_app_py(analysis)
        
        app_py_path = output_path / "app.py"
        with open(app_py_path, 'w') as f:
            f.write(content)
        
        return app_py_path
    
    def _generate_streamlit_app_py(self, analysis: AppAnalysis) -> str:
        """Generate app.py for Streamlit-based apps"""
        return '''
# app.py - Databricks App Entry Point (Streamlit)
# The actual Streamlit app is in src/streamlit_app.py

import sys
from pathlib import Path

# Add src to path so imports work
sys.path.insert(0, str(Path(__file__).parent / "src"))

if __name__ == "__main__":
    import streamlit_app
'''.strip()
    
    def _generate_api_app_py(self, analysis: AppAnalysis) -> str:
        """Generate app.py for API-based apps"""
        return '''
# app.py - Databricks App Entry Point (Flask API)

from flask import Flask, jsonify
from databricks.sql import connect
import os

app = Flask(__name__)

# Database connection helper
def get_db_connection():
    return connect(
        server_hostname=os.environ.get("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.environ.get("DATABRICKS_HTTP_PATH"),
        access_token=os.environ.get("DATABRICKS_TOKEN")
    )

@app.route("/")
def index():
    return jsonify({
        "app": "''' + analysis.app_name + '''",
        "status": "running",
        "migrated_from": "Snowflake Native App"
    })

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
'''.strip()
    
    def _generate_generic_app_py(self, analysis: AppAnalysis) -> str:
        """Generate generic app.py"""
        return '''
# app.py - Databricks App Entry Point

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    print("''' + analysis.app_name + ''' - Databricks App")
    print("Migrated from Snowflake Native App")
    # Add your app logic here

if __name__ == "__main__":
    main()
'''.strip()
    
    def _generate_requirements(self, output_path: Path, analysis: AppAnalysis):
        """Generate requirements.txt"""
        requirements = set()
        
        # Core Databricks dependencies
        requirements.add("databricks-sql-connector>=3.0.0")
        
        if analysis.has_streamlit:
            requirements.add("streamlit>=1.30.0")
        
        if analysis.has_api:
            requirements.add("flask>=3.0.0")
        
        # Add PySpark if Snowpark was used
        if analysis.snowpark_usage:
            requirements.add("pyspark>=3.5.0")
        
        # Convert Snowflake dependencies to Databricks equivalents
        for dep in analysis.dependencies:
            if 'snowflake-connector' in dep:
                continue  # Already added databricks-sql-connector
            elif 'snowflake-snowpark' in dep:
                continue  # PySpark handles this
            elif dep not in ['streamlit', 'flask', 'pyspark']:  # Avoid duplicates
                requirements.add(dep)
        
        # Write requirements.txt
        req_path = output_path / "requirements.txt"
        with open(req_path, 'w') as f:
            for req in sorted(requirements):
                f.write(f"{req}\n")
    
    def _convert_source_files(self, output_path: Path, analysis: AppAnalysis):
        """Convert and copy source files"""
        for component in analysis.components:
            if component.type == 'streamlit':
                self._convert_streamlit_file(output_path, component)
            elif component.type in ['python', 'api']:
                self._convert_python_file(output_path, component)
            elif component.type == 'sql':
                self._convert_sql_file(output_path, component)
    
    def _convert_streamlit_file(self, output_path: Path, component: AppComponent):
        """Convert Streamlit file with connector updates"""
        if not component.content:
            return
        
        content = component.content
        
        # Replace Snowflake connector imports
        content = re.sub(
            r'import snowflake\.connector',
            'from databricks import sql',
            content
        )
        content = re.sub(
            r'from snowflake import connector',
            'from databricks import sql',
            content
        )
        
        # Replace connection patterns
        content = re.sub(
            r'snowflake\.connector\.connect\(',
            'sql.connect(',
            content
        )
        
        # Replace Snowpark Session with Spark
        content = re.sub(
            r'from snowflake\.snowpark import Session',
            'from pyspark.sql import SparkSession',
            content
        )
        content = re.sub(
            r'session\.table\(',
            'spark.table(',
            content
        )
        content = re.sub(
            r'session\.sql\(',
            'spark.sql(',
            content
        )
        
        # Add Databricks connection helper
        if 'sql.connect(' in content and 'get_db_connection' not in content:
            connection_helper = '''
import os

def get_db_connection():
    """Create Databricks SQL connection"""
    from databricks import sql
    return sql.connect(
        server_hostname=os.environ.get("DATABRICKS_SERVER_HOSTNAME"),
        http_path=os.environ.get("DATABRICKS_HTTP_PATH"),
        access_token=os.environ.get("DATABRICKS_TOKEN")
    )
'''
            content = connection_helper + "\n" + content
        
        # Write converted file
        if 'pages/' in component.path:
            target_path = output_path / "src" / component.path
        else:
            target_path = output_path / "src" / "streamlit_app.py"
        
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, 'w') as f:
            f.write(content)
    
    def _convert_python_file(self, output_path: Path, component: AppComponent):
        """Convert regular Python file"""
        if not component.content:
            return
        
        content = component.content
        
        # Basic Snowpark to PySpark conversions
        if 'snowpark' in content:
            content = re.sub(
                r'from snowflake\.snowpark import.*',
                'from pyspark.sql import SparkSession, DataFrame',
                content
            )
            content = content.replace('snowpark.Session', 'SparkSession')
            content = content.replace('session.', 'spark.')
        
        # Write converted file
        target_path = output_path / "src" / Path(component.path).name
        with open(target_path, 'w') as f:
            f.write(content)
    
    def _convert_sql_file(self, output_path: Path, component: AppComponent):
        """Convert SQL file - copy to databricks/ directory for manual review"""
        if not component.content:
            return
        
        content = component.content
        
        # Add migration note at top
        header = f"-- Converted from: {component.path}\n"
        header += "-- NOTE: This SQL has been auto-converted. Please review carefully.\n"
        header += "-- Snowflake-specific syntax may need manual adjustment.\n\n"
        
        content = header + content
        
        # Write to databricks directory
        target_path = output_path / "databricks" / Path(component.path).name
        with open(target_path, 'w') as f:
            f.write(content)
    
    def _generate_uc_setup(self, output_path: Path, analysis: AppAnalysis):
        """Generate Unity Catalog setup script"""
        setup_sql = []
        setup_sql.append("-- Unity Catalog Setup for " + analysis.app_name)
        setup_sql.append("-- Run this to set up tables, views, and permissions\n")
        
        # Create catalog and schema
        setup_sql.append("-- Create catalog and schema")
        setup_sql.append(f"CREATE CATALOG IF NOT EXISTS {analysis.app_name.lower()}_catalog;")
        setup_sql.append(f"CREATE SCHEMA IF NOT EXISTS {analysis.app_name.lower()}_catalog.main;\n")
        
        # Add grants based on manifest privileges
        if analysis.manifest and analysis.manifest.privileges:
            setup_sql.append("-- Permissions (converted from Snowflake privileges)")
            for priv in analysis.manifest.privileges:
                # This is a simplified conversion - real mapping is more complex
                setup_sql.append(f"-- Original privilege: {priv}")
                setup_sql.append(f"-- TODO: Map to appropriate Unity Catalog GRANT statement\n")
        
        # Write setup script
        setup_path = output_path / "databricks" / "unity_catalog_setup.sql"
        with open(setup_path, 'w') as f:
            f.write("\n".join(setup_sql))
    
    def _generate_readme(self, output_path: Path, analysis: AppAnalysis):
        """Generate deployment README"""
        readme = f"""# {analysis.app_name} - Databricks App

Migrated from Snowflake Native App

## Migration Summary

- **Migration Complexity**: {analysis.migration_complexity.upper()}
- **Components Converted**: {len(analysis.components)}
- **Python Files**: {len(analysis.python_files)}
- **SQL Files**: {len(analysis.sql_files)}
- **App Type**: {'Streamlit' if analysis.has_streamlit else 'API' if analysis.has_api else 'Generic'}

## Deployment Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Unity Catalog

Run the setup script:

```bash
databricks sql execute -f databricks/unity_catalog_setup.sql
```

### 3. Configure Environment

Set these environment variables:

```bash
export DATABRICKS_SERVER_HOSTNAME="your-workspace.cloud.databricks.com"
export DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/xxxxx"
export DATABRICKS_TOKEN="your-token"
```

### 4. Deploy the App

```bash
databricks apps deploy
```

### 5. Test the App

Visit the app URL provided after deployment.

## Manual Review Required

"""
        
        if analysis.warnings:
            readme += "### Warnings\n\n"
            for warning in analysis.warnings:
                readme += f"- {warning}\n"
            readme += "\n"
        
        if analysis.recommendations:
            readme += "### Recommendations\n\n"
            for rec in analysis.recommendations:
                readme += f"- {rec}\n"
            readme += "\n"
        
        readme += """## File Structure

```
.
├── app.yaml                    # Databricks App configuration
├── app.py                      # Main entry point
├── requirements.txt            # Python dependencies
├── src/                        # Application source code
│   ├── streamlit_app.py        # Streamlit UI (if applicable)
│   └── ...                     # Other Python modules
├── databricks/                 # Databricks-specific files
│   ├── unity_catalog_setup.sql # UC setup script
│   └── init_scripts/           # Initialization scripts
└── tests/                      # Test files
```

## Support

For issues or questions about this migration, refer to Databricks Apps documentation:
https://docs.databricks.com/en/dev-tools/databricks-apps/index.html
"""
        
        readme_path = output_path / "README.md"
        with open(readme_path, 'w') as f:
            f.write(readme)
    
    def _convert_privileges(self, privileges: List[Dict]) -> Dict:
        """Convert Snowflake privileges to Databricks permissions"""
        # Simplified conversion - real mapping is more complex
        permissions = {
            "users": [],
            "service_principals": []
        }
        
        # This is a placeholder - actual privilege mapping needs more logic
        for priv in privileges:
            # Map Snowflake application roles to service principals
            if isinstance(priv, dict) and 'privilege' in priv:
                permissions["users"].append({
                    "permission": "CAN_VIEW",
                    "comment": f"Converted from Snowflake privilege: {priv}"
                })
        
        return permissions
