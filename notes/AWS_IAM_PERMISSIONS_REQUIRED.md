# AWS IAM Permissions Required

## Current Issue

The IAM user `cml-cloud-manager-service` lacks permission to enable detailed CloudWatch monitoring.

### Error

```
User: arn:aws:iam::975051357194:user/cml-cloud-manager-service is not authorized to perform: ec2:MonitorInstances on resource: arn:aws:ec2:us-east-1:975051357194:instance/i-0d41154137323bf58 because no identity-based policy allows the ec2:MonitorInstances action
```

## Required IAM Policy

Add this policy to the `cml-cloud-manager-service` IAM user:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:MonitorInstances",
                "ec2:UnmonitorInstances"
            ],
            "Resource": "arn:aws:ec2:*:975051357194:instance/*"
        }
    ]
}
```

## Complete Required Permissions

The service needs these EC2 permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeInstanceStatus",
                "ec2:DescribeImages",
                "ec2:DescribeTags",
                "ec2:RunInstances",
                "ec2:StartInstances",
                "ec2:StopInstances",
                "ec2:TerminateInstances",
                "ec2:CreateTags",
                "ec2:DeleteTags",
                "ec2:MonitorInstances",
                "ec2:UnmonitorInstances"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics"
            ],
            "Resource": "*"
        }
    ]
}
```

## How to Apply

1. Go to AWS IAM Console
2. Find user: `cml-cloud-manager-service`
3. Attach inline policy or update existing policy with the permissions above
4. Test by clicking "Enable Detailed Monitoring" button in the UI
