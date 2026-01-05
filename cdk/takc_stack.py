"""
TAKC Infrastructure Stack
Defines all AWS resources for the TAKC system
"""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    BundlingOptions,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_ec2 as ec2,
    aws_elasticache as elasticache,
    aws_iam as iam,
    aws_apigateway as apigw,
    aws_s3_notifications as s3n,
    aws_cloudwatch as cloudwatch,
    aws_wafv2 as wafv2,
    aws_kms as kms,
    aws_cognito as cognito,
)
from constructs import Construct
import random
import string


class TakcStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Get context variables
        environment = self.node.try_get_context("environment") or "dev"
        project_name = self.node.try_get_context("project_name") or "TAKC"
        bedrock_model_id = self.node.try_get_context("bedrock_model_id") or \
            "anthropic.claude-3-haiku-20240307-v1:0"
        
        # Generate unique suffix
        name_suffix = ''.join(random.choices(string.hexdigits.lower(), k=8))
        
        # Common tags
        tags = {
            "Project": project_name,
            "Environment": environment,
            "ManagedBy": "CDK"
        }
        
        # Use default VPC (simpler for reference implementation)
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)
        
        # KMS Key for S3 bucket encryption
        kms_key = kms.Key(
            self, "TakcKmsKey",
            description="KMS key for TAKC S3 bucket encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN
        )
        
        # S3 Bucket for data storage with KMS encryption
        data_bucket = s3.Bucket(
            self, "TakcDataBucket",
            bucket_name=f"takc-processed-data-{name_suffix}",
            versioned=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=kms_key,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False
        )
        
        # Security group for Lambda functions
        lambda_sg = ec2.SecurityGroup(
            self, "TakcLambdaSG",
            vpc=vpc,
            description="Security group for TAKC Lambda functions",
            security_group_name=f"takc-lambda-sg-{name_suffix}",
            allow_all_outbound=True
        )
        
        # Security group for ElastiCache
        cache_sg = ec2.SecurityGroup(
            self, "TakcCacheSG",
            vpc=vpc,
            description="Security group for TAKC ElastiCache",
            security_group_name=f"takc-cache-sg-{name_suffix}",
            allow_all_outbound=False
        )
        
        # ElastiCache Serverless - Fast provisioning, auto-scaling, Redis-compatible
        cache_sg.add_ingress_rule(
            peer=lambda_sg,
            connection=ec2.Port.tcp(6379),
            description="Allow Redis access from Lambda"
        )
        
        # ElastiCache Serverless Cache (using default VPC subnets - needs 2-3 subnets)
        # Get first 2-3 subnets from default VPC
        subnet_ids = [subnet.subnet_id for subnet in vpc.public_subnets[:3]]
        
        serverless_cache = elasticache.CfnServerlessCache(
            self, "TakcServerlessCache",
            serverless_cache_name=f"takc-cache-{name_suffix}",
            engine="redis",
            description="TAKC Serverless Redis cache for compressed data",
            security_group_ids=[cache_sg.security_group_id],
            subnet_ids=subnet_ids,
            # Optional: Configure cache limits
            cache_usage_limits=elasticache.CfnServerlessCache.CacheUsageLimitsProperty(
                data_storage=elasticache.CfnServerlessCache.DataStorageProperty(
                    unit="GB",
                    maximum=5  # Max 5GB for demo, adjust as needed
                ),
                ecpu_per_second=elasticache.CfnServerlessCache.ECPUPerSecondProperty(
                    maximum=5000  # Max 5000 ECPU/sec
                )
            )
        )
        
        cache_endpoint = serverless_cache.attr_endpoint_address
        cache_port = serverless_cache.attr_endpoint_port
        
        # IAM Role for Lambda functions
        lambda_role = iam.Role(
            self, "TakcLambdaRole",
            role_name=f"takc-lambda-role-{name_suffix}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )
        
        # Add permissions for S3, Bedrock, and Lambda invocation
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            resources=[
                data_bucket.bucket_arn,
                f"{data_bucket.bucket_arn}/*"
            ]
        ))
        
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            resources=["*"]
        ))
        
        # Add Lambda invoke permission (wildcard to avoid circular dependency)
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["lambda:InvokeFunction"],
            resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:takc-compression-processor-{name_suffix}"]
        ))
        
        # Grant Lambda role permission to use KMS key for S3 encryption/decryption
        kms_key.grant_encrypt_decrypt(lambda_role)
        
        # Common Lambda environment variables
        common_env = {
            "S3_BUCKET": data_bucket.bucket_name,
            "REDIS_ENDPOINT": cache_endpoint,
            "REDIS_PORT": str(cache_port),
            "BEDROCK_MODEL_ID": bedrock_model_id,
            "AWS_ACCOUNT_ID": self.account
        }
        
        # Compression Processor Lambda (no VPC for simplicity in reference implementation)
        compression_lambda = lambda_.Function(
            self, "TakcCompressionProcessor",
            function_name=f"takc-compression-processor-{name_suffix}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="bedrock_compression_service.lambda_handler",
            code=lambda_.Code.from_asset(
                "../src",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && "
                        "cp bedrock_compression_service.py compression_service.py /asset-output/"
                    ]
                )
            ),
            role=lambda_role,
            timeout=Duration.minutes(15),
            memory_size=2048,
            environment=common_env
        )
        
        # Data Processor Lambda (no VPC for simplicity in reference implementation)
        data_processor_env = common_env.copy()
        data_processor_env["COMPRESSION_LAMBDA_NAME"] = compression_lambda.function_name
        
        data_processor_lambda = lambda_.Function(
            self, "TakcDataProcessor",
            function_name=f"takc-data-processor-{name_suffix}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="data_processor.lambda_handler",
            code=lambda_.Code.from_asset(
                "../src",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && "
                        "cp data_processor.py compression_service.py /asset-output/"
                    ]
                )
            ),
            role=lambda_role,
            timeout=Duration.minutes(
                self.node.try_get_context("lambda_timeout_data_processor") or 5
            ),
            memory_size=self.node.try_get_context("lambda_memory_data_processor") or 512,
            environment=data_processor_env
        )
        
        # S3 Event Notification to trigger data processor
        data_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(data_processor_lambda),
            s3.NotificationKeyFilter(prefix="raw-data/", suffix=".txt")
        )
        
        # Query Processor Lambda (no VPC for simplicity in reference implementation)
        query_lambda = lambda_.Function(
            self, "TakcQueryProcessor",
            function_name=f"takc-query-processor-{name_suffix}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="query_processor.lambda_handler",
            code=lambda_.Code.from_asset(
                "../src",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements.txt -t /asset-output && "
                        "cp query_processor.py compression_service.py /asset-output/"
                    ]
                )
            ),
            role=lambda_role,
            timeout=Duration.seconds(
                self.node.try_get_context("lambda_timeout_query_processor") or 60
            ),
            memory_size=self.node.try_get_context("lambda_memory_query_processor") or 256,
            environment=common_env
        )
        
        # Cognito User Pool for authentication
        user_pool = cognito.UserPool(
            self, "TakcUserPool",
            user_pool_name=f"takc-user-pool-{name_suffix}",
            self_sign_up_enabled=False,  # Admin creates users only
            sign_in_aliases=cognito.SignInAliases(
                username=True,
                email=True
            ),
            auto_verify=cognito.AutoVerifiedAttrs(email=False),  # No email verification for demo
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False
            ),
            account_recovery=cognito.AccountRecovery.NONE,  # Simplified for demo
            removal_policy=RemovalPolicy.DESTROY  # Allow cleanup
        )
        
        # Cognito User Pool Client
        user_pool_client = cognito.UserPoolClient(
            self, "TakcUserPoolClient",
            user_pool=user_pool,
            user_pool_client_name=f"takc-client-{name_suffix}",
            auth_flows=cognito.AuthFlow(
                user_password=True,  # Enable username/password auth
                admin_user_password=True  # Enable admin auth
            ),
            generate_secret=False,  # No client secret for simplicity
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30)
        )
        
        # API Gateway
        api = apigw.RestApi(
            self, "TakcApi",
            rest_api_name=f"takc-api-{name_suffix}",
            description="TAKC Query API",
            deploy_options=apigw.StageOptions(
                stage_name=environment,
                throttling_rate_limit=100,
                throttling_burst_limit=200
            )
        )
        
        # Cognito Authorizer for API Gateway
        cognito_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "TakcCognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name=f"takc-cognito-authorizer-{name_suffix}",
            identity_source="method.request.header.Authorization"
        )
        
        # API Gateway /query endpoint with Cognito authorization
        query_resource = api.root.add_resource("query")
        query_integration = apigw.LambdaIntegration(query_lambda)
        query_resource.add_method(
            "POST", 
            query_integration,
            authorizer=cognito_authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO
        )
        
        # AWS WAF for API Gateway protection
        waf_rules = []
        
        # Rule 1: Rate limiting - prevent abuse
        waf_rules.append(wafv2.CfnWebACL.RuleProperty(
            name="RateLimitRule",
            priority=1,
            statement=wafv2.CfnWebACL.StatementProperty(
                rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                    limit=2000,  # 2000 requests per 5 minutes per IP
                    aggregate_key_type="IP"
                )
            ),
            action=wafv2.CfnWebACL.RuleActionProperty(
                block=wafv2.CfnWebACL.BlockActionProperty()
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name="RateLimitRule"
            )
        ))
        
        # Rule 2: AWS Managed Rules - Common Rule Set (protects against common threats)
        waf_rules.append(wafv2.CfnWebACL.RuleProperty(
            name="AWSManagedRulesCommonRuleSet",
            priority=2,
            statement=wafv2.CfnWebACL.StatementProperty(
                managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                    vendor_name="AWS",
                    name="AWSManagedRulesCommonRuleSet"
                )
            ),
            override_action=wafv2.CfnWebACL.OverrideActionProperty(
                none={}
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name="AWSManagedRulesCommonRuleSet"
            )
        ))
        
        # Rule 3: AWS Managed Rules - Known Bad Inputs
        waf_rules.append(wafv2.CfnWebACL.RuleProperty(
            name="AWSManagedRulesKnownBadInputsRuleSet",
            priority=3,
            statement=wafv2.CfnWebACL.StatementProperty(
                managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                    vendor_name="AWS",
                    name="AWSManagedRulesKnownBadInputsRuleSet"
                )
            ),
            override_action=wafv2.CfnWebACL.OverrideActionProperty(
                none={}
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name="AWSManagedRulesKnownBadInputsRuleSet"
            )
        ))
        
        # Create WAF Web ACL
        web_acl = wafv2.CfnWebACL(
            self, "TakcWebACL",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow=wafv2.CfnWebACL.AllowActionProperty()
            ),
            rules=waf_rules,
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name="TakcWebACL"
            ),
            name=f"takc-web-acl-{name_suffix}",
            description="WAF Web ACL for TAKC API Gateway protection"
        )
        
        # Associate WAF with API Gateway
        wafv2.CfnWebACLAssociation(
            self, "TakcWebACLAssociation",
            resource_arn=f"arn:aws:apigateway:{self.region}::/restapis/{api.rest_api_id}/stages/{api.deployment_stage.stage_name}",
            web_acl_arn=web_acl.attr_arn
        )
        
        # CloudWatch Alarms (if monitoring enabled)
        enable_monitoring = self.node.try_get_context("enable_monitoring")
        if enable_monitoring is None or enable_monitoring:
            # Data Processor errors alarm
            cloudwatch.Alarm(
                self, "DataProcessorErrors",
                alarm_name=f"takc-data-processor-errors-{name_suffix}",
                metric=data_processor_lambda.metric_errors(),
                threshold=5,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
            )
            
            # Compression Processor errors alarm
            cloudwatch.Alarm(
                self, "CompressionProcessorErrors",
                alarm_name=f"takc-compression-processor-errors-{name_suffix}",
                metric=compression_lambda.metric_errors(),
                threshold=5,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
            )
            
            # Query Processor errors alarm
            cloudwatch.Alarm(
                self, "QueryProcessorErrors",
                alarm_name=f"takc-query-processor-errors-{name_suffix}",
                metric=query_lambda.metric_errors(),
                threshold=10,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
            )
        
        # Outputs
        CfnOutput(
            self, "ApiEndpoint",
            value=api.url,
            description="API Gateway endpoint URL"
        )
        
        CfnOutput(
            self, "DataBucketName",
            value=data_bucket.bucket_name,
            description="S3 bucket for data storage"
        )
        
        CfnOutput(
            self, "RedisEndpoint",
            value=f"{cache_endpoint}:{cache_port}",
            description="ElastiCache Serverless Redis endpoint"
        )
        
        CfnOutput(
            self, "DataProcessorFunction",
            value=data_processor_lambda.function_name,
            description="Data processor Lambda function name"
        )
        
        CfnOutput(
            self, "CompressionProcessorFunction",
            value=compression_lambda.function_name,
            description="Compression processor Lambda function name"
        )
        
        CfnOutput(
            self, "QueryProcessorFunction",
            value=query_lambda.function_name,
            description="Query processor Lambda function name"
        )
        
        CfnOutput(
            self, "WebACLArn",
            value=web_acl.attr_arn,
            description="AWS WAF Web ACL ARN protecting the API Gateway"
        )
        
        CfnOutput(
            self, "KmsKeyId",
            value=kms_key.key_id,
            description="KMS Key ID for S3 bucket encryption"
        )
        
        CfnOutput(
            self, "UserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID for authentication"
        )
        
        CfnOutput(
            self, "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID"
        )
