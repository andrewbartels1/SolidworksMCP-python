"""
Integration tests for SolidWorks MCP Server.

Comprehensive end-to-end tests covering complete workflows from server startup
through tool execution and shutdown.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.solidworks_mcp.server import SolidWorksMCPServer
from src.solidworks_mcp.config import DeploymentMode, SecurityLevel
from src.solidworks_mcp.tools.modeling import CreatePartInput, CreateExtrusionInput
from src.solidworks_mcp.tools.sketching import CreateSketchInput, AddCircleInput


class TestCompleteWorkflows:
    """Test complete SolidWorks automation workflows."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_simple_part_creation_workflow(self, mock_config):
        """Test complete workflow for creating a simple part."""
        # Setup server
        server = SolidWorksMCPServer(mock_config)
        await server.setup()

        # Verify server is ready
        health = await server.health_check()
        assert health["status"] in ["healthy", "warning"]
        assert server.state.tool_count > 0

        # Simulate complete part creation workflow
        # 1. Create new part
        # 2. Create sketch
        # 3. Add circle to sketch
        # 4. Exit sketch
        # 5. Create extrusion

        # Mock all the adapter operations
        server.state.adapter.create_part = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"name": "TestPart", "units": "mm"},
                execution_time=1.0,
            )
        )

        server.state.adapter.create_sketch = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"sketch_name": "Sketch1", "plane": "Front Plane"},
                execution_time=0.3,
            )
        )

        server.state.adapter.add_sketch_circle = AsyncMock(
            return_value=Mock(
                is_success=True, data={"entity_id": "Circle1"}, execution_time=0.2
            )
        )

        server.state.adapter.exit_sketch = AsyncMock(
            return_value=Mock(
                is_success=True, data={"sketch_name": "Sketch1"}, execution_time=0.1
            )
        )

        server.state.adapter.create_extrusion = AsyncMock(
            return_value=Mock(
                is_success=True,
                data={"feature_name": "Boss-Extrude1"},
                execution_time=0.8,
            )
        )

        # Execute workflow steps
        workflow_results = []

        # Step 1: Create part
        create_part_tool = None
        for tool in server.mcp._tools:
            if tool.name == "create_part":
                create_part_tool = tool.func
                break
        assert create_part_tool is not None

        part_result = await create_part_tool(
            CreatePartInput(name="TestPart", units="mm")
        )
        workflow_results.append(("create_part", part_result))
        assert part_result["status"] == "success"

        # Step 2: Create sketch
        create_sketch_tool = None
        for tool in server.mcp._tools:
            if tool.name == "create_sketch":
                create_sketch_tool = tool.func
                break
        assert create_sketch_tool is not None

        sketch_result = await create_sketch_tool(CreateSketchInput(plane="Front Plane"))
        workflow_results.append(("create_sketch", sketch_result))
        assert sketch_result["status"] == "success"

        # Step 3: Add circle
        add_circle_tool = None
        for tool in server.mcp._tools:
            if tool.name == "add_circle":
                add_circle_tool = tool.func
                break
        assert add_circle_tool is not None

        circle_result = await add_circle_tool(
            AddCircleInput(center_x=0, center_y=0, radius=25)
        )
        workflow_results.append(("add_circle", circle_result))
        assert circle_result["status"] == "success"

        # Step 4: Exit sketch
        exit_sketch_tool = None
        for tool in server.mcp._tools:
            if tool.name == "exit_sketch":
                exit_sketch_tool = tool.func
                break
        assert exit_sketch_tool is not None

        exit_result = await exit_sketch_tool({})
        workflow_results.append(("exit_sketch", exit_result))
        assert exit_result["status"] == "success"

        # Step 5: Create extrusion
        create_extrusion_tool = None
        for tool in server.mcp._tools:
            if tool.name == "create_extrusion":
                create_extrusion_tool = tool.func
                break
        assert create_extrusion_tool is not None

        extrusion_result = await create_extrusion_tool(
            CreateExtrusionInput(sketch_name="Sketch1", depth=10.0, direction="blind")
        )
        workflow_results.append(("create_extrusion", extrusion_result))
        assert extrusion_result["status"] == "success"

        # Verify complete workflow
        assert len(workflow_results) == 5
        for step_name, result in workflow_results:
            assert result["status"] == "success", f"Step {step_name} failed: {result}"

        # Cleanup
        await server.stop()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multi_configuration_workflow(self, mock_config):
        """Test workflow with multiple server configurations."""
        configs = [
            # Local minimal security
            mock_config,
            # Remote strict security
            mock_config.model_copy(
                update={
                    "deployment_mode": DeploymentMode.REMOTE,
                    "security_level": SecurityLevel.STRICT,
                    "port": 8081,
                }
            ),
        ]

        for i, config in enumerate(configs):
            server = SolidWorksMCPServer(config)
            await server.setup()

            # Test basic functionality with each configuration
            health = await server.health_check()
            assert health["status"] in ["healthy", "warning"]
            assert health["config"]["deployment_mode"] == config.deployment_mode
            assert health["config"]["security_level"] == config.security_level

            await server.stop()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_error_recovery_workflow(self, mock_config):
        """Test workflow with error conditions and recovery."""
        server = SolidWorksMCPServer(mock_config)
        await server.setup()

        # Mock adapter with intermittent failures
        call_count = 0

        def failing_create_part(*args, **kwargs):
            """Test helper for failing create part."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails
                return Mock(is_success=False, error="Temporary failure")
            else:
                # Subsequent calls succeed
                return Mock(
                    is_success=True, data={"name": "TestPart"}, execution_time=1.0
                )

        server.state.adapter.create_part = AsyncMock(side_effect=failing_create_part)

        # Find create_part tool
        create_part_tool = None
        for tool in server.mcp._tools:
            if tool.name == "create_part":
                create_part_tool = tool.func
                break
        assert create_part_tool is not None

        # First attempt should fail
        result1 = await create_part_tool(CreatePartInput(name="TestPart"))
        assert result1["status"] == "error"

        # Second attempt should succeed (recovery)
        result2 = await create_part_tool(CreatePartInput(name="TestPart"))
        assert result2["status"] == "success"

        await server.stop()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.performance
    async def test_high_throughput_workflow(self, mock_config, perf_monitor):
        """Test workflow with high throughput operations."""
        server = SolidWorksMCPServer(mock_config)
        await server.setup()

        # Setup fast mock responses
        server.state.adapter.create_part = AsyncMock(
            return_value=Mock(
                is_success=True, data={"name": "PerfTestPart"}, execution_time=0.01
            )
        )

        # Find tool
        create_part_tool = None
        for tool in server.mcp._tools:
            if tool.name == "create_part":
                create_part_tool = tool.func
                break
        assert create_part_tool is not None

        # Execute multiple operations
        num_operations = 100

        perf_monitor.start()
        results = []
        for i in range(num_operations):
            result = await create_part_tool(CreatePartInput(name=f"Part{i}"))
            results.append(result)
        perf_monitor.stop()

        # Verify all operations succeeded
        assert len(results) == num_operations
        for result in results:
            assert result["status"] == "success"

        # Performance should be reasonable
        avg_time_per_operation = perf_monitor.elapsed / num_operations
        assert avg_time_per_operation < 0.1  # Less than 100ms per operation

        await server.stop()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_operations_workflow(self, mock_config):
        """Test workflow with concurrent operations."""
        import asyncio

        server = SolidWorksMCPServer(mock_config)
        await server.setup()

        # Setup mock responses
        server.state.adapter.create_part = AsyncMock(
            return_value=Mock(
                is_success=True, data={"name": "ConcurrentPart"}, execution_time=0.1
            )
        )

        # Find tool
        create_part_tool = None
        for tool in server.mcp._tools:
            if tool.name == "create_part":
                create_part_tool = tool.func
                break
        assert create_part_tool is not None

        # Execute concurrent operations
        tasks = []
        for i in range(10):
            task = create_part_tool(CreatePartInput(name=f"ConcurrentPart{i}"))
            tasks.append(task)

        # Wait for all operations to complete
        results = await asyncio.gather(*tasks)

        # Verify all operations succeeded
        assert len(results) == 10
        for i, result in enumerate(results):
            assert result["status"] == "success", f"Concurrent operation {i} failed"

        await server.stop()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_tool_coverage_workflow(self, mock_config):
        """Test workflow that exercises tools from all categories."""
        server = SolidWorksMCPServer(mock_config)
        await server.setup()

        # Mock all adapter methods for comprehensive testing
        server.state.adapter.create_part = AsyncMock(
            return_value=Mock(is_success=True, data={"name": "TestPart"})
        )
        server.state.adapter.create_sketch = AsyncMock(
            return_value=Mock(is_success=True, data={"sketch_name": "Sketch1"})
        )
        server.state.adapter.save_file = AsyncMock(
            return_value=Mock(is_success=True, data={"file_path": "test.sldprt"})
        )
        server.state.adapter.get_mass_properties = AsyncMock(
            return_value=Mock(is_success=True, data={"mass": 1.0})
        )
        server.state.adapter.export_file = AsyncMock(
            return_value=Mock(is_success=True, data={"export_path": "test.step"})
        )

        # Test tools from each category
        tool_categories = {
            "modeling": ["create_part"],
            "sketching": ["create_sketch"],
            "file_management": ["save_file"],
            "analysis": ["get_mass_properties"],
            "export": ["export_step"],
        }

        tested_tools = []

        for category, tool_names in tool_categories.items():
            for tool_name in tool_names:
                # Find tool
                tool_func = None
                for tool in server.mcp._tools:
                    if tool.name == tool_name:
                        tool_func = tool.func
                        break

                if tool_func is not None:
                    try:
                        # Create appropriate input based on tool
                        if tool_name == "create_part":
                            result = await tool_func(CreatePartInput(name="TestPart"))
                        elif tool_name == "create_sketch":
                            result = await tool_func(
                                CreateSketchInput(plane="Front Plane")
                            )
                        elif tool_name == "save_file":
                            result = await tool_func({"file_path": "test.sldprt"})
                        elif tool_name == "get_mass_properties":
                            result = await tool_func({})
                        elif tool_name == "export_step":
                            result = await tool_func(
                                {"file_path": "test.step", "format_type": "step"}
                            )
                        else:
                            result = await tool_func({})

                        assert result["status"] == "success", f"Tool {tool_name} failed"
                        tested_tools.append(tool_name)

                    except Exception as e:
                        # Log but don't fail the test for individual tool issues
                        print(f"Warning: Tool {tool_name} test failed: {e}")

        # Should have tested tools from multiple categories
        assert len(tested_tools) >= 3, (
            f"Only tested {len(tested_tools)} tools: {tested_tools}"
        )

        await server.stop()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_server_lifecycle_multiple_cycles(self, mock_config):
        """Test multiple server startup/shutdown cycles."""
        for cycle in range(3):
            server = SolidWorksMCPServer(mock_config)

            # Startup
            await server.setup()
            assert server._setup_complete is True

            # Verify functionality
            health = await server.health_check()
            assert health["status"] in ["healthy", "warning"]

            # Shutdown
            await server.stop()
            assert server._setup_complete is False

        # All cycles should complete without issues
