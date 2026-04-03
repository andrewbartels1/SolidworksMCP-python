"""
SolidWorks MCP Server - Example Workflows

This module provides comprehensive examples of using the SolidWorks MCP server
for various CAD automation tasks, from basic part creation to complex assemblies.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

# Example workflow configurations
EXAMPLE_WORKFLOWS = {
    "simple_part": {
        "name": "Simple Mechanical Part",
        "description": "Create a basic part with extrusion and hole",
        "difficulty": "Beginner",
        "estimated_time": "2-3 minutes",
    },
    "complex_bracket": {
        "name": "L-Bracket with Features",
        "description": "Complex bracket with multiple features, fillets, and holes",
        "difficulty": "Intermediate",
        "estimated_time": "5-7 minutes",
    },
    "assembly_workflow": {
        "name": "Simple Assembly",
        "description": "Create multiple parts and assemble them with mates",
        "difficulty": "Advanced",
        "estimated_time": "10-15 minutes",
    },
    "drawing_package": {
        "name": "Complete Drawing Package",
        "description": "Create part, generate technical drawings with dimensions",
        "difficulty": "Intermediate",
        "estimated_time": "8-10 minutes",
    },
    "batch_processing": {
        "name": "Batch File Operations",
        "description": "Process multiple files with custom properties and exports",
        "difficulty": "Advanced",
        "estimated_time": "5-8 minutes",
    },
}


class SolidWorksMCPDemo:
    """Demo class for SolidWorks MCP workflows."""

    def __init__(self, server):
        """Initialize demo with MCP server instance."""
        self.server = server
        self.logger = logging.getLogger(__name__)

    async def call_tool_safe(
        self, tool_name: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Safely call a tool with error handling."""
        try:
            self.logger.info(f"🔧 Calling tool: {tool_name}")
            result = await self.server.call_tool(tool_name, parameters)

            if result.get("status") == "success":
                self.logger.info(f"✅ {tool_name}: Success")
            else:
                self.logger.warning(
                    f"⚠️ {tool_name}: {result.get('message', 'Unknown issue')}"
                )

            return result
        except Exception as e:
            self.logger.error(f"❌ {tool_name}: {e}")
            return {"status": "error", "message": str(e)}

    async def simple_part_workflow(self) -> dict[str, Any]:
        """Create a simple mechanical part with basic features."""
        print("\n" + "=" * 50)
        print("🔨 SIMPLE PART WORKFLOW")
        print("=" * 50)
        print("Creating: Rectangular block with center hole")

        results = {}

        # Step 1: Create new part
        print("\n1️⃣ Creating new part...")
        part_result = await self.call_tool_safe(
            "create_part",
            {
                "template": "Part Template",
                "part_name": "Simple Block",
                "units": "mm",
                "material": "Aluminum 6061",
            },
        )
        results["create_part"] = part_result.get("status") == "success"

        # Step 2: Create base sketch
        print("\n2️⃣ Creating base sketch...")
        sketch_result = await self.call_tool_safe(
            "create_sketch", {"plane": "Front Plane", "sketch_name": "Base Rectangle"}
        )
        results["create_sketch"] = sketch_result.get("status") == "success"

        # Step 3: Draw rectangle
        print("\n3️⃣ Drawing rectangle...")
        rect_result = await self.call_tool_safe(
            "sketch_rectangle",
            {"width": 80.0, "height": 50.0, "center_x": 0.0, "center_y": 0.0},
        )
        results["sketch_rectangle"] = rect_result.get("status") == "success"

        # Step 4: Exit sketch and create extrusion
        print("\n4️⃣ Creating extrusion...")
        extrude_result = await self.call_tool_safe(
            "create_extrusion",
            {
                "sketch_name": "Base Rectangle",
                "depth": 20.0,
                "direction": "Blind",
                "reverse_direction": False,
            },
        )
        results["create_extrusion"] = extrude_result.get("status") == "success"

        # Step 5: Create hole sketch
        print("\n5️⃣ Creating hole sketch...")
        hole_sketch_result = await self.call_tool_safe(
            "create_sketch", {"plane": "Top Face", "sketch_name": "Center Hole"}
        )
        results["hole_sketch"] = hole_sketch_result.get("status") == "success"

        # Step 6: Draw circle for hole
        print("\n6️⃣ Drawing center circle...")
        circle_result = await self.call_tool_safe(
            "sketch_circle", {"center_x": 0.0, "center_y": 0.0, "radius": 8.0}
        )
        results["sketch_circle"] = circle_result.get("status") == "success"

        # Step 7: Create cut extrusion (hole)
        print("\n7️⃣ Creating center hole...")
        hole_result = await self.call_tool_safe(
            "create_extrusion",
            {
                "sketch_name": "Center Hole",
                "depth": 20.0,
                "direction": "Through All",
                "operation_type": "Cut",
            },
        )
        results["create_hole"] = hole_result.get("status") == "success"

        # Step 8: Calculate mass properties
        print("\n8️⃣ Calculating mass properties...")
        mass_result = await self.call_tool_safe(
            "calculate_mass_properties",
            {
                "model_path": "current",
                "units": "kg",
                "reference_coordinate_system": "default",
            },
        )
        results["mass_properties"] = mass_result.get("status") == "success"

        success_count = sum(results.values())
        total_steps = len(results)

        print(
            f"\n📊 Workflow Summary: {success_count}/{total_steps} steps completed successfully"
        )

        if success_count == total_steps:
            print("🎉 Simple part workflow completed successfully!")
        else:
            print("⚠️ Some steps encountered issues - check logs for details")

        return results

    async def complex_bracket_workflow(self) -> dict[str, Any]:
        """Create a complex L-bracket with multiple features."""
        print("\n" + "=" * 50)
        print("🏗️ COMPLEX BRACKET WORKFLOW")
        print("=" * 50)
        print("Creating: L-bracket with holes, fillets, and chamfers")

        results = {}

        # Step 1: Create new part
        print("\n1️⃣ Creating bracket part...")
        part_result = await self.call_tool_safe(
            "create_part",
            {
                "template": "Part Template",
                "part_name": "L-Bracket",
                "units": "mm",
                "material": "Steel AISI 1020",
            },
        )
        results["create_part"] = part_result.get("status") == "success"

        # Step 2: Create L-profile sketch
        print("\n2️⃣ Creating L-profile sketch...")
        sketch_result = await self.call_tool_safe(
            "create_sketch", {"plane": "Right Plane", "sketch_name": "L-Profile"}
        )
        results["l_profile"] = sketch_result.get("status") == "success"

        # Step 3: Draw L-shape using lines
        print("\n3️⃣ Drawing L-profile lines...")
        # Create vertical segment
        line1_result = await self.call_tool_safe(
            "sketch_line", {"start_x": 0.0, "start_y": 0.0, "end_x": 0.0, "end_y": 60.0}
        )

        # Create horizontal segment
        line2_result = await self.call_tool_safe(
            "sketch_line", {"start_x": 0.0, "start_y": 0.0, "end_x": 80.0, "end_y": 0.0}
        )

        # Create thickness lines
        line3_result = await self.call_tool_safe(
            "sketch_line",
            {"start_x": 0.0, "start_y": 60.0, "end_x": 10.0, "end_y": 60.0},
        )

        results["l_lines"] = all(
            [
                line1_result.get("status") == "success",
                line2_result.get("status") == "success",
                line3_result.get("status") == "success",
            ]
        )

        # Step 4: Add dimensions and constraints
        print("\n4️⃣ Adding sketch constraints...")
        constraint_result = await self.call_tool_safe(
            "add_constraint",
            {
                "constraint_type": "Horizontal",
                "entities": ["Line2"],
                "constraint_parameters": {},
            },
        )
        results["constraints"] = constraint_result.get("status") == "success"

        # Step 5: Create extrusion
        print("\n5️⃣ Creating L-bracket extrusion...")
        extrude_result = await self.call_tool_safe(
            "create_extrusion",
            {"sketch_name": "L-Profile", "depth": 15.0, "direction": "Blind"},
        )
        results["extrusion"] = extrude_result.get("status") == "success"

        # Step 6: Create mounting holes pattern
        print("\n6️⃣ Creating mounting holes...")
        hole_pattern_result = await self.call_tool_safe(
            "create_pattern",
            {
                "pattern_type": "Linear",
                "feature_to_pattern": "Mounting Hole",
                "direction_1": {"distance": 30.0, "instances": 3},
                "direction_2": {"distance": 20.0, "instances": 2},
            },
        )
        results["hole_pattern"] = hole_pattern_result.get("status") == "success"

        # Step 7: Add fillets
        print("\n7️⃣ Adding corner fillets...")
        fillet_result = await self.call_tool_safe(
            "create_fillet",
            {
                "edges": ["Corner Edge1", "Corner Edge2"],
                "radius": 3.0,
                "fillet_type": "Constant Radius",
            },
        )
        results["fillets"] = fillet_result.get("status") == "success"

        # Step 8: Mass properties analysis
        print("\n8️⃣ Analyzing bracket properties...")
        analysis_result = await self.call_tool_safe(
            "calculate_mass_properties",
            {"model_path": "current", "units": "kg", "include_center_of_mass": True},
        )
        results["analysis"] = analysis_result.get("status") == "success"

        success_count = sum(results.values())
        total_steps = len(results)

        print(
            f"\n📊 Complex Bracket Summary: {success_count}/{total_steps} steps completed"
        )

        if success_count >= total_steps * 0.8:  # 80% success rate
            print("🎉 Complex bracket workflow completed successfully!")
        else:
            print("⚠️ Workflow encountered multiple issues")

        return results

    async def drawing_package_workflow(self) -> dict[str, Any]:
        """Create complete drawing package with dimensions."""
        print("\n" + "=" * 50)
        print("📐 DRAWING PACKAGE WORKFLOW")
        print("=" * 50)
        print("Creating: Technical drawings with full dimensioning")

        results = {}

        # Assume we have a part already created
        print("\n1️⃣ Creating technical drawing...")
        drawing_result = await self.call_tool_safe(
            "create_technical_drawing",
            {
                "model_file": "current_part.sldprt",
                "template": "A3_Drawing_Template.drwdot",
                "output_path": "drawings/part_drawing.slddrw",
                "sheet_format": "A3 (ISO) Landscape",
                "scale": "1:1",
                "auto_populate_views": True,
            },
        )
        results["create_drawing"] = drawing_result.get("status") == "success"

        # Step 2: Add standard views
        print("\n2️⃣ Adding drawing views...")
        views = [
            {"type": "Front", "position": [100, 200], "scale": "1:1"},
            {"type": "Right", "position": [250, 200], "scale": "1:1"},
            {"type": "Top", "position": [100, 350], "scale": "1:1"},
            {"type": "Isometric", "position": [250, 350], "scale": "1:2"},
        ]

        view_results = []
        for i, view in enumerate(views):
            view_result = await self.call_tool_safe(
                "add_drawing_view",
                {
                    "drawing_path": "part_drawing.slddrw",
                    "view_type": view["type"],
                    "view_name": f"View{i + 1}",
                    "position": view["position"],
                    "scale": view["scale"],
                },
            )
            view_results.append(view_result.get("status") == "success")

        results["drawing_views"] = all(view_results)

        # Step 3: Add dimensions
        print("\n3️⃣ Adding dimensions...")
        dimensions = [
            {"type": "Linear", "entities": ["Line1", "Line2"], "position": [150, 250]},
            {"type": "Radial", "entities": ["Circle1"], "position": [75, 180]},
            {"type": "Angular", "entities": ["Line1", "Line3"], "position": [120, 220]},
        ]

        dim_results = []
        for dimension in dimensions:
            dim_result = await self.call_tool_safe(
                "add_dimension",
                {
                    "drawing_path": "part_drawing.slddrw",
                    "dimension_type": dimension["type"],
                    "entities": dimension["entities"],
                    "position": dimension["position"],
                    "tolerance": "±0.1",
                },
            )
            dim_results.append(dim_result.get("status") == "success")

        results["dimensions"] = all(dim_results)

        # Step 4: Add annotations
        print("\n4️⃣ Adding annotations and notes...")
        annotation_result = await self.call_tool_safe(
            "add_annotation",
            {
                "drawing_path": "part_drawing.slddrw",
                "annotation_type": "Note",
                "text": "Material: Steel AISI 1020\nFinish: Mill finish\nTolerances: ±0.1mm unless noted",
                "position": [300, 50],
                "font_size": 10,
            },
        )
        results["annotations"] = annotation_result.get("status") == "success"

        # Step 5: Update title block
        print("\n5️⃣ Updating title block...")
        title_result = await self.call_tool_safe(
            "update_title_block",
            {
                "drawing_path": "part_drawing.slddrw",
                "title": "L-Bracket Assembly",
                "part_number": "LB-001-A",
                "revision": "REV A",
                "drawn_by": "CAD Engineer",
                "checked_by": "Design Manager",
                "material": "Steel AISI 1020",
                "scale": "1:1",
            },
        )
        results["title_block"] = title_result.get("status") == "success"

        # Step 6: Export to PDF
        print("\n6️⃣ Exporting to PDF...")
        pdf_result = await self.call_tool_safe(
            "export_pdf",
            {
                "drawing_path": "part_drawing.slddrw",
                "output_path": "exports/part_drawing.pdf",
                "quality": "High",
                "color_mode": "Color",
            },
        )
        results["export_pdf"] = pdf_result.get("status") == "success"

        success_count = sum(results.values())
        total_steps = len(results)

        print(
            f"\n📊 Drawing Package Summary: {success_count}/{total_steps} operations completed"
        )

        if success_count >= total_steps * 0.8:
            print("🎉 Drawing package workflow completed successfully!")
        else:
            print("⚠️ Drawing workflow encountered some issues")

        return results

    async def batch_processing_workflow(self) -> dict[str, Any]:
        """Demonstrate batch processing capabilities."""
        print("\n" + "=" * 50)
        print("🔄 BATCH PROCESSING WORKFLOW")
        print("=" * 50)
        print("Processing: Multiple files with properties and exports")

        results = {}

        # Step 1: Batch update custom properties
        print("\n1️⃣ Batch updating custom properties...")
        batch_props_result = await self.call_tool_safe(
            "batch_process_files",
            {
                "source_directory": "./parts/",
                "operation": "Update custom properties",
                "operation_parameters": {
                    "properties": {
                        "Author": "Engineering Team",
                        "CompanyName": "ACME Corp",
                        "Revision": "A",
                        "CheckedBy": "QA Manager",
                        "ApprovedBy": "Design Manager",
                    },
                    "overwrite_existing": True,
                },
                "file_pattern": "*.sldprt",
                "include_subdirectories": True,
                "parallel_processing": True,
            },
        )
        results["batch_properties"] = batch_props_result.get("status") == "success"

        # Step 2: Batch export to STEP
        print("\n2️⃣ Batch exporting to STEP format...")
        batch_export_result = await self.call_tool_safe(
            "batch_export",
            {
                "source_directory": "./parts/",
                "output_directory": "./exports/step/",
                "export_format": "STEP",
                "file_pattern": "*.sldprt",
                "include_subdirectories": True,
                "export_options": {
                    "step_version": "AP214",
                    "units": "mm",
                    "quality": "high",
                },
            },
        )
        results["batch_export"] = batch_export_result.get("status") == "success"

        # Step 3: Generate VBA for complex operations
        print("\n3️⃣ Generating VBA for complex operations...")
        vba_result = await self.call_tool_safe(
            "generate_vba_code",
            {
                "operation_type": "Batch File Processing",
                "parameters": {
                    "source_folder": "./parts/",
                    "operations": ["UpdateProperties", "ExportSTEP", "GenerateDrawing"],
                    "batch_size": 10,
                    "parallel_processing": True,
                    "error_handling": "Continue",
                    "log_operations": True,
                },
            },
        )
        results["vba_generation"] = vba_result.get("status") == "success"

        # Step 4: Create batch reports
        print("\n4️⃣ Generating batch processing reports...")
        report_result = await self.call_tool_safe(
            "generate_drawing_report",
            {
                "drawing_path": "./processed_files/",
                "report_type": "Batch Summary",
                "include_statistics": True,
                "include_errors": True,
                "export_format": "Excel",
                "output_path": "reports/batch_processing_report.xlsx",
            },
        )
        results["batch_reports"] = report_result.get("status") == "success"

        # Step 5: Optimize performance for large batches
        print("\n5️⃣ Optimizing batch performance...")
        optimize_result = await self.call_tool_safe(
            "optimize_performance",
            {
                "target_file": "./parts/large_assembly.sldasm",
                "optimization_type": "Batch processing",
                "optimization_level": "Balanced",
                "preserve_features": ["Mates", "Configurations"],
                "create_backup": True,
            },
        )
        results["performance_optimization"] = optimize_result.get("status") == "success"

        success_count = sum(results.values())
        total_steps = len(results)

        print(
            f"\n📊 Batch Processing Summary: {success_count}/{total_steps} operations completed"
        )

        if success_count >= total_steps * 0.8:
            print("🎉 Batch processing workflow completed successfully!")
        else:
            print("⚠️ Batch processing encountered some issues")

        return results

    async def run_workflow(self, workflow_name: str) -> dict[str, Any]:
        """Run a specific workflow by name."""
        workflow_methods = {
            "simple_part": self.simple_part_workflow,
            "complex_bracket": self.complex_bracket_workflow,
            "drawing_package": self.drawing_package_workflow,
            "batch_processing": self.batch_processing_workflow,
        }

        if workflow_name not in workflow_methods:
            raise ValueError(f"Unknown workflow: {workflow_name}")

        workflow_info = EXAMPLE_WORKFLOWS[workflow_name]
        print(f"\n🎬 Starting workflow: {workflow_info['name']}")
        print(f"📝 Description: {workflow_info['description']}")
        print(f"🎯 Difficulty: {workflow_info['difficulty']}")
        print(f"⏱️ Estimated time: {workflow_info['estimated_time']}")

        start_time = asyncio.get_event_loop().time()
        results = await workflow_methods[workflow_name]()
        end_time = asyncio.get_event_loop().time()

        elapsed = end_time - start_time
        print(f"\n⏱️ Actual time: {elapsed:.1f} seconds")

        return results

    async def run_all_workflows(self) -> dict[str, dict[str, Any]]:
        """Run all available workflows as a comprehensive demo."""
        print("\n" + "=" * 60)
        print("🎭 COMPREHENSIVE SOLIDWORKS MCP DEMONSTRATION")
        print("=" * 60)
        print("Running all example workflows to showcase capabilities")

        all_results = {}

        for workflow_name in EXAMPLE_WORKFLOWS.keys():
            try:
                print(f"\n{'=' * 20} {workflow_name.upper()} {'=' * 20}")
                results = await self.run_workflow(workflow_name)
                all_results[workflow_name] = results

                success_rate = sum(results.values()) / len(results) * 100
                print(f"✅ {workflow_name}: {success_rate:.0f}% success rate")

            except Exception as e:
                print(f"❌ {workflow_name}: Failed - {e}")
                all_results[workflow_name] = {"error": str(e)}

        # Final summary
        print(f"\n" + "=" * 60)
        print("🏆 DEMONSTRATION SUMMARY")
        print("=" * 60)

        total_workflows = len(all_results)
        successful_workflows = sum(
            1
            for result in all_results.values()
            if not isinstance(result, dict) or "error" not in result
        )

        print(f"📊 Workflows completed: {successful_workflows}/{total_workflows}")
        print(f"🎯 Success rate: {successful_workflows / total_workflows * 100:.0f}%")

        for workflow_name, results in all_results.items():
            if "error" in results:
                status = "❌ FAILED"
            else:
                success_rate = sum(results.values()) / len(results) * 100
                status = f"✅ {success_rate:.0f}% success"

            workflow_info = EXAMPLE_WORKFLOWS[workflow_name]
            print(f"  {workflow_info['name']}: {status}")

        return all_results


# Example usage functions for standalone testing
async def run_demo_workflow(server, workflow_name: str = "simple_part"):
    """Run a single demo workflow."""
    demo = SolidWorksMCPDemo(server)
    return await demo.run_workflow(workflow_name)


async def run_comprehensive_demo(server):
    """Run all demo workflows."""
    demo = SolidWorksMCPDemo(server)
    return await demo.run_all_workflows()


def print_available_workflows():
    """Print information about available workflows."""
    print("\n" + "=" * 60)
    print("📚 AVAILABLE EXAMPLE WORKFLOWS")
    print("=" * 60)

    for workflow_id, info in EXAMPLE_WORKFLOWS.items():
        print(f"\n🔧 {workflow_id}")
        print(f"   Name: {info['name']}")
        print(f"   Description: {info['description']}")
        print(f"   Difficulty: {info['difficulty']}")
        print(f"   Time: {info['estimated_time']}")

    print(f"\n💡 Use start_local_server.py to run these workflows")
    print(f"📖 Or integrate into your own applications")


if __name__ == "__main__":
    print_available_workflows()
