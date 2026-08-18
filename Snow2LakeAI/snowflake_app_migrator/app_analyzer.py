#!/usr/bin/env python3
"""
Snowflake Native App Analyzer

Analyzes Snowflake Native Application structure and components to prepare
for migration to Databricks Apps platform.
"""

from __future__ import annotations

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field


@dataclass
class AppComponent:
    """Represents a component of the Snowflake Native App"""
    name: str
    type: str  # 'streamlit', 'sql', 'python', 'udf', 'procedure', 'view', 'table'
    path: str
    content: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    complexity: str = "low"  # low, medium, high
    migration_notes: List[str] = field(default_factory=list)


@dataclass
class AppManifest:
    """Parsed Snowflake Native App manifest"""
    name: str
    version: str
    label: Optional[str] = None
    privileges: List[Dict] = field(default_factory=list)
    artifacts: List[Dict] = field(default_factory=list)
    configuration: Dict = field(default_factory=dict)
    raw_manifest: Dict = field(default_factory=dict)


@dataclass
class AppAnalysis:
    """Complete analysis of a Snowflake Native App"""
    app_name: str
    app_path: str
    manifest: Optional[AppManifest] = None
    components: List[AppComponent] = field(default_factory=list)
    has_streamlit: bool = False
    has_api: bool = False
    has_stored_procedures: bool = False
    has_udfs: bool = False
    python_files: List[str] = field(default_factory=list)
    sql_files: List[str] = field(default_factory=list)
    streamlit_pages: List[str] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)
    snowpark_usage: Dict[str, int] = field(default_factory=dict)
    migration_complexity: str = "medium"  # low, medium, high
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class SnowflakeAppAnalyzer:
    """Analyzes Snowflake Native App structure for migration to Databricks"""
    
    STREAMLIT_INDICATORS = [
        "import streamlit",
        "from streamlit",
        "st.",
        "streamlit_app"
    ]
    
    SNOWPARK_PATTERNS = [
        r"from snowflake\.snowpark",
        r"import snowflake\.snowpark",
        r"session\.table\(",
        r"session\.create_dataframe\(",
        r"session\.sql\(",
        r"@udf",
        r"@sproc"
    ]
    
    API_INDICATORS = [
        "from flask",
        "from fastapi",
        "@app.route",
        "@app.get",
        "@app.post"
    ]
    
    def __init__(self):
        self.analysis: Optional[AppAnalysis] = None
    
    def analyze(self, app_path: str) -> AppAnalysis:
        """
        Analyze a Snowflake Native App directory.
        
        Args:
            app_path: Path to the Snowflake Native App directory
            
        Returns:
            AppAnalysis object with complete analysis
        """
        app_path_obj = Path(app_path)
        if not app_path_obj.exists():
            raise ValueError(f"App path does not exist: {app_path}")
        
        app_name = app_path_obj.name
        self.analysis = AppAnalysis(app_name=app_name, app_path=str(app_path_obj.absolute()))
        
        # Parse manifest
        self._parse_manifest(app_path_obj)
        
        # Scan directory structure
        self._scan_directory(app_path_obj)
        
        # Analyze code patterns
        self._analyze_code_patterns()
        
        # Determine migration complexity
        self._assess_complexity()
        
        # Generate recommendations
        self._generate_recommendations()
        
        return self.analysis
    
    def _parse_manifest(self, app_path: Path):
        """Parse manifest.yml file"""
        manifest_path = app_path / "manifest.yml"
        if not manifest_path.exists():
            manifest_path = app_path / "manifest.yaml"
        
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r') as f:
                    manifest_data = yaml.safe_load(f)
                
                self.analysis.manifest = AppManifest(
                    name=manifest_data.get('manifest_version', 'unknown'),
                    version=manifest_data.get('version', {}).get('name', '1.0'),
                    label=manifest_data.get('version', {}).get('label', None),
                    privileges=manifest_data.get('privileges', []),
                    artifacts=manifest_data.get('artifacts', []),
                    configuration=manifest_data.get('configuration', {}),
                    raw_manifest=manifest_data
                )
            except Exception as e:
                self.analysis.warnings.append(f"Failed to parse manifest: {e}")
        else:
            self.analysis.warnings.append("No manifest.yml found")
    
    def _scan_directory(self, app_path: Path):
        """Scan directory for app components"""
        for root, dirs, files in os.walk(app_path):
            root_path = Path(root)
            
            for file in files:
                file_path = root_path / file
                relative_path = file_path.relative_to(app_path)
                
                # Categorize file
                if file.endswith('.py'):
                    self._analyze_python_file(file_path, str(relative_path))
                elif file.endswith('.sql'):
                    self._analyze_sql_file(file_path, str(relative_path))
                elif file == 'requirements.txt':
                    self._parse_requirements(file_path)
    
    def _analyze_python_file(self, file_path: Path, relative_path: str):
        """Analyze a Python file"""
        self.analysis.python_files.append(relative_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            component = AppComponent(
                name=file_path.name,
                type='python',
                path=relative_path,
                content=content
            )
            
            # Check for Streamlit
            if any(indicator in content for indicator in self.STREAMLIT_INDICATORS):
                component.type = 'streamlit'
                self.analysis.has_streamlit = True
                self.analysis.streamlit_pages.append(relative_path)
                component.migration_notes.append("Streamlit app - needs connector updates")
            
            # Check for API frameworks
            if any(indicator in content for indicator in self.API_INDICATORS):
                component.type = 'api'
                self.analysis.has_api = True
                component.migration_notes.append("API app - consider Flask/FastAPI patterns")
            
            # Check for Snowpark usage
            for pattern in self.SNOWPARK_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    snowpark_feature = pattern.replace(r'\\', '').replace('(', '').replace(')', '')
                    self.analysis.snowpark_usage[snowpark_feature] = self.analysis.snowpark_usage.get(snowpark_feature, 0) + len(matches)
                    component.dependencies.append('snowpark')
                    component.migration_notes.append(f"Uses Snowpark: {snowpark_feature}")
            
            # Check for UDF/Procedure decorators
            if '@udf' in content or '@sproc' in content:
                if '@udf' in content:
                    component.type = 'udf'
                    self.analysis.has_udfs = True
                if '@sproc' in content:
                    component.type = 'procedure'
                    self.analysis.has_stored_procedures = True
                component.complexity = 'medium'
                component.migration_notes.append("UDF/Procedure needs PySpark conversion")
            
            self.analysis.components.append(component)
            
        except Exception as e:
            self.analysis.warnings.append(f"Failed to analyze {relative_path}: {e}")
    
    def _analyze_sql_file(self, file_path: Path, relative_path: str):
        """Analyze a SQL file"""
        self.analysis.sql_files.append(relative_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            component = AppComponent(
                name=file_path.name,
                type='sql',
                path=relative_path,
                content=content
            )
            
            # Check for stored procedures
            if 'CREATE OR REPLACE PROCEDURE' in content.upper():
                component.type = 'procedure'
                self.analysis.has_stored_procedures = True
                component.complexity = 'high'
                component.migration_notes.append("Stored procedure - may need rewrite as Python UDF")
            
            # Check for UDFs
            if 'CREATE OR REPLACE FUNCTION' in content.upper():
                component.type = 'udf'
                self.analysis.has_udfs = True
                component.complexity = 'medium'
                component.migration_notes.append("UDF - convert to Databricks SQL UDF or Python UDF")
            
            # Check for views
            if 'CREATE OR REPLACE VIEW' in content.upper() or 'CREATE VIEW' in content.upper():
                component.type = 'view'
                component.complexity = 'low'
                component.migration_notes.append("View - SQL translation needed")
            
            # Check for Snowflake-specific syntax
            snowflake_features = []
            if 'VARIANT' in content.upper():
                snowflake_features.append('VARIANT type')
            if 'FLATTEN(' in content.upper():
                snowflake_features.append('FLATTEN function')
            if 'LATERAL FLATTEN' in content.upper():
                snowflake_features.append('LATERAL FLATTEN')
            if 'COPY INTO' in content.upper():
                snowflake_features.append('COPY INTO')
            
            if snowflake_features:
                component.complexity = 'high'
                component.migration_notes.append(f"Snowflake-specific: {', '.join(snowflake_features)}")
            
            self.analysis.components.append(component)
            
        except Exception as e:
            self.analysis.warnings.append(f"Failed to analyze {relative_path}: {e}")
    
    def _parse_requirements(self, file_path: Path):
        """Parse requirements.txt for dependencies"""
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        package = line.split('==')[0].split('>=')[0].split('<=')[0].strip()
                        self.analysis.dependencies.add(package)
        except Exception as e:
            self.analysis.warnings.append(f"Failed to parse requirements.txt: {e}")
    
    def _analyze_code_patterns(self):
        """Analyze code patterns across all components"""
        # Check for Snowpark prevalence
        if self.analysis.snowpark_usage:
            total_snowpark_calls = sum(self.analysis.snowpark_usage.values())
            if total_snowpark_calls > 20:
                self.analysis.warnings.append(
                    f"Heavy Snowpark usage detected ({total_snowpark_calls} calls) - extensive PySpark migration needed"
                )
    
    def _assess_complexity(self):
        """Assess overall migration complexity"""
        complexity_score = 0
        
        # Component types
        if self.analysis.has_streamlit:
            complexity_score += 2  # Streamlit is relatively straightforward
        if self.analysis.has_api:
            complexity_score += 3  # API requires more adaptation
        if self.analysis.has_stored_procedures:
            complexity_score += 5  # Procedures are complex
        if self.analysis.has_udfs:
            complexity_score += 3  # UDFs need conversion
        
        # Snowpark usage
        if self.analysis.snowpark_usage:
            complexity_score += min(len(self.analysis.snowpark_usage), 5)
        
        # SQL files
        complexity_score += min(len(self.analysis.sql_files), 5)
        
        # Determine complexity level
        if complexity_score <= 5:
            self.analysis.migration_complexity = 'low'
        elif complexity_score <= 12:
            self.analysis.migration_complexity = 'medium'
        else:
            self.analysis.migration_complexity = 'high'
    
    def _generate_recommendations(self):
        """Generate migration recommendations"""
        recs = self.analysis.recommendations
        
        # General recommendations
        if self.analysis.has_streamlit:
            recs.append("✓ Streamlit app detected - use Databricks Apps Streamlit runtime")
            recs.append("  Replace snowflake.connector with databricks.sql.connect")
            recs.append("  Update session.table() calls to spark.table()")
        
        if self.analysis.has_api:
            recs.append("✓ API app detected - use Flask/FastAPI in Databricks Apps")
            recs.append("  Set up proper authentication via app.yaml")
        
        if self.analysis.has_stored_procedures:
            recs.append("⚠ Stored procedures detected - consider converting to Python UDFs or notebooks")
        
        if self.analysis.has_udfs:
            recs.append("✓ UDFs detected - convert to Databricks SQL UDFs or Python UDFs")
        
        if self.analysis.snowpark_usage:
            recs.append("⚠ Snowpark usage detected - requires PySpark DataFrame API conversion")
            recs.append("  Key conversions: session.table() → spark.table(), session.sql() → spark.sql()")
        
        if 'snowflake-connector-python' in self.analysis.dependencies:
            recs.append("✓ Replace snowflake-connector-python with databricks-sql-connector")
        
        if 'snowflake-snowpark-python' in self.analysis.dependencies:
            recs.append("✓ Replace snowflake-snowpark-python with pyspark")
        
        # Complexity-based recommendations
        if self.analysis.migration_complexity == 'high':
            recs.append("⚠ High complexity migration - recommend phased approach")
            recs.append("  1. Migrate data layer and SQL first")
            recs.append("  2. Convert Python/Snowpark logic")
            recs.append("  3. Adapt UI layer last")
        
        # Permission recommendations
        if self.analysis.manifest and self.analysis.manifest.privileges:
            recs.append("✓ Review Snowflake privileges and map to Unity Catalog grants")
            recs.append("  USAGE → USE SCHEMA, SELECT → SELECT, EXECUTE → EXECUTE")
    
    def print_summary(self):
        """Print analysis summary"""
        if not self.analysis:
            print("No analysis performed yet")
            return
        
        print("\n" + "="*60)
        print(f" SNOWFLAKE NATIVE APP ANALYSIS")
        print("="*60)
        print(f" App Name:           {self.analysis.app_name}")
        print(f" App Path:           {self.analysis.app_path}")
        print(f" Migration Complexity: {self.analysis.migration_complexity.upper()}")
        print("="*60)
        
        print(f"\n📊 COMPONENTS:")
        print(f"   Python files:       {len(self.analysis.python_files)}")
        print(f"   SQL files:          {len(self.analysis.sql_files)}")
        print(f"   Streamlit pages:    {len(self.analysis.streamlit_pages)}")
        print(f"   Has API:            {'Yes' if self.analysis.has_api else 'No'}")
        print(f"   Stored Procedures:  {'Yes' if self.analysis.has_stored_procedures else 'No'}")
        print(f"   UDFs:               {'Yes' if self.analysis.has_udfs else 'No'}")
        
        if self.analysis.snowpark_usage:
            print(f"\n🔧 SNOWPARK USAGE:")
            for feature, count in self.analysis.snowpark_usage.items():
                print(f"   {feature}: {count} occurrences")
        
        if self.analysis.dependencies:
            print(f"\n📦 DEPENDENCIES:")
            for dep in sorted(self.analysis.dependencies):
                print(f"   • {dep}")
        
        if self.analysis.warnings:
            print(f"\n⚠️  WARNINGS:")
            for warning in self.analysis.warnings:
                print(f"   • {warning}")
        
        if self.analysis.recommendations:
            print(f"\n💡 RECOMMENDATIONS:")
            for rec in self.analysis.recommendations:
                print(f"   {rec}")
        
        print("\n" + "="*60)
