from enum import Enum


class AwsRegion(str, Enum):
    # NB: add all required regions and corresponding IOLVM AMI_ID in ENV_VARS!

    US_EAST_1 = "us-east-1"  # Virginia

    # US_EAST_2 = "us-east-2"

    # US_WEST_1 = "us-west-1"

    US_WEST_2 = "us-west-2"  # Oregon
