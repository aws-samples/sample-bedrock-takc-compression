#!/usr/bin/env python3
"""
TAKC CDK Application Entry Point
Deploys Task-Aware Knowledge Compression infrastructure on AWS
"""
import aws_cdk as cdk
from takc_stack import TakcStack

app = cdk.App()

import os

TakcStack(
    app, 
    "TakcStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT") or app.node.try_get_context("aws_account_id") or "119145850660",
        region=os.environ.get("CDK_DEFAULT_REGION") or app.node.try_get_context("aws_region") or "us-east-1"
    ),
    description="TAKC - Task-Aware Knowledge Compression Infrastructure"
)

app.synth()
