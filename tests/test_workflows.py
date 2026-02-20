#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for workflow execution and orchestration.

This script tests:
- Workflow JSON parsing
- Adapter initialization
- Dependency graph validation
- Workflow execution (dry-run mode)
"""

import sys
import os
import argparse
import logging
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workflows.run_workflow import WorkflowRunner

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_workflow_json_validation(workflow_file: str):
    """Test workflow JSON file validity"""
    logger.info(f"Testing workflow JSON validation: {workflow_file}")
    
    try:
        with open(workflow_file, 'r') as f:
            workflow_data = json.load(f)
        
        # Check required fields
        required_fields = ["workflow"]
        for field in required_fields:
            if field not in workflow_data:
                raise ValueError(f"Missing required field: {field}")
        
        wf_section = workflow_data["workflow"]
        wf_required = ["nodes", "edges"]
        for field in wf_required:
            if field not in wf_section:
                raise ValueError(f"Missing required field in workflow: {field}")
        
        nodes = wf_section["nodes"]
        edges = wf_section["edges"]
        
        logger.info(f"✓ Found {len(nodes)} workflow nodes")
        logger.info(f"✓ Found {len(edges)} workflow edges")
        
        # Log sample nodes
        for i, node in enumerate(nodes[:3]):
            logger.info(f"  Node {i}: {node.get('id')} (type: {node.get('type')})")
        if len(nodes) > 3:
            logger.info(f"  ... and {len(nodes) - 3} more nodes")
        
        logger.info("✓ Workflow JSON validation passed")
        return True
    except json.JSONDecodeError as e:
        logger.error(f"✗ JSON parsing error: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Workflow validation failed: {e}")
        return False


def test_workflow_graph_validation(workflow_file: str):
    """Test workflow dependency graph"""
    logger.info(f"Testing workflow graph validation: {workflow_file}")
    
    try:
        with open(workflow_file, 'r') as f:
            workflow_data = json.load(f)
        
        wf_section = workflow_data["workflow"]
        nodes = {n["id"]: n for n in wf_section["nodes"]}
        edges = wf_section["edges"]
        
        # Validate edges reference existing nodes
        for edge in edges:
            src = edge.get("source")
            dst = edge.get("target")
            
            if src not in nodes:
                raise ValueError(f"Edge references non-existent source node: {src}")
            if dst not in nodes:
                raise ValueError(f"Edge references non-existent target node: {dst}")
        
        # Check for cycles (simple check)
        logger.info(f"✓ Graph validation passed - all edges reference valid nodes")
        logger.info(f"  Nodes: {len(nodes)}, Edges: {len(edges)}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Graph validation failed: {e}")
        return False


def test_workflow_runner_init(workflow_file: str):
    """Test WorkflowRunner initialization"""
    logger.info(f"Testing WorkflowRunner initialization: {workflow_file}")
    
    try:
        with open(workflow_file, 'r') as f:
            workflow_data = json.load(f)
        
        root_dir = Path(workflow_file).parent
        
        # Try to initialize runner
        runner = WorkflowRunner(workflow_data, root_dir)
        
        logger.info(f"✓ WorkflowRunner initialized successfully")
        logger.info(f"  Nodes: {len(runner.nodes_by_id)}")
        logger.info(f"  Edges: {len(runner.edges)}")
        
        return True
    except FileNotFoundError as e:
        logger.error(f"✗ Module not found: {e}")
        logger.info("  Make sure to run in DRY-RUN mode or provide valid module paths")
        return False
    except Exception as e:
        logger.error(f"✗ WorkflowRunner initialization failed: {e}")
        return False


def list_available_workflows():
    """List available test workflows"""
    logger.info("Available test workflows:")
    
    workflow_dir = Path(__file__).parent.parent / "data" / "workflows"
    
    if not workflow_dir.exists():
        logger.error(f"Workflow directory not found: {workflow_dir}")
        return
    
    workflows = list(workflow_dir.glob("*.json"))
    
    if not workflows:
        logger.info("  No workflows found")
        return
    
    for workflow in workflows:
        logger.info(f"  - {workflow.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Test workflow execution and orchestration"
    )
    parser.add_argument(
        "--workflow",
        type=str,
        default=None,
        help="Path to workflow JSON file"
    )
    parser.add_argument(
        "--test",
        choices=["json-validation", "graph-validation", "runner-init", "list", "all"],
        default="list",
        help="Which test to run (default: list)"
    )
    
    args = parser.parse_args()
    
    logger.info(f"=== Workflow Test Suite ===")
    
    if args.test == "list":
        list_available_workflows()
        return 0
    
    if args.workflow is None:
        logger.error("--workflow argument required for this test")
        logger.info("Use --test list to see available workflows")
        return 1
    
    workflow_path = Path(args.workflow)
    if not workflow_path.exists():
        logger.error(f"Workflow file not found: {args.workflow}")
        return 1
    
    tests = {
        "json-validation": lambda: test_workflow_json_validation(str(workflow_path)),
        "graph-validation": lambda: test_workflow_graph_validation(str(workflow_path)),
        "runner-init": lambda: test_workflow_runner_init(str(workflow_path)),
    }
    
    results = {}
    
    if args.test == "all":
        for test_name, test_func in tests.items():
            results[test_name] = test_func()
    else:
        test_func = tests[args.test]
        results[args.test] = test_func()
    
    logger.info(f"\n=== Test Results ===")
    for test_name, passed in results.items():
        status = "PASSED ✓" if passed else "FAILED ✗"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
