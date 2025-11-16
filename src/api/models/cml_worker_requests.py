"""Request DTOs for CML Worker API endpoints."""

from pydantic import BaseModel, Field, model_validator

from application.settings import app_settings


class CreateCMLWorkerRequest(BaseModel):
    """Request body for creating a new CML Worker."""

    name: str = Field(..., description="Human-readable name for the worker")
    instance_type: str = Field(..., description="EC2 instance type")
    ami_id: str | None = Field(
        None, description="Optional AMI ID (uses regional default if not provided)"
    )
    ami_name: str | None = Field(None, description="Optional AMI name")
    cml_version: str | None = Field(None, description="CML version to be installed")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "cml-worker-prod-01",
                "instance_type": "c5.2xlarge",
                "ami_id": "ami-0abcdef1234567890",
                "ami_name": "cml-worker-ami-2.7.0",
                "cml_version": "2.7.0",
            }
        }


class UpdateCMLWorkerTagsRequest(BaseModel):
    """Request body for updating CML Worker tags."""

    tags: dict[str, str] = Field(..., description="Tags to add or update")

    class Config:
        json_schema_extra = {
            "example": {
                "tags": {
                    "Environment": "Production",
                    "Team": "DevOps",
                    "CostCenter": "Engineering",
                }
            }
        }


class RegisterLicenseRequest(BaseModel):
    """Request body for registering CML license."""

    license_token: str = Field(..., description="CML license registration token")

    class Config:
        json_schema_extra = {"example": {"license_token": "ABCD-1234-EFGH-5678"}}


class ImportCMLWorkerRequest(BaseModel):
    """Request model for importing existing EC2 instances as CML Workers.

    You can import an instance by providing one of the following:
    - aws_instance_id: Direct lookup by EC2 instance ID
    - ami_id: Search for instances using this AMI ID
    - ami_name: Search for instances with matching AMI name

    At least one search criterion must be provided.

    The 'name' field is optional - if not provided, the AWS instance's
    name will be used automatically.
    """

    aws_instance_id: str | None = Field(
        None,
        description="AWS EC2 instance ID (e.g., 'i-1234567890abcdef0'). "
        "If provided, directly import this instance.",
        examples=["i-0abcdef1234567890"],
    )

    ami_id: str | None = Field(
        None,
        description="AMI ID to search for (e.g., 'ami-0c55b159cbfafe1f0'). "
        "Will import the first instance found with this AMI.",
        examples=["ami-0c55b159cbfafe1f0"],
    )

    ami_name: str | None = Field(
        None,
        description="AMI name pattern to search for. "
        "Will import the first instance found with matching AMI name.",
        examples=[app_settings.cml_worker_ami_name_default],
    )

    name: str | None = Field(
        None,
        description="Optional friendly name for the worker. "
        "If not provided, uses the AWS instance's name automatically.",
        examples=["cml-worker-imported-01"],
    )

    @model_validator(mode="after")
    def validate_search_criteria(self) -> "ImportCMLWorkerRequest":
        """Ensure at least one search criterion is provided."""
        if not any([self.aws_instance_id, self.ami_id, self.ami_name]):
            raise ValueError(
                "Must provide at least one of: aws_instance_id, ami_id, or ami_name"
            )
        return self

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "ami_name": app_settings.cml_worker_ami_name_default,
                },
                {
                    "ami_id": "ami-0c55b159cbfafe1f0",
                },
                {
                    "aws_instance_id": "i-0abcdef1234567890",
                    "name": "imported-worker-01",
                },
                {
                    "aws_instance_id": "i-0abcdef1234567890",
                },
            ]
        }
