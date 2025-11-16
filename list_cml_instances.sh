#!/bin/bash
# Script to list available EC2 instances with the CML AMI

set -e

AWS_REGION="${1:-us-east-1}"
AMI_NAME_PATTERN="${2:-cisco-cml2.9-lablet-v0.1.7}"

echo "🔍 Checking for EC2 instances with AMI name pattern: ${AMI_NAME_PATTERN}"
echo ""

# First, find AMI IDs matching the name pattern
echo "📋 Step 1: Finding AMI IDs..."
AMI_IDS=$(aws ec2 describe-images \
  --region "$AWS_REGION" \
  --filters "Name=name,Values=$AMI_NAME_PATTERN" \
  --query 'Images[*].ImageId' \
  --output text)

if [ -z "$AMI_IDS" ]; then
  echo "❌ No AMIs found matching pattern: $AMI_NAME_PATTERN"
  exit 1
fi

echo "✅ Found AMI IDs: $AMI_IDS"
echo ""

# Now search for instances using these AMIs
echo "📋 Step 2: Finding instances using these AMIs..."
for AMI_ID in $AMI_IDS; do
  echo ""
  echo "Instances using AMI: $AMI_ID"
  aws ec2 describe-instances \
    --region "$AWS_REGION" \
    --filters "Name=image-id,Values=$AMI_ID" \
    --query 'Reservations[*].Instances[*].[InstanceId, InstanceType, State.Name, Tags[?Key==`Name`].Value | [0]]' \
    --output table
done
