"""Request DTOs for CML Worker API endpoints."""

from pydantic import BaseModel, Field


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
